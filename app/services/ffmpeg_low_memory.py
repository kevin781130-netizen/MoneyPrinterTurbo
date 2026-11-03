"""Opt-in, low-RAM FFmpeg path for one untransformed source and dry voiceover.

This intentionally does NOT support transitions, playback speed, subtitle burn-in,
multi-clip composition or background music. Callers must enforce those guards.
Default product behavior remains MoviePy unless explicitly enabled.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from loguru import logger
from app.utils import utils

_TIMEOUT_SECONDS = 180


def _ffmpeg() -> str:
    result = utils.get_ffmpeg_binary()
    if not result:
        raise RuntimeError("FFmpeg is unavailable for low-memory renderer")
    return result


def _ffprobe() -> str:
    binary = _ffmpeg()
    sibling = Path(binary).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    if sibling.is_file():
        return str(sibling)
    found = shutil.which("ffprobe")
    if not found:
        raise RuntimeError("FFprobe is unavailable for low-memory renderer")
    return found


def _run(args: list[str], description: str) -> None:
    try:
        result = subprocess.run(
            args, check=False, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"{description} failed: {type(exc).__name__}") from exc
    if result.returncode:
        # FFmpeg output is untrusted; only a bounded diagnostic is emitted.
        raise RuntimeError(
            f"{description} failed with exit {result.returncode}: "
            f"{(result.stderr or '')[-1200:]}"
        )


def _probe(path: str) -> dict:
    result = subprocess.run(
        [_ffprobe(), "-v", "error", "-show_entries",
         "format=duration:stream=codec_type,width,height", "-of", "json", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True, timeout=15,
    )
    return json.loads(result.stdout)


def source_duration(path: str) -> float:
    data = _probe(path)
    value = float(data["format"]["duration"])
    if not math.isfinite(value) or value <= 0:
        raise ValueError("source has invalid duration")
    if not any(stream.get("codec_type") == "video" for stream in data.get("streams", [])):
        raise ValueError("source has no video stream")
    return value


def _atomic_render(output_file: str, argv: list[str], description: str) -> None:
    output = Path(output_file)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(
        prefix=f".{output.stem}.lowmem-", suffix=".mp4", dir=str(output.parent)
    )
    os.close(fd)
    try:
        # FFmpeg must write the temporary file, never the downloadable final path.
        _run([*argv, "-y", temporary], description)
        if os.path.getsize(temporary) <= 1024:
            raise RuntimeError(f"{description} generated an empty MP4")
        data = _probe(temporary)
        if not any(s.get("codec_type") == "video" for s in data.get("streams", [])):
            raise RuntimeError(f"{description} output has no video stream")
        os.replace(temporary, output_file)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def combine_one_source(
    *, source: str, output_file: str, duration: float, width: int,
    height: int, fit_mode: str
) -> str:
    """Render 30-fps BT.709 video using bounded-memory FFmpeg streaming."""
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("low-memory renderer requires positive even dimensions")
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("invalid output duration")
    if fit_mode == "cover":
        resizing = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase:"
            "flags=lanczos,"
            f"crop={width}:{height},"
        )
    elif fit_mode == "contain":
        resizing = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease:"
            "flags=lanczos,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black,"
        )
    else:
        raise ValueError(f"unsupported fit_mode {fit_mode!r}")

    vf = (
        resizing + "setsar=1,format=yuv420p,"
        "setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv"
    )
    logger.info(
        f"opt-in low-memory FFmpeg encode: {width}x{height}, "
        f"duration={duration:.2f}s, fit={fit_mode}"
    )
    command = [
        _ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-filter_threads", "1", "-threads", "1", "-i", source,
        "-t", f"{duration:.6f}", "-vf", vf,
        "-r", "30", "-an", "-c:v", "libx264", "-preset", "veryfast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
    ]
    _atomic_render(output_file, command, "low-memory scene encode")
    return output_file


def mux_dry_voiceover(
    *, input_video: str, input_audio: str, output_file: str,
    voice_volume: float, audio_bitrate: str = "192k"
) -> None:
    """Mux a narration without opening uncompressed 1080p frames in Python."""
    volume = float(voice_volume)
    if not math.isfinite(volume) or volume < 0:
        raise ValueError("invalid voice volume")
    command = [
        _ffmpeg(), "-hide_banner", "-nostdin", "-loglevel", "error",
        "-threads", "1", "-i", input_video, "-i", input_audio,
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
        "-c:a", "aac", "-b:a", audio_bitrate,
    ]
    if volume != 1:
        command += ["-af", f"volume={volume:.6f}"]
    command += ["-shortest", "-movflags", "+faststart"]
    _atomic_render(output_file, command, "low-memory narration mux")
    data = _probe(output_file)
    if not any(s.get("codec_type") == "audio" for s in data.get("streams", [])):
        try:
            os.unlink(output_file)
        except FileNotFoundError:
            pass
        raise RuntimeError("low-memory output has no narration audio stream")
