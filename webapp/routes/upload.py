# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Upload route - Handle FIT file upload and effort detection"""

import uuid
import logging
import tempfile
import time
import os
from collections import deque
from threading import Lock
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, File, UploadFile, HTTPException, Form, Request
from fastapi.responses import RedirectResponse
from dependencies import SessionsDep

from utils.effort_analyzer import (
    parse_fit, create_efforts, merge_extend, split_included, detect_sprints
)
from utils.analysis_config import EffortConfig, SprintConfig

from utils.metrics import calculate_ride_stats

logger = logging.getLogger(__name__)

# Upload directory for temporary FIT file storage
UPLOAD_DIR = Path(tempfile.gettempdir()) / "peffort_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Simple in-memory rate limiting per client IP.
# Keeps abuse under control without introducing external dependencies.
RATE_LIMIT_MAX_REQUESTS = 10
RATE_LIMIT_WINDOW_SECONDS = 60
TRUST_PROXY_HEADERS = os.getenv("UPLOAD_RATE_LIMIT_TRUST_PROXY_HEADERS", "false").strip().lower() in {"1", "true", "yes", "on"}

try:
    RATE_LIMIT_MAX_REQUESTS = max(1, int(os.getenv("UPLOAD_RATE_LIMIT_MAX_REQUESTS", str(RATE_LIMIT_MAX_REQUESTS))))
except ValueError:
    RATE_LIMIT_MAX_REQUESTS = 10

try:
    RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv("UPLOAD_RATE_LIMIT_WINDOW_SECONDS", str(RATE_LIMIT_WINDOW_SECONDS))))
except ValueError:
    RATE_LIMIT_WINDOW_SECONDS = 60

_upload_timestamps: Dict[str, deque] = {}
_upload_rate_lock = Lock()

router = APIRouter()


def setup_upload_router(sessions_dict: Dict[str, Any]):
    """Setup the upload router with shared sessions dictionary"""
    _ = sessions_dict


def _is_upload_rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    with _upload_rate_lock:
        queue = _upload_timestamps.get(client_ip)
        if queue is not None:
            # Prune expired timestamps.
            while queue and now - queue[0] > RATE_LIMIT_WINDOW_SECONDS:
                queue.popleft()
            # Remove idle entry to prevent unbounded dict growth.
            if not queue:
                del _upload_timestamps[client_ip]
                queue = None
        if queue is not None and len(queue) >= RATE_LIMIT_MAX_REQUESTS:
            return True
        if queue is None:
            queue = deque()
        queue.append(now)
        _upload_timestamps[client_ip] = queue
        return False


def _get_client_ip(request: Request) -> str:
    if TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            first_ip = forwarded.split(",")[0].strip()
            if first_ip:
                return first_ip

        real_ip = request.headers.get("x-real-ip", "").strip()
        if real_ip:
            return real_ip

    return request.client.host if request.client and request.client.host else "unknown"


@router.post("/upload")
async def upload_fit(
    request: Request,
    sessions: SessionsDep,
    file: UploadFile = File(...),
    cp: float = Form(250),
    weight: float = Form(60),
    window_sec: int = Form(60),
    min_cp_pct: float = Form(100),
    merge_pct: float = Form(15),
    trim_win: int = Form(10),
    trim_low: float = Form(85),
    extend_win: int = Form(15),
    extend_low: float = Form(80),
    sprint_min_power: int = Form(500),
    sprint_min_duration: int = Form(5),
    sprint_merge_gap: int = Form(3)
):
    """
    Handle FIT file upload, parse it, detect efforts, and redirect to inspection view.

    Args:
        file: Uploaded FIT file
        cp: Critical Power (W)
        weight: Athlete weight (kg)
        window_sec: Detection window (seconds)
        min_cp_pct: Minimum CP intensity (%)
        merge_pct: Merge tolerance (%)
        trim_win: Trim window (seconds)
        trim_low: Trim low threshold (%)
        extend_win: Extend window (seconds)
        extend_low: Extend low threshold (%)
        sprint_min_power: Sprint minimum power (W)
        sprint_min_duration: Sprint minimum duration (s)
        sprint_merge_gap: Sprint merge gap (s)

    Returns:
        RedirectResponse to dashboard with session_id
    """
    client_ip = _get_client_ip(request)
    if _is_upload_rate_limited(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many uploads. Please wait and try again."
        )

    # Validate file
    if not file.filename or not file.filename.lower().endswith('.fit'):
        raise HTTPException(
            status_code=400, detail="File must be a .fit file"
        )

    # Validate numeric parameters to prevent abuse
    if not (50 <= cp <= 600):
        raise HTTPException(
            status_code=400, detail="CP must be between 50 and 600 watts"
        )
    if not (30 <= weight <= 200):
        raise HTTPException(
            status_code=400, detail="Weight must be between 30 and 200 kg"
        )
    if not (10 <= window_sec <= 600):
        raise HTTPException(
            status_code=400,
            detail="Window seconds must be between 10 and 600"
        )
    if not (50 <= min_cp_pct <= 300):
        raise HTTPException(
            status_code=400,
            detail="Min CP % must be between 50 and 300"
        )
    # Additional parameter validation to prevent parameter-abuse DoS
    if not (0 <= merge_pct <= 50):
        raise HTTPException(
            status_code=400,
            detail="Merge % must be between 0 and 50"
        )
    if not (0 <= trim_win <= 120):
        raise HTTPException(
            status_code=400,
            detail="Trim window must be between 0 and 120 seconds"
        )
    if not (50 <= trim_low <= 100):
        raise HTTPException(
            status_code=400,
            detail="Trim low % must be between 50 and 100"
        )
    if not (0 <= extend_win <= 120):
        raise HTTPException(
            status_code=400,
            detail="Extend window must be between 0 and 120 seconds"
        )
    if not (50 <= extend_low <= 100):
        raise HTTPException(
            status_code=400,
            detail="Extend low % must be between 50 and 100"
        )
    if not (200 <= sprint_min_power <= 2000):
        raise HTTPException(
            status_code=400,
            detail="Sprint minimum power must be between 200 and 2000 watts"
        )
    if not (1 <= sprint_min_duration <= 120):
        raise HTTPException(
            status_code=400,
            detail="Sprint minimum duration must be between 1 and 120 seconds"
        )
    if not (0 <= sprint_merge_gap <= 60):
        raise HTTPException(
            status_code=400,
            detail="Sprint merge gap must be between 0 and 60 seconds"
        )

    # Generate secure session ID
    session_id = str(uuid.uuid4())

    # Save uploaded file with deterministic server-side name to avoid path tricks.
    file_path = UPLOAD_DIR / f"{session_id}.fit"
    try:
        # Validate file size (max 50MB for FIT files) while streaming to disk
        max_size = 50 * 1024 * 1024  # 50MB
        chunk_size = 1024 * 1024  # 1MB
        total_size = 0

        with open(file_path, 'wb') as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    # Remove partially written file before raising
                    f.close()
                    if file_path.exists():
                        file_path.unlink()
                    raise HTTPException(
                        status_code=400,
                        detail="File too large. Max size is 50MB"
                    )
                f.write(chunk)

        if total_size == 0:
            if file_path.exists():
                file_path.unlink()
            raise HTTPException(
                status_code=400,
                detail="File is empty"
            )
        logger.info(f"File saved: {file_path}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        # Clean up partial file on error
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=500, detail="Error saving file"
        )

    # Parse FIT file
    try:
        df = parse_fit(str(file_path))
        logger.info(f"FIT parsed: {len(df)} records")
    except Exception as e:
        logger.error(f"Error parsing FIT: {e}")
        raise HTTPException(
            status_code=400, detail="Error parsing FIT file"
        )
    finally:
        # Always attempt cleanup, including unexpected parser failures.
        if file_path.exists():
            file_path.unlink()

    # Create effort config with all parameters
    effort_config = EffortConfig(
        window_seconds=window_sec,
        min_effort_intensity_cp=min_cp_pct,
        merge_power_diff_percent=merge_pct,
        trim_window_seconds=trim_win,
        trim_low_percent=trim_low,
        extend_window_seconds=extend_win,
        extend_low_percent=extend_low
    )

    # Detect efforts
    try:
        efforts = create_efforts(
            df=df,
            cp=cp,
            window_sec=effort_config.window_seconds,
            merge_pct=effort_config.merge_power_diff_percent,
            min_cp_pct=effort_config.min_effort_intensity_cp,
            trim_win=effort_config.trim_window_seconds,
            trim_low=effort_config.trim_low_percent
        )

        # Merge and extend
        efforts = merge_extend(
            df=df,
            efforts=efforts,
            merge_pct=merge_pct,
            trim_win=trim_win,
            trim_low=trim_low,
            extend_win=extend_win,
            extend_low=extend_low
        )

        # Split included efforts
        efforts = split_included(df=df, efforts=efforts)

        logger.info(f"Detected {len(efforts)} efforts")
    except Exception as e:
        logger.error(f"Error detecting efforts: {e}")
        raise HTTPException(
            status_code=500, detail="Error detecting efforts"
        )

    # Detect sprints with user parameters
    try:
        sprint_config = SprintConfig(
            min_power=sprint_min_power,
            window_seconds=sprint_min_duration,
            merge_gap_sec=sprint_merge_gap
        )
        sprints = detect_sprints(
            df=df,
            min_power=sprint_min_power,
            min_duration_sec=sprint_min_duration,
            merge_gap_sec=sprint_merge_gap
        )
        logger.info(f"Detected {len(sprints)} sprints")
    except Exception as e:
        logger.warning(f"Sprint detection failed: {e}")
        sprints = []
        sprint_detection_error = str(e)
    else:
        sprint_detection_error = None

    # Calculate ride statistics
    ride_stats = calculate_ride_stats(df, cp)

    # Store session data (Redis-backed when REDIS_URL is configured)
    sessions[session_id] = {
        'filename': file.filename,
        'df': df,
        'efforts': efforts,
        'sprints': sprints,
        'cp': cp,
        'weight': weight,
        'effort_config': effort_config,
        'sprint_config': sprint_config,
        'stats': ride_stats,
        'sprint_detection_error': sprint_detection_error,
        'kjkg_sections': 5  # Default: 5 kJ/kg sections
    }

    # Redirect to dashboard with tabs
    return RedirectResponse(url=f"/dashboard/{session_id}", status_code=303)
