"""MinIO RGB video frame sampling for annotation VLM jobs."""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import EpisodeInventory, EpisodeObject, ListRecord
from app.services.minio_client import get_minio_service

logger = logging.getLogger(__name__)

FRAME_PIXEL_SAMPLER_VERSION = 'minio-rgb-ffmpeg-v1'
PREFERRED_CAMERA_SUFFIXES = (
    'cam_top.mp4',
    'cam_left_wrist.mp4',
    'cam_right_wrist.mp4',
)


def _ffmpeg_bin() -> str | None:
    """Prefer static imageio-ffmpeg binary (no apt), then PATH ffmpeg."""
    try:
        import imageio_ffmpeg

        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    except Exception:
        pass
    return shutil.which('ffmpeg')


def _ffprobe_bin() -> str | None:
    path = shutil.which('ffprobe')
    if path:
        return path
    # imageio-ffmpeg ships ffmpeg only; duration probe is optional.
    return None


def resolve_rgb_video(db: Session, episode_id: str) -> tuple[str, str] | None:
    """Return (bucket, object_key) for a preferred RGB camera video, if present."""
    inventory = (
        db.query(EpisodeInventory)
        .filter(EpisodeInventory.ingested_episode_id == episode_id)
        .first()
    )
    if inventory is None:
        return None
    list_record = db.query(ListRecord).filter(ListRecord.id == inventory.list_id).first()
    if list_record is None or not list_record.bucket:
        return None
    rows = (
        db.query(EpisodeObject)
        .filter(
            EpisodeObject.episode_inventory_id == inventory.id,
            EpisodeObject.source_status != 'missing',
            EpisodeObject.object_key.like('%.mp4'),
        )
        .order_by(EpisodeObject.object_key.asc())
        .all()
    )
    if not rows:
        return None
    preferred: EpisodeObject | None = None
    for suffix in PREFERRED_CAMERA_SUFFIXES:
        for row in rows:
            key = row.object_key or ''
            if key.endswith(suffix) and 'depth' not in key.lower() and 'colormap' not in key.lower():
                preferred = row
                break
        if preferred is not None:
            break
    if preferred is None:
        for row in rows:
            key = (row.object_key or '').lower()
            if 'depth' in key or 'colormap' in key:
                continue
            if row.object_role == 'camera_rgb_video' or key.endswith('.mp4'):
                preferred = row
                break
    if preferred is None:
        return None
    return list_record.bucket, preferred.object_key


def sample_rgb_frames_b64(
    *,
    bucket: str,
    object_key: str,
    sample_steps: list[int],
    frame_count: int,
    duration_sec: float | None = None,
    max_width: int = 512,
    jpeg_quality: int = 4,
) -> list[dict]:
    """Download MP4 from MinIO and extract JPEG frames at sample_steps via ffmpeg.

    Returns list of {step, camera, mime, b64, bytes}.
    Empty list on hard failure (caller may continue text-only).
    """
    if not sample_steps:
        return []
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        logger.warning('ffmpeg not available; skip media sampling')
        return []
    minio = get_minio_service()
    tmp_dir = tempfile.mkdtemp(prefix='ann-vlm-')
    video_path = Path(tmp_dir) / 'source.mp4'
    try:
        response = minio.get_object(bucket, object_key)
        try:
            with open(video_path, 'wb') as fh:
                for chunk in response.stream(1024 * 1024):
                    fh.write(chunk)
        finally:
            response.close()
            response.release_conn()
        if not video_path.exists() or video_path.stat().st_size < 64:
            return []

        probed = _probe_duration_seconds(video_path)
        effective_duration = probed if probed and probed > 0 else duration_sec
        frames: list[dict] = []
        camera = Path(object_key).name
        for step in sample_steps:
            ts = _step_to_timestamp(step, frame_count=frame_count, duration_sec=effective_duration)
            out_path = Path(tmp_dir) / f'step_{step:06d}.jpg'
            ok = _ffmpeg_extract_jpeg(
                ffmpeg=ffmpeg,
                video_path=video_path,
                timestamp_sec=ts,
                out_path=out_path,
                max_width=max_width,
                jpeg_quality=jpeg_quality,
            )
            if not ok or not out_path.exists():
                continue
            raw = out_path.read_bytes()
            if not raw:
                continue
            frames.append({
                'step': int(step),
                'camera': camera,
                'mime': 'image/jpeg',
                'b64': base64.b64encode(raw).decode('ascii'),
                'bytes': len(raw),
                'timestampSec': round(ts, 4),
            })
        return frames
    except Exception:
        logger.exception('sample_rgb_frames_b64 failed bucket=%s key=%s', bucket, object_key)
        return []
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _step_to_timestamp(step: int, *, frame_count: int, duration_sec: float | None) -> float:
    if duration_sec and duration_sec > 0 and frame_count and frame_count > 1:
        # Map inclusive step index into [0, duration).
        ratio = max(0.0, min(1.0, float(step) / float(frame_count - 1)))
        return max(0.0, min(duration_sec - 0.001, ratio * duration_sec))
    if duration_sec and duration_sec > 0 and frame_count and frame_count > 0:
        fps = frame_count / duration_sec
        return max(0.0, min(duration_sec - 0.001, step / max(fps, 1e-6)))
    # Fallback assume ~10 FPS when metadata unavailable.
    return max(0.0, float(step) / 10.0)


def _probe_duration_seconds(video_path: Path) -> float | None:
    ffprobe = _ffprobe_bin()
    if ffprobe:
        try:
            proc = subprocess.run(
                [
                    ffprobe,
                    '-v', 'error',
                    '-show_entries', 'format=duration',
                    '-of', 'default=noprint_wrappers=1:nokey=1',
                    str(video_path),
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if proc.returncode == 0 and (proc.stdout or '').strip():
                return float(proc.stdout.strip())
        except Exception:
            pass
    # imageio-ffmpeg ships ffmpeg only; parse Duration from ffmpeg -i stderr.
    ffmpeg = _ffmpeg_bin()
    if not ffmpeg:
        return None
    try:
        proc = subprocess.run(
            [ffmpeg, '-hide_banner', '-i', str(video_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        import re

        match = re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)', proc.stderr or '')
        if not match:
            return None
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return None


def _ffmpeg_extract_jpeg(
    *,
    ffmpeg: str,
    video_path: Path,
    timestamp_sec: float,
    out_path: Path,
    max_width: int,
    jpeg_quality: int,
) -> bool:
    # -ss before -i for fast seek; single frame, downscale, moderate JPEG quality (2-31, lower=better).
    scale = f"scale='min({max_width},iw)':-2"
    cmd = [
        ffmpeg,
        '-hide_banner',
        '-loglevel', 'error',
        '-ss', f'{timestamp_sec:.3f}',
        '-i', str(video_path),
        '-frames:v', '1',
        '-vf', scale,
        '-q:v', str(max(2, min(31, jpeg_quality))),
        '-y',
        str(out_path),
    ]
    try:
        proc = subprocess.run(cmd, check=False, capture_output=True, timeout=60)
        return proc.returncode == 0 and out_path.exists()
    except Exception:
        logger.exception('ffmpeg extract failed ts=%s', timestamp_sec)
        return False
