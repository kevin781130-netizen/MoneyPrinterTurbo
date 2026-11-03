#!/usr/bin/env python3
"""Read-only preflight for the Windows 11 low-memory acceptance gate.

Run with the SAME Python executable you intend to use for acceptance:
    .venv\\Scripts\\python.exe scripts/check_windows_prereqs.py --json-out evidence/prerequisites.json

No downloads, imports of application modules, package changes, or network calls.
Exit 0 = prerequisites PASS, exit 2 = ENVIRONMENT_BLOCKED.
"""
from __future__ import annotations

import argparse
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_PYTHON = (3, 11)
EXTRA_REQUIREMENTS = ("httpx==0.28.1", "pillow>=13.0.0,<14")


def _check_binary(name: str, arguments: list[str], token: str | None = None) -> dict:
    executable = shutil.which(name)
    if not executable:
        return {"status": "BLOCKED", "reason": f"{name} not on PATH"}
    try:
        result = subprocess.run(
            [executable, *arguments], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=15, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "BLOCKED", "reason": f"{name}: {type(exc).__name__}"}
    if result.returncode:
        return {"status": "BLOCKED", "reason": f"{name} exited {result.returncode}"}
    if token and token not in (result.stdout + result.stderr):
        return {"status": "BLOCKED", "reason": f"{name} missing {token} encoder"}
    return {"status": "PASS", "path": executable}


def _dependencies() -> dict:
    try:
        from packaging.requirements import Requirement
    except ImportError:
        return {
            "status": "BLOCKED",
            "missing": ["packaging"],
            "incompatible": [],
            "reason": "packaging is required to validate installed versions",
        }

    try:
        with (ROOT / "pyproject.toml").open("rb") as source:
            requirements = tomllib.load(source)["project"]["dependencies"]
    except (OSError, ValueError, KeyError, tomllib.TOMLDecodeError) as exc:
        return {
            "status": "BLOCKED", "missing": [], "incompatible": [],
            "reason": f"Cannot read project dependency contract: {type(exc).__name__}",
        }

    # Pillow's security override replaces MoviePy's old Pillow cap; httpx is
    # needed by FastAPI TestClient and was pinned in verified Render E2E.
    requirements = list(requirements) + list(EXTRA_REQUIREMENTS)
    missing = []
    incompatible = []
    checked = 0
    for text in requirements:
        item = Requirement(text)
        if item.marker is not None and not item.marker.evaluate():
            continue
        try:
            installed = metadata.version(item.name)
        except metadata.PackageNotFoundError:
            missing.append(item.name)
            continue
        checked += 1
        if item.specifier and not item.specifier.contains(installed, prereleases=True):
            incompatible.append({
                "package": item.name,
                "required": str(item.specifier),
                "installed": installed,
            })

    return {
        "status": "BLOCKED" if missing or incompatible else "PASS",
        "checked": checked,
        "missing": sorted(set(missing), key=str.casefold),
        "incompatible": incompatible,
    }


def check() -> dict:
    platform_ok = os.name == "nt" and platform.system() == "Windows"
    python_ok = sys.version_info[:2] == REQUIRED_PYTHON
    bits_ok = sys.maxsize > 2 ** 32
    tools = {
        "ffmpeg": _check_binary("ffmpeg", ["-hide_banner", "-encoders"], "libx264"),
        "ffprobe": _check_binary("ffprobe", ["-version"]),
    }
    deps = _dependencies()
    blockers = []
    if not platform_ok:
        blockers.append("Run this gate on Windows 11 (not Linux/WSL).")
    if not python_ok:
        blockers.append("Use a 64-bit Python 3.11 interpreter, matching .python-version.")
    if not bits_ok:
        blockers.append("32-bit Python is not supported by this acceptance gate.")
    for name, result in tools.items():
        if result["status"] != "PASS":
            blockers.append(result["reason"])
    if deps["status"] != "PASS":
        blockers.append("Python dependencies are missing or differ from pyproject.toml/security override.")

    return {
        "gate": "MPT_WINDOWS_PREREQUISITES",
        "status": "ENVIRONMENT_BLOCKED" if blockers else "PASS",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "version_ok": python_ok,
            "bits_64": bits_ok,
        },
        "native_windows": platform_ok,
        "binaries": tools,
        "dependencies": deps,
        "blockers": blockers,
        "repair_hint": (
            "From the repository root with uv installed: "
            "uv sync --frozen --python 3.11; "
            "uv pip install --python .venv\\Scripts\\python.exe httpx==0.28.1; "
            "then run acceptance with -Python .\\.venv\\Scripts\\python.exe. "
            "Ensure FFmpeg and FFprobe with libx264 are on PATH. "
            "These are instructions, not commands executed by this preflight."
            if blockers else None
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    options = parser.parse_args()
    try:
        result = check()
    except Exception as exc:
        result = {
            "gate": "MPT_WINDOWS_PREREQUISITES", "status": "ENVIRONMENT_BLOCKED",
            "blockers": [f"Preflight could not complete: {type(exc).__name__}: {exc}"],
        }
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(payload + "\n", encoding="utf-8")
    print("MPT_WINDOWS_PREREQUISITES_RESULT=" + json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
