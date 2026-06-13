# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# ==============================================================================

"""Upload route — FIT file upload + effort detection (ruptures OR legacy)."""

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

from utils.effort_analyzer import parse_fit, detect_sprints
from utils.ruptures_analyzer import RupturesConfig, detect_efforts_ruptures
from utils.analysis_config import SprintConfig, EffortConfig
from utils.metrics import calculate_ride_stats

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(tempfile.gettempdir()) / "peffort_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

RATE_LIMIT_MAX_REQUESTS   = 10
RATE_LIMIT_WINDOW_SECONDS = 60
TRUST_PROXY_HEADERS = os.getenv(
    "UPLOAD_RATE_LIMIT_TRUST_PROXY_HEADERS", "false"
).strip().lower() in {"1", "true", "yes", "on"}

try:
    RATE_LIMIT_MAX_REQUESTS = max(1, int(os.getenv(
        "UPLOAD_RATE_LIMIT_MAX_REQUESTS", str(RATE_LIMIT_MAX_REQUESTS))))
except ValueError:
    RATE_LIMIT_MAX_REQUESTS = 10

try:
    RATE_LIMIT_WINDOW_SECONDS = max(1, int(os.getenv(
        "UPLOAD_RATE_LIMIT_WINDOW_SECONDS", str(RATE_LIMIT_WINDOW_SECONDS))))
except ValueError:
    RATE_LIMIT_WINDOW_SECONDS = 60

_upload_timestamps: Dict[str, deque] = {}
_upload_rate_lock = Lock()

router = APIRouter()


def setup_upload_router(sessions_dict: Dict[str, Any]):
    _ = sessions_dict


def _is_upload_rate_limited(client_ip: str) -> bool:
    now = time.monotonic()
    with _upload_rate_lock:
        queue = _upload_timestamps.get(client_ip)
        if queue is not None:
            while queue and now - queue[0] > RATE_LIMIT_WINDOW_SECONDS:
                queue.popleft()
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

    # ── Athlete ────────────────────────────────────────────────────────────────
    cp: float     = Form(250),
    weight: float = Form(60),

    # ── Detection method switch ────────────────────────────────────────────────
    analysis_method: str = Form("ruptures"),   # "ruptures" | "legacy"

    # ── Ruptures params ────────────────────────────────────────────────────────
    ruptures_model: str          = Form("l2"),
    ruptures_penalty: float      = Form(10.0),
    ruptures_min_seg: int        = Form(15),
    ruptures_smooth: int         = Form(20),
    ruptures_merge_gap: int      = Form(30),
    ruptures_merge_power_diff: float = Form(15.0),
    min_cp_pct: float            = Form(100.0),

    # ── Legacy params ──────────────────────────────────────────────────────────
    legacy_window_sec: int       = Form(60),
    legacy_min_cp_pct: float     = Form(100.0),
    legacy_merge_pct: float      = Form(15.0),
    legacy_trim_window: int      = Form(10),
    legacy_extend_window: int    = Form(15),

    # ── Sprint detection (shared) ──────────────────────────────────────────────
    sprint_min_power: int        = Form(500),
    sprint_min_duration: int     = Form(5),
    sprint_merge_gap: int        = Form(3),
):
    client_ip = _get_client_ip(request)
    if _is_upload_rate_limited(client_ip):
        raise HTTPException(status_code=429, detail="Too many uploads. Please wait.")

    if not file.filename or not file.filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="File must be a .fit file")

    # ── Validate common ────────────────────────────────────────────────────────
    if not (50 <= cp <= 600):
        raise HTTPException(status_code=400, detail="CP must be 50–600 W")
    if not (30 <= weight <= 200):
        raise HTTPException(status_code=400, detail="Weight must be 30–200 kg")
    if analysis_method not in ("ruptures", "legacy"):
        raise HTTPException(status_code=400, detail="analysis_method must be 'ruptures' or 'legacy'")

    # ── Validate ruptures params ───────────────────────────────────────────────
    if analysis_method == "ruptures":
        if ruptures_model not in ("rbf", "l2", "l1"):
            raise HTTPException(status_code=400, detail="ruptures_model must be rbf, l2 or l1")
        if not (0.5 <= ruptures_penalty <= 200):
            raise HTTPException(status_code=400, detail="ruptures_penalty must be 0.5–200")
        if not (5 <= ruptures_min_seg <= 600):
            raise HTTPException(status_code=400, detail="ruptures_min_seg must be 5–600 s")
        if not (0 <= ruptures_smooth <= 120):
            raise HTTPException(status_code=400, detail="ruptures_smooth must be 0–120 s")
        if not (0 <= ruptures_merge_gap <= 300):
            raise HTTPException(status_code=400, detail="ruptures_merge_gap must be 0–300 s")
        if not (0 <= ruptures_merge_power_diff <= 100):
            raise HTTPException(status_code=400, detail="ruptures_merge_power_diff must be 0–100")
        if not (50 <= min_cp_pct <= 300):
            raise HTTPException(status_code=400, detail="min_cp_pct must be 50–300")

    # ── Validate sprint params ─────────────────────────────────────────────────
    if not (200 <= sprint_min_power <= 2000):
        raise HTTPException(status_code=400, detail="sprint_min_power must be 200–2000 W")
    if not (1 <= sprint_min_duration <= 120):
        raise HTTPException(status_code=400, detail="sprint_min_duration must be 1–120 s")
    if not (0 <= sprint_merge_gap <= 60):
        raise HTTPException(status_code=400, detail="sprint_merge_gap must be 0–60 s")

    # ── Save file ──────────────────────────────────────────────────────────────
    session_id = str(uuid.uuid4())
    file_path  = UPLOAD_DIR / f"{session_id}.fit"

    try:
        max_size   = 50 * 1024 * 1024
        chunk_size = 1024 * 1024
        total_size = 0
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(chunk_size)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_size:
                    f.close()
                    file_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=400, detail="File too large (max 50 MB)")
                f.write(chunk)
        if total_size == 0:
            file_path.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail="File is empty")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error saving file: %s", e)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail="Error saving file")

    # ── Parse FIT ─────────────────────────────────────────────────────────────
    try:
        df = parse_fit(str(file_path))
        logger.info("FIT parsed: %d records", len(df))
    except Exception as e:
        logger.error("Error parsing FIT: %s", e)
        raise HTTPException(status_code=400, detail="Error parsing FIT file")
    finally:
        file_path.unlink(missing_ok=True)

    # ── Effort detection ───────────────────────────────────────────────────────
    if analysis_method == "ruptures":
        ruptures_cfg = RupturesConfig(
            model                = ruptures_model,
            penalty              = ruptures_penalty,
            min_segment_sec      = ruptures_min_seg,
            smooth_window_sec    = ruptures_smooth,
            min_cp_pct           = min_cp_pct,
            merge_gap_sec        = ruptures_merge_gap,
            merge_power_diff_pct = ruptures_merge_power_diff,
        )
        try:
            efforts = detect_efforts_ruptures(df, cp=cp, config=ruptures_cfg)
            logger.info("ruptures detected %d efforts", len(efforts))
        except Exception as e:
            logger.error("Error in ruptures detection: %s", e)
            raise HTTPException(status_code=500, detail="Error detecting efforts")

        effort_config = EffortConfig(
            window_seconds           = ruptures_min_seg,
            min_effort_intensity_cp  = min_cp_pct,
            merge_power_diff_percent = ruptures_merge_power_diff,
            trim_window_seconds      = 0,
            trim_low_percent         = 85,
            extend_window_seconds    = 0,
            extend_low_percent       = 80,
        )
        session_detection = {
            "method":         "ruptures",
            "ruptures_config": ruptures_cfg,
        }

    else:  # legacy
        legacy_cfg = EffortConfig(
            window_seconds           = legacy_window_sec,
            min_effort_intensity_cp  = legacy_min_cp_pct,
            merge_power_diff_percent = legacy_merge_pct,
            trim_window_seconds      = legacy_trim_window,
            trim_low_percent         = 85,
            extend_window_seconds    = legacy_extend_window,
            extend_low_percent       = 80,
        )
        try:
            from utils.effort_analyzer import create_efforts, merge_extend, split_included
            efforts = create_efforts(
                df          = df,
                cp          = cp,
                window_sec  = legacy_window_sec,
                merge_pct   = legacy_merge_pct,
                min_cp_pct  = legacy_min_cp_pct,
                trim_win    = legacy_trim_window,
                trim_low    = 85,
            )
            efforts = merge_extend(
                df         = df,
                efforts    = efforts,
                merge_pct  = legacy_merge_pct,
                trim_win   = legacy_trim_window,
                trim_low   = 85,
                extend_win = legacy_extend_window,
                extend_low = 80,
            )
            efforts = split_included(df=df, efforts=efforts)
            logger.info("legacy detected %d efforts", len(efforts))
        except Exception as e:
            logger.error("Error in legacy detection: %s", e)
            raise HTTPException(status_code=500, detail="Error detecting efforts (legacy)")

        effort_config = legacy_cfg
        ruptures_cfg  = None
        session_detection = {
            "method":        "legacy",
            "effort_config": legacy_cfg,
        }

    # ── Sprint detection ───────────────────────────────────────────────────────
    sprint_config = SprintConfig(
        min_power      = sprint_min_power,
        window_seconds = sprint_min_duration,
        merge_gap_sec  = sprint_merge_gap,
    )
    try:
        sprints = detect_sprints(
            df              = df,
            min_power       = sprint_min_power,
            min_duration_sec= sprint_min_duration,
            merge_gap_sec   = sprint_merge_gap,
        )
        logger.info("Detected %d sprints", len(sprints))
        sprint_detection_error = None
    except Exception as e:
        logger.warning("Sprint detection failed: %s", e)
        sprints = []
        sprint_detection_error = str(e)

    ride_stats = calculate_ride_stats(df, cp)

    # ── Store session ──────────────────────────────────────────────────────────
    sessions[session_id] = {
        "filename":              file.filename,
        "df":                    df,
        "efforts":               efforts,
        "sprints":               sprints,
        "cp":                    cp,
        "weight":                weight,
        "effort_config":         effort_config,
        "ruptures_config":       ruptures_cfg,
        "sprint_config":         sprint_config,
        "stats":                 ride_stats,
        "sprint_detection_error": sprint_detection_error,
        "kjkg_sections":         5,
        **session_detection,
    }

    return RedirectResponse(url=f"/dashboard/{session_id}", status_code=303)