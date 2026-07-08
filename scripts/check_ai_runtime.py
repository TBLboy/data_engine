#!/usr/bin/env python3
"""AI QC Runtime 环境核查脚本。

仅做检测和报告，不自动安装、不修改配置、不重启服务。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def warn(msg: str) -> None:
    print(f"  [WARN] {msg}")


def fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")


def check_python() -> None:
    print("── Python ──")
    v = sys.version_info
    ok(f"Python {v.major}.{v.minor}.{v.micro}")
    if v < (3, 10):
        warn("Python < 3.10，部分依赖可能不兼容")


def check_os() -> None:
    print("── OS ──")
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    ok(line.strip().split("=", 1)[1].strip('"'))
                    return
    except Exception:
        pass
    warn("无法读取 OS 信息")


def check_nvidia() -> None:
    print("── GPU ──")
    nvidia_smi = shutil.which("nvidia-smi")
    if not nvidia_smi:
        fail("nvidia-smi 不可用，GPU 驱动可能未安装")
        return
    try:
        out = subprocess.check_output([nvidia_smi, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                                      text=True, timeout=15)
        for line in out.strip().split("\n"):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 2:
                ok(f"GPU: {parts[0]}, VRAM: {parts[1]}")
    except Exception as e:
        fail(f"nvidia-smi 执行失败: {e}")
    try:
        out = subprocess.check_output([nvidia_smi], text=True, timeout=15)
        for line in out.split("\n"):
            if "CUDA Version" in line:
                ok(f"CUDA: {line.split(':')[-1].strip()}")
                break
    except Exception:
        pass


def check_docker() -> None:
    print("── Docker ──")
    docker = shutil.which("docker")
    if not docker:
        warn("Docker 未安装")
        return
    try:
        out = subprocess.check_output([docker, "--version"], text=True, timeout=10)
        ok(out.strip())
    except Exception:
        fail("Docker 不可用")
    compose = shutil.which("docker-compose") or shutil.which("docker")
    if compose:
        try:
            out = subprocess.check_output([compose, "compose", "version"],
                                          text=True, timeout=10)
            ok(f"Compose: {out.strip()}")
        except Exception:
            try:
                out = subprocess.check_output([compose, "compose", "version"],
                                              text=True, timeout=10)
            except Exception:
                warn("docker compose 不可用")


def check_ollama() -> None:
    print("── Ollama ──")
    ollama = shutil.which("ollama")
    if not ollama:
        warn("Ollama 未安装")
        return
    ok(f"Ollama binary: {ollama}")
    try:
        out = subprocess.check_output([ollama, "--version"], text=True, timeout=10)
        ok(f"Version: {out.strip()}")
    except Exception:
        fail("ollama --version 失败")

    # Check if ollama serve is reachable
    import urllib.request
    try:
        resp = urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5)
        if resp.status == 200:
            ok("Ollama 服务可访问 (localhost:11434)")
        else:
            warn(f"Ollama 服务返回 {resp.status}")
    except Exception:
        warn("Ollama 服务不可访问 (localhost:11434)，请确认 ollama serve 是否在运行")


def check_nvidia_container() -> None:
    print("── NVIDIA Container Toolkit ──")
    docker = shutil.which("docker")
    if not docker:
        warn("Docker 不可用，跳过检查")
        return
    try:
        result = subprocess.run(
            [docker, "run", "--rm", "--gpus", "all", "alpine", "echo", "gpu-ok"],
            capture_output=True, text=True, timeout=30
        )
        if "gpu-ok" in result.stdout:
            ok("Docker GPU 透传可用")
        else:
            warn(f"NVIDIA Container Toolkit 未配置或不可用: {result.stderr.strip()[:200]}")
    except Exception as e:
        warn(f"GPU 透传检查失败: {str(e)[:200]}")


def main() -> None:
    print("Robot QC AI Runtime Check\n")
    checks = [
        check_os,
        check_python,
        check_nvidia,
        check_docker,
        check_nvidia_container,
        check_ollama,
    ]
    for c in checks:
        c()
        print()
    print("Done.")


if __name__ == "__main__":
    main()
