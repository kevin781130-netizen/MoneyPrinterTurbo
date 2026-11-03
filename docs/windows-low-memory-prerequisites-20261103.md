# Windows 11 pre-device gate — fail before rendering

**Current Windows status: NOT_RUN.** This document does not assert a Windows test passed.

The gate is scoped to **single local video, no transitions, no burned captions, no BGM, 1080×1080 output** via the explicitly enabled low-memory FFmpeg path. It does not test full paid AI generation or long-form workflows.

## 1. Existing checkout, read-only preflight

Run from the repo root in **Windows PowerShell** (the branch must be `dev/mpt-slim-20261103`):

```powershell
python scripts/check_windows_prereqs.py --json-out evidence/mpt-low-memory-prerequisites.json
```

Exit **0** means the environment's prerequisites are present, **2** means `ENVIRONMENT_BLOCKED`. The report gives the exact missing/incompatible Python distribution names, plus binary/version blockers. It does not install, download or change packages. It requires:

- Native 64-bit Windows and **Python 3.11** (not WSL), in the exact interpreter that will run the tests
- FFmpeg **with libx264**, and FFprobe, both available on PATH
- `pyproject.toml` direct dependencies at their declared versions; **Pillow >=13,<14** (security override) and **httpx 0.28.1** (verified TestClient version)
- Git and the target branch are checked separately by the full PowerShell gate

## 2. Optional dependency repair only if reported as blocked

If you have `uv` installed, from the same repository root:

```powershell
uv sync --frozen --python 3.11
uv pip install --python .venv\Scripts\python.exe httpx==0.28.1
.\.venv\Scripts\python.exe scripts/check_windows_prereqs.py --json-out evidence/mpt-low-memory-prerequisites.json
```

These commands **are not run automatically** and do not require Docker. If `ffmpeg` or `ffprobe` are missing, provision trusted Windows binaries on PATH before running the gate. Do not disable `libx264` validation to force a PASS.

## 3. Only after preflight PASS — one-command Windows acceptance

```powershell
powershell -NoProfile -File .\scripts\accept-low-memory-windows.ps1 -Python .\.venv\Scripts\python.exe
```

The entrypoint checks the branch, executes the same preflight first, then requires 9 regression tests PASS, 5 offline smoke checks PASS, and 4 real `/videos` HTTP checks with a **540→1080** local MP4. No paid providers, Docker, or GitHub Actions.

Evidence is written to `evidence/mpt-low-memory-prerequisites.json` and `evidence/mpt-low-memory-windows-gate.json`, with per-stage logs. A missing dependency returns **ENVIRONMENT_BLOCKED** rather than being misreported as a rendering defect.

**Do not merge to `main` or call Windows accepted** solely because earlier Render Linux runs passed; Windows is a separate gate.
