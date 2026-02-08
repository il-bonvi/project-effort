# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""Upload route - Handle FIT file upload and effort detection"""

import uuid
import logging
import sys
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, File, UploadFile, HTTPException, Form
from fastapi.responses import RedirectResponse

# Add PEFFORT to path for imports
_peffort_path = Path(__file__).parent.parent.parent / "PEFFORT"
sys.path.insert(0, str(_peffort_path))

from peffort_engine import (  # type: ignore
    parse_fit, create_efforts, merge_extend, split_included, detect_sprints
)
from peffort_config import EffortConfig, SprintConfig  # type: ignore

from utils.metrics import calculate_ride_stats

logger = logging.getLogger(__name__)

# Upload directory
UPLOAD_DIR = Path(__file__).parent.parent.parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# This will be set by app.py
_shared_sessions: Dict[str, Any] = {}

router = APIRouter()


def setup_upload_router(sessions_dict: Dict[str, Any]):
    """Setup the upload router with shared sessions dictionary"""
    global _shared_sessions
    _shared_sessions = sessions_dict


@router.post("/upload")
async def upload_fit(
    file: UploadFile = File(...),
    ftp: float = Form(280),
    weight: float = Form(70),
    window_sec: int = Form(60),
    min_ftp_pct: float = Form(100),
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
        ftp: Functional Threshold Power (W)
        weight: Athlete weight (kg)
        window_sec: Detection window (seconds)
        min_ftp_pct: Minimum FTP intensity (%)
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
    # Validate file
    if not file.filename or not file.filename.lower().endswith('.fit'):
        raise HTTPException(status_code=400, detail="File must be a .fit file")
    
    # Generate session ID
    session_id = str(uuid.uuid4())[:8]
    
    # Save uploaded file
    file_path = UPLOAD_DIR / f"{session_id}_{file.filename}"
    try:
        content = await file.read()
        with open(file_path, 'wb') as f:
            f.write(content)
        logger.info(f"File saved: {file_path}")
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving file: {str(e)}")
    
    # Parse FIT file
    try:
        df = parse_fit(str(file_path))
        logger.info(f"FIT parsed: {len(df)} records")
    except Exception as e:
        logger.error(f"Error parsing FIT: {e}")
        # Clean up
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=400, detail=f"Error parsing FIT file: {str(e)}")
    
    # Create effort config with all parameters
    effort_config = EffortConfig(
        window_seconds=window_sec,
        min_effort_intensity_ftp=min_ftp_pct,
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
            ftp=ftp,
            window_sec=effort_config.window_seconds,
            merge_pct=effort_config.merge_power_diff_percent,
            min_ftp_pct=effort_config.min_effort_intensity_ftp,
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
        raise HTTPException(status_code=500, detail=f"Error detecting efforts: {str(e)}")
    
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
    
    # Calculate ride statistics
    ride_stats = calculate_ride_stats(df, ftp)
    
    # Store session data
    _shared_sessions[session_id] = {
        'file_path': str(file_path),
        'filename': file.filename,
        'df': df,
        'efforts': efforts,
        'sprints': sprints,
        'ftp': ftp,
        'weight': weight,
        'effort_config': effort_config,
        'sprint_config': sprint_config,
        'stats': ride_stats
    }
    
    # Redirect to dashboard with tabs
    return RedirectResponse(url=f"/dashboard/{session_id}", status_code=303)
