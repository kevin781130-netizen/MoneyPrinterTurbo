#!/usr/bin/env python3
"""No-Docker/no-API smoke: local FFmpeg MP4, audio, SRT, cache, and fail-closed.

Run: python scripts/offline_smoke.py --json-out evidence/mpt-offline-smoke.json
Scope excludes /videos HTTP, LLM/TTS providers, and burned-in subtitles.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import wave


def cmd(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=90).stdout


def tone(path, frequency):
    with wave.open(str(path), "wb") as sink:
        sink.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        sink.writeframes(b"".join(struct.pack("<h", int(4500 * math.sin(
            2 * math.pi * frequency * i / 48000))) for i in range(31200)))


def smoke():
    if not __debug__:
        return {"status": "ENVIRONMENT_BLOCKED", "reason": "run without Python -O; assertions must remain enabled"}
    for program in ("ffmpeg", "ffprobe"):
        if not shutil.which(program):
            return {"status": "ENVIRONMENT_BLOCKED", "reason": f"missing {program}"}
    if "libx264" not in cmd("ffmpeg", "-hide_banner", "-encoders"):
        return {"status": "ENVIRONMENT_BLOCKED", "reason": "libx264 encoder not found"}
    try:
        from app.services.video_project import VideoProject
        from app.utils.subtitle_writer import write_subtitle_file
    except ImportError as exc:
        return {"status": "ENVIRONMENT_BLOCKED", "reason": f"missing runtime dependency: {exc}"}

    checks = []
    with tempfile.TemporaryDirectory(prefix="mpt-offline-") as directory:
        root = Path(directory)
        for color in ("red", "blue"):
            cmd("ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                "-threads", "1", "-f", "lavfi", "-i",
                f"color=c={color}:s=160x90:r=10:d=0.65", "-an", "-c:v",
                "libx264", "-pix_fmt", "yuv420p", str(root / f"{color}.mp4"))
        tone(root / "voice.wav", 440)
        tone(root / "music.wav", 220)
        project = VideoProject(root / "project")
        revision = project.create_revision({
            "project_id": "offline_smoke", "settings": {"width": 160, "height": 90, "fps": 10},
            "scenes": [{"id": name, "footage": f"{color}.mp4", "audio": "voice.wav",
                        "narration": name} for name, color in (("opening", "red"), ("closing", "blue"))],
            "bgm": "music.wav",
        }, relative_to=root)
        report = project.render(stage_timeout=60)
        target = Path(report["export"]["path"])
        assert report["state"] == "succeeded" and report["promoted"]
        assert target.stat().st_size > 1024
        assert hashlib.sha256(target.read_bytes()).hexdigest() == report["export"]["sha256"]
        checks.append("native MP4 render and checksum")
        media = json.loads(cmd("ffprobe", "-v", "error", "-show_entries",
                               "format=duration:stream=codec_type,width,height",
                               "-of", "json", str(target)))
        streams = media["streams"]
        assert len([s for s in streams if s["codec_type"] == "audio"]) == 1
        assert len([s for s in streams if s["codec_type"] == "video"
                    and s["width"] == 160 and s["height"] == 90]) == 1
        assert 1.0 < float(media["format"]["duration"]) < 1.7
        checks.append("video/audio streams and duration")
        assert not any(x["action"] == "build" for x in project.plan(revision["revision_id"]))
        checks.append("render stage cache")
        srt_path = root / "captions.srt"
        captions = "1\n00:00:00,000 --> 00:00:00,650\nHello\n\n"
        assert write_subtitle_file(str(srt_path), captions)
        assert not write_subtitle_file(str(srt_path), "incomplete")
        assert srt_path.read_text(encoding="utf-8") == captions
        checks.append("atomic SRT publish and invalid-cue rejection")
        (root / "bad.mp4").write_bytes(b"not a video")
        invalid = VideoProject(root / "invalid-project")
        invalid.create_revision({"project_id": "invalid_smoke", "scenes": [
            {"id": "bad", "footage": "bad.mp4", "audio": "voice.wav"}
        ]}, relative_to=root)
        try:
            invalid.render(stage_timeout=60)
        except Exception:
            pass
        else:
            raise AssertionError("corrupt video unexpectedly rendered")
        failed = invalid.status()
        assert failed["state"] == "failed" and failed["failed_stage"]
        assert invalid.metadata()["last_successful_export"] is None
        checks.append("corrupt input fails closed with persisted failure state")
    return {"status": "PASS", "scope": "local-renderer-and-srt-only", "checks": checks}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json-out", type=Path)
    args = parser.parse_args()
    try:
        result = smoke()
    except Exception as exc:
        result = {"status": "FAIL", "reason": f"{type(exc).__name__}: {exc}"}
    report = json.dumps(result, ensure_ascii=False, indent=2)
    print(report)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(report + "\n", encoding="utf-8")
    return {"PASS": 0, "FAIL": 1, "ENVIRONMENT_BLOCKED": 2}[result["status"]]


if __name__ == "__main__":
    sys.exit(main())
