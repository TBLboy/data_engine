"""Ollama HTTP API 客户端。

默认不启用，配置显式打开后才调用 LLM。
调用失败时不抛异常，返回 None 触发 fallback。
"""

from __future__ import annotations

import logging
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


def call_ollama(prompt: str, *, base_url: str, model: str, timeout_seconds: int) -> LlmResult | None:
    """调用 Ollama chat API（非流式）。失败返回 None。"""
    t0 = time.monotonic()
    try:
        resp = httpx.post(
            f"{base_url.rstrip('/')}/api/chat",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 2048},
            },
            timeout=timeout_seconds,
        )
        latency_ms = int((time.monotonic() - t0) * 1000)
        if resp.status_code != 200:
            logger.warning("Ollama returned %d: %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json()
        text = (data.get("message") or {}).get("content", "")
        if not text or not text.strip():
            logger.warning("Ollama returned empty response")
            return None
        return LlmResult(text=text.strip(), model=model, latency_ms=latency_ms)
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
