"""
Video upload / processing pipeline for "Sell your car" uploads.

Pipeline (sync portion, returns immediately after step 4):
    1. Stream uploaded bytes to a temporary file (≤100 MB).
    2. Run `ffprobe -show_format` → reject if duration > 60 s.
    3. Persist original to /opt/autobids/uploads/videos/<sha>/source.<ext>.
    4. Extract a poster frame (≈1 s in) → poster.jpg.
    5. Schedule background AV1 transcode (libsvtav1) → av1.mp4 → swap
       url on the auction doc when done.

The synchronous result is enough to render `<video poster=... src=...>`
in the listing page. The AV1 file is hot-swapped on the auction record
once encoded so future visitors get the smaller payload.

NOTE: ffmpeg/ffprobe must be installed on the host. Ansible role
`backend` installs them in `apt_packages`.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple

log = logging.getLogger(__name__)

# Max upload size + duration are enforced server-side. The client also
# checks these but a determined caller can bypass the client check.
MAX_VIDEO_BYTES = 100 * 1024 * 1024  # 100 MB
MAX_VIDEO_SECONDS = 60.0
ALLOWED_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".avi", ".mkv"}

# File-magic signatures (first ~16 bytes). MP4/MOV/M4V all share the
# ISO base media container — bytes 4-8 == "ftyp" plus a brand. WebM
# is the EBML magic. Each tuple is `(offset, byte-signature)`; any
# match is accepted.
_VIDEO_MAGIC = [
    (4, b"ftyp"),          # MP4 / MOV / M4V / 3GP (ISO BMFF)
    (0, b"\x1aE\xdf\xa3"),  # WebM / Matroska (EBML)
    (0, b"RIFF"),          # AVI (RIFF wrapper)
    (0, b"FLV\x01"),       # FLV (not in allowed exts but recognised)
]


def looks_like_video(path: str) -> bool:
    try:
        with open(path, "rb") as f:
            head = f.read(32)
    except OSError:
        return False
    for off, sig in _VIDEO_MAGIC:
        if head[off : off + len(sig)] == sig:
            return True
    return False

UPLOAD_DIR = os.path.abspath(os.environ.get("UPLOAD_DIR", "/opt/autobids/uploads"))
VIDEOS_DIR = os.path.join(UPLOAD_DIR, "videos")


def _ensure_dirs():
    os.makedirs(VIDEOS_DIR, exist_ok=True)


def probe_duration(path: str) -> Optional[float]:
    """Return the duration in seconds, or None if ffprobe fails."""
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                path,
            ],
            stderr=subprocess.STDOUT,
            timeout=15,
        )
        d = json.loads(out).get("format", {}).get("duration")
        return float(d) if d else None
    except Exception as e:  # noqa: BLE001
        log.warning("ffprobe failed for %s: %s", path, e)
        return None


def extract_poster(src_path: str, out_path: str) -> bool:
    """Extract a single still frame ~1 s into the video as JPEG. Returns
    True on success."""
    try:
        subprocess.check_call(
            [
                "ffmpeg", "-y",
                "-ss", "1",
                "-i", src_path,
                "-frames:v", "1",
                "-q:v", "3",
                "-vf", "scale='min(1280,iw)':-2",
                out_path,
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return os.path.exists(out_path)
    except Exception as e:  # noqa: BLE001
        log.warning("poster extraction failed for %s: %s", src_path, e)
        return False


async def transcode_to_av1(src_path: str, out_path: str) -> bool:
    """Background AV1 transcode using libsvtav1 (fast, GPL-friendly).

    Runs as `asyncio.create_subprocess_exec` so the event loop keeps
    serving requests during the long encode (~30-90 s for a 1-min
    1080p clip on modern CPU)."""
    cmd = [
        "ffmpeg", "-y",
        "-i", src_path,
        "-c:v", "libsvtav1",
        "-preset", "8",            # 0=slowest, 13=fastest. 8 is a sane default.
        "-crf", "32",              # 28-35 typical for web. Lower = better quality, larger file.
        "-c:a", "libopus",
        "-b:a", "96k",
        "-movflags", "+faststart",
        "-pix_fmt", "yuv420p",
        out_path,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            log.error("AV1 transcode timed out for %s", src_path)
            return False
        if proc.returncode != 0:
            log.error(
                "AV1 transcode failed for %s (rc=%s): %s",
                src_path, proc.returncode, (stderr or b"")[:400].decode(errors="replace"),
            )
            return False
        return os.path.exists(out_path)
    except Exception as e:  # noqa: BLE001
        log.exception("AV1 transcode crashed for %s: %s", src_path, e)
        return False


def save_upload_streamed(tmp_path: str, target_path: str) -> str:
    """Move `tmp_path` to `target_path`. Returns absolute target.

    Uses `shutil.move` (not `os.replace`) so the move works across
    filesystems / overlay mounts — `/tmp` and `/app/uploads` are
    typically on different mounts in container environments.
    """
    import shutil

    Path(target_path).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(tmp_path, target_path)
    return target_path


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def process_uploaded_video(tmp_path: str, original_filename: str) -> Tuple[dict, Optional[str]]:
    """Sync portion of the pipeline. Returns
        (metadata_dict, av1_target_path or None when transcode skipped).

    metadata_dict keys: video_url, video_poster_url, video_duration_seconds, sha.
    Raises ValueError on validation failure (caller maps to HTTP 400).
    """
    _ensure_dirs()
    ext = os.path.splitext(original_filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise ValueError(f"unsupported video extension: {ext or '<none>'}")

    # Magic-bytes check — guards against `.mp4` extension on a non-video
    # payload (PDF / EXE / JS bomb). ffprobe would also catch most of
    # these but the magic check is cheap and explicit.
    if not looks_like_video(tmp_path):
        raise ValueError("file does not look like a supported video container")

    duration = probe_duration(tmp_path)
    if duration is None:
        raise ValueError("could not read video duration (corrupt file?)")
    if duration > MAX_VIDEO_SECONDS:
        raise ValueError(
            f"video duration {duration:.1f}s exceeds {MAX_VIDEO_SECONDS:.0f}s limit"
        )

    sha = sha256_file(tmp_path)
    target_dir = os.path.join(VIDEOS_DIR, sha[:2], sha[2:4], sha)
    Path(target_dir).mkdir(parents=True, exist_ok=True)
    source_path = os.path.join(target_dir, f"source{ext}")
    poster_path = os.path.join(target_dir, "poster.jpg")
    av1_path = os.path.join(target_dir, "av1.mp4")

    save_upload_streamed(tmp_path, source_path)
    extract_poster(source_path, poster_path)

    # Public URLs — relative path under /api/uploads/ (served by FastAPI
    # static mount or img.autoandbid.bg/uploads/ in production).
    rel_src = f"/api/uploads/videos/{sha[:2]}/{sha[2:4]}/{sha}/source{ext}"
    rel_poster = f"/api/uploads/videos/{sha[:2]}/{sha[2:4]}/{sha}/poster.jpg" \
        if os.path.exists(poster_path) else None
    rel_av1 = f"/api/uploads/videos/{sha[:2]}/{sha[2:4]}/{sha}/av1.mp4"

    return (
        {
            "video_url": rel_src,
            "video_poster_url": rel_poster,
            "video_duration_seconds": round(duration, 2),
            "sha": sha,
            "av1_url_when_ready": rel_av1,
        },
        av1_path,
    )
