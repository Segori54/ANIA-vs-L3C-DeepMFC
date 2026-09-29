"""Phase 1: hardware inventory and a real CUDA training/resume acceptance test."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter


def memory_bytes():
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ("total_phys", "avail_phys", "total_page", "avail_page", "total_virtual", "avail_virtual", "extended")]
        status = MemoryStatus()
        status.length = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total_phys
    elif hasattr(os, "sysconf"):
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return None


def inventory(output):
    import torch
    disk = shutil.disk_usage(output)
    result = {
        "utc": datetime.now(timezone.utc).isoformat(), "platform": platform.platform(),
        "python": sys.version, "executable": sys.executable,
        "processor": platform.processor(), "cpu_count": os.cpu_count(),
        "ram_bytes": memory_bytes(), "disk_free_bytes": disk.free,
        "torch": str(torch.__version__), "torch_cuda": torch.version.cuda,
        "cudnn": torch.backends.cudnn.version(), "cuda_available": torch.cuda.is_available(),
        "gpus": [],
    }
    if shutil.which("nvidia-smi"):
        result["nvidia_smi"] = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=20).stdout.strip()
    for index in range(torch.cuda.device_count()):
        prop = torch.cuda.get_device_properties(index)
        result["gpus"].append({"name": prop.name, "vram_bytes": prop.total_memory,
                               "capability": list(torch.cuda.get_device_capability(index))})
    return result


def smoke(output, device_name="cuda", steps=80):
    # Set before initializing CUDA; useful for deterministic linear algebra.
    os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    import torch
    from torch import nn
    from .checkpoint import save_checkpoint, load_checkpoint
    if steps < 4:
        raise ValueError("At least four steps are required")
    if device_name == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for the GPU gate; no silent CPU fallback")
    device = torch.device(device_name)
    torch.set_num_threads(2)
    torch.use_deterministic_algorithms(True)
    torch.manual_seed(20260929)
    if device.type == "cuda":
        torch.cuda.manual_seed_all(20260929)
        torch.cuda.reset_peak_memory_stats()
    model = nn.Sequential(nn.Linear(32, 64), nn.Tanh(), nn.Linear(64, 8)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    x = torch.randn(64, 32, device=device)
    target = x[:, :8] * 0.4
    initial = float((model(x) - target).square().mean().detach())
    config = {"purpose": "hardware_smoke_not_afc", "steps": steps}
    losses = []
    start = perf_counter()

    def update(net, opt):
        # Consume RNG on every step so the resume test checks RNG restoration too.
        jitter = 0.005 * torch.randn_like(x)
        opt.zero_grad(set_to_none=True)
        loss = (net(x + jitter) - target).square().mean()
        if not torch.isfinite(loss):
            raise RuntimeError("Non-finite loss")
        loss.backward()
        if any(p.grad is not None and not torch.isfinite(p.grad).all() for p in net.parameters()):
            raise RuntimeError("Non-finite gradients")
        opt.step()
        return float(loss.detach())

    halfway = steps // 2
    for _ in range(halfway):
        losses.append(update(model, optimizer))
    checkpoint = Path(output) / "resume_checkpoint.pt"
    save_checkpoint(checkpoint, model, optimizer, step=halfway, config=config)
    for _ in range(halfway, steps):
        losses.append(update(model, optimizer))
    expected = {key: value.detach().clone() for key, value in model.state_dict().items()}
    resumed = nn.Sequential(nn.Linear(32, 64), nn.Tanh(), nn.Linear(64, 8)).to(device)
    resumed_optimizer = torch.optim.Adam(resumed.parameters(), lr=0.01)
    loaded = load_checkpoint(checkpoint, resumed, resumed_optimizer, expected_config=config)
    for _ in range(loaded["step"], steps):
        update(resumed, resumed_optimizer)
    maximum_error = max(float((expected[key] - value).abs().max())
                        for key, value in resumed.state_dict().items())
    final = float((resumed(x) - target).square().mean().detach())
    if device.type == "cuda":
        torch.cuda.synchronize()
    passed = final < initial * 0.25 and maximum_error <= 1e-6
    result = {
        "passed": passed, "scope": "hardware_training_and_resume_only_not_afc",
        "device": str(next(resumed.parameters()).device), "steps": steps,
        "initial_loss": initial, "final_loss": final,
        "resume_max_parameter_error": maximum_error,
        "elapsed_seconds": perf_counter() - start,
        "peak_vram_bytes": torch.cuda.max_memory_allocated() if device.type == "cuda" else None,
        "losses": losses,
    }
    (Path(output) / "smoke.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not passed:
        raise RuntimeError("Training/resume acceptance test failed; see smoke.json")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs/training/phase1")
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    facts = inventory(output)
    (output / "environment.json").write_text(json.dumps(facts, indent=2), encoding="utf-8")
    frozen = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True, check=True)
    (output / "requirements-resolved.txt").write_text(frozen.stdout, encoding="utf-8")
    print(json.dumps(facts, indent=2))
    if args.smoke:
        print(json.dumps(smoke(output, args.device), indent=2))


if __name__ == "__main__":
    main()
