#!/usr/bin/env python3
"""Real FastAPI /videos -> queue -> MoviePy -> MP4 -> HTTP download offline E2E.

No paid providers or fake pipeline stages. Run from repository root:
python scripts/api_offline_e2e.py --json-out .render-api-e2e/result.json
Exit codes: PASS=0, FAIL=1, ENVIRONMENT_BLOCKED=2.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def command(args: list[str], *, timeout=90) -> str:
    return subprocess.run(args, check=True, capture_output=True,
                          text=True, timeout=timeout).stdout


def run() -> dict:
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            return {"status": "ENVIRONMENT_BLOCKED", "reason": f"missing {program}"}

    with tempfile.TemporaryDirectory(prefix="mpt-api-e2e-") as temporary:
        # All runtime data and config are isolated from the source checkout.
        os.environ["MPT_HOME"] = str(Path(temporary) / "home")
        try:
            from fastapi.testclient import TestClient
            from app import asgi
            from app.config import config
            from app.models import const
            from app.models.schema import VideoAspect
            from app.services import state as sm
            from app.utils import utils
        except ImportError as exc:
            return {"status": "ENVIRONMENT_BLOCKED", "reason": f"missing dependency: {exc}"}

        if config.app.get("enable_redis") or not isinstance(sm.state, sm.MemoryState):
            return {"status": "ENVIRONMENT_BLOCKED", "reason": "in-memory task state required"}

        config.app["api_key"] = ""
        config.app["upload_post_enabled"] = False
        config.app["upload_post_api_key"] = ""
        config.app["video_codec"] = "libx264"
        config.app["video_clip_concurrency"] = 1

        # Render Free can OOM while allocating 1080p MoviePy frames. Only the
        # API acceptance process may opt into a reduced canvas; all real task,
        # queue, codec, audio, render and download paths remain unchanged.
        resolution = int(os.environ.get("MPT_API_E2E_RESOLUTION", "1080"))
        if resolution not in (480, 1080):
            raise ValueError("MPT_API_E2E_RESOLUTION must be 480 or 1080")
        if resolution != 1080:
            original_resolution = VideoAspect.to_resolution
            def smoke_resolution(self):
                if self == VideoAspect.square:
                    return resolution, resolution
                return original_resolution(self)
            VideoAspect.to_resolution = smoke_resolution
            print(f"MPT_API_E2E_TEST_ONLY_RESOLUTION={resolution}", flush=True)

        # Reproduce 1080p OOM with and without MoviePy enlargement. The source
        # is a genuine locally encoded video; no renderer is mocked.
        source_resolution = int(os.environ.get("MPT_API_E2E_SOURCE_RESOLUTION", "540"))
        if source_resolution not in (540, 1080):
            raise ValueError("MPT_API_E2E_SOURCE_RESOLUTION must be 540 or 1080")
        print(f"MPT_API_E2E_SOURCE_RESOLUTION={source_resolution}", flush=True)
        materials_dir = Path(utils.storage_dir("local_videos", create=True))
        material = materials_dir / "api-offline-clip.mp4"
        command([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
            "-threads", "1", "-f", "lavfi", "-i",
            f"color=c=blue:s={source_resolution}x{source_resolution}:r=30:d=4.5",
            "-an", "-c:v", "libx264",
            "-preset", "ultrafast", "-pix_fmt", "yuv420p", str(material)
        ], timeout=120)

        # User-provided script, local clip, built-in silent voice: no LLM,
        # stock-provider, TTS-provider, soundtrack-provider or remote H3 call.
        payload = {
            "video_subject": "Offline API acceptance",
            "video_script": "This offline rendering test uses no paid providers.",
            "video_aspect": "1:1",
            "video_source": "local",
            "video_materials": [{"provider": "local", "url": str(material), "duration": 4}],
            "voice_name": "no-voice",
            "subtitle_enabled": False,
            "bgm_type": "none",
            "bgm_volume": 0,
            "video_count": 1,
            "video_clip_duration": 5,
            "n_threads": 1,
        }
        checks = []
        started = time.monotonic()
        with TestClient(asgi.app) as client:
            response = client.post("/api/v1/videos", json=payload)
            if response.status_code != 200 or response.json().get("status") != 200:
                raise AssertionError(f"POST /videos {response.status_code}: {response.text[:500]}")
            task_id = response.json()["data"]["task_id"]
            checks.append("real POST /api/v1/videos creates task")

            state = {}
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline:
                polled = client.get(f"/api/v1/tasks/{task_id}")
                if polled.status_code != 200:
                    raise AssertionError(f"GET /tasks/{task_id} {polled.status_code}: {polled.text[:500]}")
                state = polled.json()["data"]
                if state.get("state") in (const.TASK_STATE_COMPLETE, const.TASK_STATE_FAILED):
                    break
                time.sleep(0.65)
            else:
                raise AssertionError(f"task timed out: {state}")
            if state["state"] != const.TASK_STATE_COMPLETE:
                raise AssertionError(f"task failed at {state.get('failed_stage')}: {state.get('error')}")
            if state.get("progress") != 100 or len(state.get("videos") or []) != 1:
                raise AssertionError(f"unexpected task result: {state}")
            checks.append("real GET /api/v1/tasks/{id} reports completed 100%")

            output = Path(utils.task_dir(task_id)) / "final-1.mp4"
            if not output.is_file() or output.stat().st_size <= 1000:
                raise AssertionError("output file missing/empty")
            info = json.loads(command([
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=codec_type,width,height", "-of", "json", str(output)
            ]))
            duration = float(info["format"]["duration"])
            streams = info["streams"]
            if not 2.5 <= duration <= 5.0:
                raise AssertionError(f"unexpected MP4 duration {duration}")
            if not any(s.get("codec_type") == "video" and s.get("width") == resolution
                       and s.get("height") == resolution for s in streams):
                raise AssertionError(f"missing {resolution}x{resolution} video stream: {streams}")
            if not any(s.get("codec_type") == "audio" for s in streams):
                raise AssertionError("missing MP4 audio stream")
            checks.append(f"real MP4 has {resolution}x{resolution} video and audio (production resolution only if 1080)")

            downloaded = client.get(f"/api/v1/download/{task_id}/final-1.mp4")
            if downloaded.status_code != 200 or downloaded.content[4:8] != b"ftyp":
                raise AssertionError(f"download failed: {downloaded.status_code}")
            if len(downloaded.content) != output.stat().st_size:
                raise AssertionError("HTTP payload length differs from output file")
            checks.append("real GET /api/v1/download/{id}/final-1.mp4 matches output")

        return {
            "status": "PASS", "scope": "real-fastapi-local-source-no-paid-provider",
            "checks": checks, "duration_seconds": duration, "width": resolution,
            "production_resolution_tested": resolution == 1080,
            "source_resolution": source_resolution,
            "height": resolution, "output_bytes": output.stat().st_size,
            "elapsed_seconds": round(time.monotonic() - started, 2)
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    options = parser.parse_args()
    try:
        result = run()
    except Exception as exc:
        result = {"status": "FAIL", "scope": "real-fastapi-local-source-no-paid-provider",
                  "reason": f"{type(exc).__name__}: {exc}"}
    print("MPT_API_OFFLINE_E2E_RESULT=" + json.dumps(result, ensure_ascii=False), flush=True)
    if options.json_out:
        options.json_out.parent.mkdir(parents=True, exist_ok=True)
        options.json_out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "ENVIRONMENT_BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
