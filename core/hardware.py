import platform
import os
import subprocess
import shutil


def get_total_ram_gb():
    page_size = os.sysconf("SC_PAGE_SIZE")
    physical_pages = os.sysconf("SC_PHYS_PAGES")
    total_bytes = page_size * physical_pages
    return total_bytes / (1024 ** 3)


def get_cpu_model():
    try:
        with open("/proc/cpuinfo", "r") as f:
            for line in f:
                if line.startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except FileNotFoundError:
        pass

    return platform.processor() or "Unknown"


def get_nvidia_gpus():
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        gpus = []

        for line in result.stdout.strip().splitlines():
            name, total_mb, free_mb = [
                item.strip() for item in line.split(",", 2)
            ]

            gpus.append({
                "vendor": "nvidia",
                "name": name,
                "vram_total_gb": float(total_mb) / 1024,
                "vram_free_gb": float(free_mb) / 1024
            })

        return gpus

    except (FileNotFoundError, subprocess.CalledProcessError):
        return []


def get_storage(path=None):
    if path is None:
        path = os.environ.get("AI_DATA_ROOT", "/workspace")

    total, used, free = shutil.disk_usage(path)

    return {
        "path": path,
        "total_gb": total / (1024 ** 3),
        "used_gb": used / (1024 ** 3),
        "free_gb": free / (1024 ** 3)
    }


def inspect_hardware():
    return {
        "operating_system": platform.system(),
        "architecture": platform.machine(),
        "cpu_model": get_cpu_model(),
        "cpu_cores": os.cpu_count(),
        "ram_total_gb": get_total_ram_gb(),
        "gpus": get_nvidia_gpus(),
        "storage": get_storage()
    }
