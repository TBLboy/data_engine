"""Ollama HTTP API 客户端。

默认不启用，配置显式打开后才调用 LLM。
调用失败时不抛异常，返回 None 触发 fallback。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Generator
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass
class LlmResult:
    text: str
    model: str
    latency_ms: int


def _is_image_unsupported_error(status_code: int, body: str) -> bool:
    if status_code not in {400, 404, 500}:
        return False
    lowered = (body or '').lower()
    markers = (
        'image input is not supported',
        'mmproj',
        'does not support images',
        'vision not supported',
        'images are not supported',
    )
    return any(marker in lowered for marker in markers)


def _looks_like_json_payload(text: str) -> bool:
    if not text:
        return False
    stripped = text.strip()
    if stripped.startswith('{') and ('canonicalInstructionEn' in stripped or 'occurrences' in stripped):
        return True
    return bool(
        re.search(
            r'\{\s*"(?:canonicalInstructionEn|occurrences|taskOutcome)"',
            stripped,
        )
    )


def _prefer_structured_text(content: str, thinking: str) -> str:
    """Pick the field most likely to contain usable JSON for annotation VLM."""
    content = (content or '').strip()
    thinking = (thinking or '').strip()
    if _looks_like_json_payload(content):
        return content
    if _looks_like_json_payload(thinking):
        return thinking
    # Prefer content even if incomplete JSON; else fall back to thinking prose.
    if content:
        return content
    return thinking


def call_ollama_generate(
    prompt: str,
    *,
    base_url: str,
    model: str,
    timeout_seconds: int,
    format: str | None = None,
    temperature: float = 0.0,
    num_predict: int = 1024,
    think: bool | None = False,
) -> LlmResult | None:
    """Call Ollama /api/generate (text-only). Prefer this for JSON conversion.

    On qwen3-thinking, /api/generate + think=false reliably fills response
    instead of dumping analysis into thinking with empty content.
    """
    t0 = time.monotonic()
    try:
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if format:
            payload["format"] = format
        if think is not None:
            payload["think"] = bool(think)
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/generate",
            json=payload,
            timeout=timeout_seconds,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            logger.warning("Ollama generate returned %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        text = data.get("response") or ""
        thinking = data.get("thinking") or ""
        text = _prefer_structured_text(str(text), str(thinking))
        if not text or not str(text).strip():
            logger.warning("Ollama generate returned empty response")
            return None
        return LlmResult(text=str(text).strip(), model=model, latency_ms=latency_ms)
    except httpx.TimeoutException:
        logger.warning("Ollama generate timed out after %ds", timeout_seconds)
        return None
    except Exception:
        logger.exception("Ollama generate call failed")
        return None


def call_ollama(
    prompt: str,
    *,
    base_url: str,
    model: str,
    timeout_seconds: int,
    format: str | None = None,
    temperature: float = 0.3,
    num_predict: int = 2048,
    images_b64: list[str] | None = None,
    think: bool | None = None,
) -> LlmResult | None:
    """调用 Ollama chat API（非流式）。失败返回 None。

    images_b64: optional list of raw base64-encoded images (no data-URI prefix)
    for vision models such as qwen3-vl.
    think: when False, request non-thinking content path (Ollama qwen3-thinking models).
    """
    t0 = time.monotonic()
    try:
        message: dict = {"role": "user", "content": prompt}
        if images_b64:
            message["images"] = list(images_b64)
        messages: list[dict] = [message]
        if format == 'json':
            messages.insert(
                0,
                {
                    "role": "system",
                    "content": (
                        "You are a JSON API. Reply with a single JSON object only. "
                        "Do not write analysis. Put the final JSON in message content."
                    ),
                },
            )
        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": num_predict},
        }
        if format:
            payload["format"] = format
        if think is not None:
            # Ollama qwen3-thinking: think=false routes tokens to content.
            payload["think"] = bool(think)
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json=payload,
            timeout=timeout_seconds,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            body = resp.text[:500]
            logger.warning("Ollama returned %d: %s", resp.status_code, body[:200])
            # Vision path unsupported (missing mmproj / non-vision model): one text-only retry.
            if images_b64 and _is_image_unsupported_error(resp.status_code, body):
                logger.warning("Ollama image input unsupported; retrying text-only")
                return call_ollama(
                    prompt,
                    base_url=base_url,
                    model=model,
                    timeout_seconds=timeout_seconds,
                    format=format,
                    temperature=temperature,
                    num_predict=num_predict,
                    images_b64=None,
                    think=think,
                )
            return None
        data = resp.json()
        message = data.get("message") or {}
        content = message.get("content", "") or ""
        thinking = message.get("thinking") or data.get("thinking") or ""
        text = _prefer_structured_text(str(content), str(thinking))
        if not text or not str(text).strip():
            logger.warning("Ollama returned empty response")
            return None
        return LlmResult(text=str(text).strip(), model=model, latency_ms=latency_ms)
    except httpx.TimeoutException:
        logger.warning("Ollama timed out after %ds", timeout_seconds)
        return None
    except Exception:
        logger.exception("Ollama call failed")
        return None


def call_ollama_stream(
    prompt: str,
    *,
    base_url: str,
    model: str,
    timeout_seconds: int,
) -> Generator[tuple[str, str], None, None] | None:
    """调用 Ollama chat API（流式），逐 token yield。失败返回 None。

    返回一个 Generator，每次 yield 一个 (kind, text) 元组。
    kind 为 "think" 表示思考过程（不展示给用户），"text" 表示正式回复。
    如果连接失败/超时，返回 None。
    """
    try:
        with httpx.stream(
            "POST",
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": True,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=timeout_seconds,
        ) as resp:
            if resp.status_code != 200:
                logger.warning("Ollama stream returned %d: %s", resp.status_code, resp.text[:200])
                return None

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    import json as _json
                    chunk = _json.loads(line)
                    msg = chunk.get("message") or {}
                    content = msg.get("content", "")
                    thinking = msg.get("thinking", "")
                    if thinking:
                        yield ("think", thinking)
                    if content:
                        yield ("text", content)
                    if chunk.get("done"):
                        break
                except Exception:
                    continue

    except httpx.TimeoutException:
        logger.warning("Ollama stream timed out after %ds", timeout_seconds)
        return None
    except Exception:
        logger.exception("Ollama stream call failed")
        return None
