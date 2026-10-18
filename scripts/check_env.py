#!/usr/bin/env python3
"""
scripts/check_env.py
Phase 0 Environment Verification & Hardware Baseline Gate.

Validates:
1. NVIDIA GPU VRAM headroom (>= 1,000 MB unallocated margin).
2. Ollama API responsiveness and model provisioning.
3. Docker daemon connectivity and container security constraints.
"""

import os
import shutil
import subprocess
import sys
from typing import Optional, Tuple

import requests

# Terminal formatting constants
CLR_RESET = "\033[0m"
CLR_GREEN = "\033[92m"
CLR_RED = "\033[91m"
CLR_YELLOW = "\033[93m"
CLR_BLUE = "\033[94m"


def log_step(name: str) -> None:
    print(f"\n{CLR_BLUE}=== [GATE] {name} ==={CLR_RESET}")


def log_pass(msg: str) -> None:
    print(f"  {CLR_GREEN}✔ PASS:{CLR_RESET} {msg}")


def log_warn(msg: str) -> None:
    print(f"  {CLR_YELLOW}⚠ WARN:{CLR_RESET} {msg}")


def log_fail(msg: str) -> None:
    print(f"  {CLR_RED}✖ FAIL:{CLR_RESET} {msg}")


# ----------------------------------------------------------------------
# 1. GPU VRAM Headroom Verification (ADR-12)
# ----------------------------------------------------------------------
def query_vram_via_nvml() -> Optional[Tuple[int, int, str]]:
    """Attempts to inspect VRAM using nvidia-ml-py."""
    try:
        import pynvml  # nvidia-ml-py exposes the pynvml namespace
        pynvml.nvmlInit()
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count == 0:
            return None

        # Select device 0 (primary GPU)
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        device_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(device_name, bytes):
            device_name = device_name.decode("utf-8")

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mb = int(mem_info.total / (1024 * 1024))
        free_mb = int(mem_info.free / (1024 * 1024))
        pynvml.nvmlShutdown()
        return total_mb, free_mb, device_name
    except Exception:
        return None


def query_vram_via_cli() -> Optional[Tuple[int, int, str]]:
    """Fallback: inspects VRAM by invoking nvidia-smi CLI directly."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        cmd = [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.free",
            "--format=csv,nounits,noheader",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().splitlines()
        if not lines:
            return None
        name, total_str, free_str = [x.strip() for x in lines[0].split(",")]
        return int(total_str), int(free_str), name
    except Exception:
        return None


def check_gpu_environment() -> bool:
    log_step("GPU VRAM Allocation & Headroom (Target: >= 1,000 MB Free)")

    # Check if running in CI environment
    if os.getenv("CI", "false").lower() == "true":
        log_warn("CI environment detected. Skipping physical GPU check (Mock Fallback Active).")
        return True

    gpu_data = query_vram_via_nvml()
    source = "nvidia-ml-py"

    if not gpu_data:
        gpu_data = query_vram_via_cli()
        source = "nvidia-smi CLI"

    if not gpu_data:
        log_fail("No NVIDIA GPU or drivers detected. Host does not satisfy hardware baseline.")
        return False

    total_mb, free_mb, dev_name = gpu_data
    print(f"  Device Name:   {dev_name}")
    print(f"  Total VRAM:    {total_mb:,} MB")
    print(f"  Free VRAM:     {free_mb:,} MB (via {source})")

    min_headroom_mb = 1000
    if free_mb < min_headroom_mb:
        log_fail(f"Insufficient VRAM headroom: {free_mb:,} MB available, but >= {min_headroom_mb:,} MB is required.")
        return False

    log_pass(f"Hardware headroom verified ({free_mb:,} MB >= {min_headroom_mb:,} MB).")
    return True


# ----------------------------------------------------------------------
# 2. Ollama Runtime & Model Provisioning (ADR-10)
# ----------------------------------------------------------------------
def check_ollama_environment() -> bool:
    log_step("Ollama Daemon & Provisioned Models")
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Step A: Ping daemon
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=2.0)
        if resp.status_code != 200:
            log_fail(f"Ollama returned HTTP {resp.status_code} at {base_url}.")
            return False
        log_pass(f"Ollama is responsive at {base_url}.")
    except requests.exceptions.RequestException as e:
        log_fail(f"Cannot connect to Ollama daemon at {base_url}. Did you run 'ollama serve'? Details: {e}")
        return False

    # Step B: Validate required models
    installed_models = [m.get("name") for m in resp.json().get("models", [])]
    required_models = [
        "qwen2.5:7b-instruct-q4_K_M",
        "nomic-embed-text:v1.5",
    ]

    all_models_present = True
    for req in required_models:
        # Check direct match or base match
        matches = [m for m in installed_models if m and (req in m or m in req)]
        if matches:
            log_pass(f"Model detected: {matches[0]}")
        else:
            log_fail(f"Required model missing: '{req}'. Run: ollama pull {req}")
            all_models_present = False

    if not all_models_present:
        return False

    # Step C: Pre-warm / Load Model into VRAM (ADR-10 Compliance)
    print(f"  {CLR_BLUE}ℹ INFO:{CLR_RESET} Pre-warming qwen2.5 into GPU VRAM (allowing up to 30s cold-load)...")
    try:
        warmup_payload = {
            "model": "qwen2.5:7b-instruct-q4_K_M",
            "prompt": "ping",
            "stream": False,
            "keep_alive": -1,  # Keep permanently loaded in VRAM (ADR-10)
            "options": {"num_predict": 1},
        }
        # Cold start timeout: 30 seconds for disk->VRAM transfer
        warmup_resp = requests.post(f"{base_url}/api/generate", json=warmup_payload, timeout=30.0)
        if warmup_resp.status_code != 200:
            log_fail(f"Model warm-up failed with HTTP {warmup_resp.status_code}: {warmup_resp.text}")
            return False
        log_pass("Model loaded and pre-warmed in VRAM with keep_alive enabled.")
    except requests.exceptions.Timeout:
        log_fail("Model cold-load timed out after 30s. Check storage read speed or Ollama logs.")
        return False
    except Exception as e:
        log_fail(f"Ollama pre-warm failed: {e}")
        return False

    # Step D: Rapid Warm Inference Latency Gate (SLA Target: <= 2.0s)
    try:
        ping_payload = {
            "model": "qwen2.5:7b-instruct-q4_K_M",
            "prompt": "1+1=",
            "stream": False,
            "options": {"num_predict": 1},
        }
        ping_resp = requests.post(f"{base_url}/api/generate", json=ping_payload, timeout=2.0)
        if ping_resp.status_code == 200:
            log_pass("Warm single-token inference completed in < 2.0s.")
            return True
        else:
            log_fail(f"Warm ping failed with HTTP {ping_resp.status_code}.")
            return False
    except requests.exceptions.Timeout:
        log_fail("Warm inference exceeded 2.0s SLA! GPU inference throughput compromised.")
        return False
    except Exception as e:
        log_fail(f"Warm inference verification failed: {e}")
        return False


# ----------------------------------------------------------------------
# 3. Docker Daemon Socket & Security Isolation (COMP-05)
# ----------------------------------------------------------------------
def check_docker_environment() -> bool:
    log_step("Docker Daemon Socket & Sandbox Isolation (COMP-05)")

    if not shutil.which("docker"):
        log_fail("Docker executable not found on PATH.")
        return False

    # Security flags derived directly from COMP-05 invariants
    test_cmd = [
        "docker", "run", "--rm",
        "--network", "none",
        "--memory", "256m",
        "--memory-swap", "256m",
        "--cpus", "1.0",
        "--read-only",
        "--tmpfs", "/tmp:rw,size=16m",
        "python:3.11-slim",
        "python", "-c",
        "import sys, os; sys.stdout.write('ISOLATION_OK') if os.path.exists('/tmp') else sys.exit(1)",
    ]

    try:
        proc = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
        if proc.returncode == 0 and "ISOLATION_OK" in proc.stdout:
            log_pass("Docker sandbox booted with full security flags (network=none, read-only root, 256MB cap, tmpfs).")
            return True
        else:
            log_fail(f"Docker security container execution failed (exit code {proc.returncode}).")
            if proc.stderr:
                print(f"  {CLR_RED}Stderr output:{CLR_RESET} {proc.stderr.strip()}")
            return False
    except subprocess.TimeoutExpired:
        log_fail("Docker command timed out after 10s. Daemon may be frozen.")
        return False
    except PermissionError:
        log_fail("Permission denied accessing Docker socket. Is your user in the 'docker' group? Run: sudo usermod -aG docker $USER")
        return False
    except Exception as e:
        log_fail(f"Unexpected error validating Docker: {e}")
        return False


# ----------------------------------------------------------------------
# Main Orchestrator
# ----------------------------------------------------------------------
def main() -> int:
    print(f"{CLR_BLUE}======================================================{CLR_RESET}")
    print(f"{CLR_BLUE}   ENTERPRISE AGENT: PHASE 0 ENVIRONMENT VALIDATION    {CLR_RESET}")
    print(f"{CLR_BLUE}======================================================{CLR_RESET}")

    gpu_ok = check_gpu_environment()
    ollama_ok = check_ollama_environment()
    docker_ok = check_docker_environment()

    print(f"\n{CLR_BLUE}=== SUMMARY GATE RESULTS ==={CLR_RESET}")
    print(f"  1. Hardware & VRAM Headroom:   {'✔ PASS' if gpu_ok else '✖ FAIL'}")
    print(f"  2. Ollama & Local Models:       {'✔ PASS' if ollama_ok else '✖ FAIL'}")
    print(f"  3. Docker Sandbox Constraints: {'✔ PASS' if docker_ok else '✖ FAIL'}")

    if gpu_ok and ollama_ok and docker_ok:
        print(f"\n{CLR_GREEN}>>> SUCCESS: Phase 0 prerequisites verified. Proceed to Phase 1.{CLR_RESET}\n")
        return 0
    else:
        print(f"\n{CLR_RED}>>> REJECTED: Environment fails production prerequisites. Rectify issues above.{CLR_RESET}\n")
        return 1


if __name__ == "__main__":
    sys.exit(main())
