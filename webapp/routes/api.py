# ==============================================================================
# Copyright (c) 2026 Andrea Bonvicin - bFactor Project
# PROPRIETARY LICENSE - TUTTI I DIRITTI RISERVATI
# Sharing, distribution or reproduction is strictly prohibited.
# La condivisione, distribuzione o riproduzione è severamente vietata.
# ==============================================================================

"""
API ROUTES - RESTful endpoints for effort/sprint manipulation and data export
"""

import re
import html as html_module
import json
import logging
import csv
import urllib.request
from datetime import datetime, timezone
import numpy as np
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from io import StringIO, BytesIO

from fastapi import APIRouter, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from dependencies import SessionsDep

from utils.effort_analyzer import (
    create_efforts, merge_extend, split_included, detect_sprints
)
from utils.analysis_config import EffortConfig, SprintConfig

# Configure logging
logger = logging.getLogger(__name__)

def _invalidate_session_caches(session: Dict[str, Any]) -> None:
    """Drop derived per-session caches after any mutation of core session data."""
    session.pop('_chart_data_cache', None)
    session.pop('_map2d_html_cache', None)
    session.pop('_map3d_html_cache', None)


def _normalize_efforts(efforts: List[Tuple[int, int, float]]) -> List[Tuple[int, int, float]]:
    """Canonical effort order: chronological by start index (then end index)."""
    return sorted(efforts, key=lambda e: (int(e[0]), int(e[1])))


def _normalize_sprints(sprints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Canonical sprint order: descending average power."""
    return sorted(sprints, key=lambda s: float(s.get('avg', 0.0)), reverse=True)


def _normalize_session_intervals(session: Dict[str, Any]) -> None:
    """Keep session intervals in canonical order for cross-tab stable numbering."""
    if 'efforts' in session and isinstance(session.get('efforts'), list):
        session['efforts'] = _normalize_efforts(session.get('efforts', []))
    if 'sprints' in session and isinstance(session.get('sprints'), list):
        session['sprints'] = _normalize_sprints(session.get('sprints', []))


def _get_non_overlapping_bounds(efforts: List[Tuple[int, int, float]], effort_idx: int, 
                                proposed_start: int, proposed_end: int) -> Tuple[int, int]:
    """
    Adjust proposed bounds to avoid overlapping with other efforts.
    
    If the proposed range overlaps with another effort:
    - If effort comes before another: shrink proposed_end to match the start of the next effort
    - If effort comes after another: shrink proposed_start to match the end of the previous effort
    
    Args:
        efforts: List of all efforts (start_idx, end_idx, avg_power)
        effort_idx: Index of the effort being modified
        proposed_start: Proposed new start index
        proposed_end: Proposed new end index
    
    Returns:
        Tuple of (adjusted_start, adjusted_end) that don't overlap with other efforts
    """
    adjusted_start = proposed_start
    adjusted_end = proposed_end
    
    # Check against all other efforts
    for idx, other_effort in enumerate(efforts):
        if idx == effort_idx:
            continue
        
        other_start, other_end, _ = other_effort
        
        # Check if proposed range overlaps with this effort
        # Overlap occurs if: proposed_start < other_end AND proposed_end > other_start
        if adjusted_start < other_end and adjusted_end > other_start:
            # There's an overlap - need to prevent it
            # If our proposed range starts before this effort, clip the end
            if adjusted_start < other_start:
                adjusted_end = min(adjusted_end, other_start)
            # If our proposed range starts at or after this effort's start, clip the start
            else:
                adjusted_start = max(adjusted_start, other_end)
    
    return adjusted_start, adjusted_end


def setup_api_router(sessions_dict: Dict[str, Dict[str, Any]]) -> APIRouter:
    """
    Set up the API router with access to shared sessions.

    Args:
        sessions_dict: Reference to the main sessions dictionary from app.py

    Returns:
        Configured APIRouter instance
    """
    _ = sessions_dict
    return router


# Create the APIRouter
router = APIRouter(
    prefix="/api",
    tags=["api"],
    responses={404: {"description": "Not found"}}
)


# =============================================================================
# PYDANTIC MODELS - Request/Response schemas
# =============================================================================

class MergeRequest(BaseModel):
    """Request to merge two consecutive efforts"""
    effort_idx1: int
    effort_idx2: int


class ExtendRequest(BaseModel):
    """Request to extend an effort before/after"""
    effort_idx: int
    extend_before_sec: Optional[int] = 0
    extend_after_sec: Optional[int] = 0


class SplitRequest(BaseModel):
    """Request to split an effort at a specific time"""
    effort_idx: int
    split_time_sec: float

class TrimRequest(BaseModel):
    """Request to trim an effort start/end in seconds"""
    effort_idx: int
    trim_start_sec: int = 0
    trim_end_sec: int = 0


class EffortModification(BaseModel):
    """Single effort modification with start/end timestamps"""
    start: float
    end: float
    label: str
    color: Optional[str] = None


class SprintModification(BaseModel):
    """Single sprint modification with start/end timestamps"""
    start: float
    end: float
    label: str
    color: Optional[str] = None


class LocalModificationsRequest(BaseModel):
    """Request to apply local effort/sprint modifications from inspection view"""
    efforts: list[EffortModification]
    sprints: list[SprintModification]
    deleted_effort_indices: list[int] = []
    deleted_sprint_indices: list[int] = []


class DashboardImportEffort(BaseModel):
    """Effort record used by dashboard JSON import."""
    index: Optional[int] = None
    new_start: float
    new_end: float
    avg_power: float = 0.0
    deleted: bool = False


class DashboardImportSprint(BaseModel):
    """Sprint record used by dashboard JSON import."""
    start: float
    end: float
    label: str
    color: Optional[str] = None
    avg: Optional[float] = None
    duration: Optional[float] = None
    max_power: Optional[float] = None


class DashboardImportRequest(BaseModel):
    """Validated payload for dashboard JSON import."""
    session_id: str
    efforts: list[DashboardImportEffort]
    sprints: list[DashboardImportSprint] = Field(default_factory=list)
    deleted_efforts: list[int] = Field(default_factory=list)
    deleted_sprints: list[int] = Field(default_factory=list)


class LegacyImportEffort(BaseModel):
    """Effort item for legacy /{session_id}/import payload."""
    index: int
    new_start: float
    new_end: float
    avg_power: float = 0.0


class LegacyImportRequest(BaseModel):
    """Validated legacy import payload."""
    efforts: list[LegacyImportEffort] = Field(default_factory=list)
    deleted_efforts: list[int] = Field(default_factory=list)
    deleted_sprints: list[int] = Field(default_factory=list)


class ExportJsonLlamaRequest(BaseModel):
    """Request to export JSON for Llama training with activity type"""
    activity_type: str = Field(..., description="Type of activity: allenamento, corsa_circuito, corsa_linea, ITT, TTT")


# =============================================================================
# SESSION DATA ENDPOINTS
# =============================================================================

@router.get("/session-data/{session_id}")
async def get_session_data(session_id: str, sessions: SessionsDep):
    """
    Get FIT data for inspection chart (time_sec, power, efforts, cp)

    Returns:
        JSON with time_sec, power arrays and effort list
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        session = sessions[session_id]
        df = session.get('df')
        efforts = session.get('efforts', [])
        cp = session.get('cp', 250)

        if df is None or df.empty:
            raise HTTPException(status_code=400, detail="No FIT data available")

        time_sec = df['time_sec'].tolist()
        power = df['power'].tolist()

        efforts_data = []
        for start_idx, end_idx, avg_power in efforts:
            efforts_data.append({
                'start_idx': int(start_idx),
                'end_idx': int(end_idx),
                'avg_power': float(avg_power)
            })

        return {
            'success': True,
            'data': {
                'time_sec': time_sec,
                'power': power
            },
            'efforts': efforts_data,
            'cp': float(cp)
        }
    except Exception as e:
        logger.error(f"Error getting session data: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{session_id}/status")
async def get_session_status(session_id: str, sessions: SessionsDep):
    """
    Get current session status and effort/sprint counts

    Returns:
        JSON with session_id, filename, record count, effort/sprint counts, CP, weight
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    sprint_detection_error = session.get('sprint_detection_error')
    if sprint_detection_error:
        logger.warning("Session %s has sprint_detection_error: %s", session_id, sprint_detection_error)

    return {
        "session_id": session_id,
        "filename": session['filename'],
        "total_records": len(session['df']),
        "total_efforts": len(session['efforts']),
        "total_sprints": len(session.get('sprints', [])),
        "cp": session.get('cp', 250),
        "weight": session.get('weight', 60),
        "sprint_detection_error": sprint_detection_error
    }


class UpdateCpWeightRequest(BaseModel):
    cp: int
    weight: float

class UpdateKjkgSectionsRequest(BaseModel):
    kjkg_sections: float

@router.post("/{session_id}/update-cp-weight")
async def update_cp_weight(session_id: str, request: UpdateCpWeightRequest, sessions: SessionsDep):
    """
    Update CP and weight values for a session

    Args:
        session_id: Session ID
        request: UpdateCpWeightRequest with cp and weight values

    Returns:
        JSON confirmation
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    # Validate inputs
    if not (50 <= request.cp <= 500):
        raise HTTPException(status_code=400, detail="CP must be between 50 and 500 watts")

    if not (40 <= request.weight <= 150):
        raise HTTPException(status_code=400, detail="Weight must be between 40 and 150 kg")

    # Update session values
    session['cp'] = request.cp
    session['weight'] = request.weight

    # Recalculate stats if CP changed
    if 'stats' in session:
        from utils.metrics import calculate_ride_stats
        session['stats'] = calculate_ride_stats(session['df'], request.cp)

    # Only invalidate caches to refresh metric calculations (avg_speed, W/kg, etc)
    # DO NOT re-detect efforts/sprints - they are managed manually in inspection.html
    _invalidate_session_caches(session)

    logger.info(f"Updated session {session_id}: CP={request.cp}W, Weight={request.weight}kg")

    return {
        "status": "success",
        "message": f"CP updated to {request.cp}W, Weight updated to {request.weight}kg",
        "cp": request.cp,
        "weight": request.weight
    }


@router.post("/{session_id}/update-kjkg-sections")
async def update_kjkg_sections(session_id: str, request: UpdateKjkgSectionsRequest, sessions: SessionsDep):
    """
    Update kJ/kg sections configuration for altimetria visualization

    Args:
        session_id: Session ID
        request: UpdateKjkgSectionsRequest with kjkg_sections value

    Returns:
        JSON confirmation
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    # Validate input
    if not (0.5 <= request.kjkg_sections <= 20):
        raise HTTPException(status_code=400, detail="kJ/kg sections must be between 0.5 and 20")

    # Update session value
    session['kjkg_sections'] = request.kjkg_sections

    # Invalidate chart data cache so it's recalculated with new setting
    _invalidate_session_caches(session)

    logger.info(f"Updated session {session_id}: kJ/kg sections={request.kjkg_sections}")

    return {
        "status": "success",
        "message": f"kJ/kg sections updated to {request.kjkg_sections}"
    }


# =============================================================================
# EFFORT MANIPULATION ENDPOINTS
# =============================================================================

@router.post("/{session_id}/merge")
async def merge_efforts(session_id: str, request: MergeRequest, sessions: SessionsDep):
    """
    Merge two efforts into one, creating new effort spanning both

    Args:
        request: MergeRequest with effort_idx1 and effort_idx2

    Returns:
        JSON confirmation with new total effort count
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    efforts = session['efforts']

    if request.effort_idx1 >= len(efforts) or request.effort_idx2 >= len(efforts):
        raise HTTPException(status_code=400, detail="Invalid effort indices")

    e1 = efforts[request.effort_idx1]
    e2 = efforts[request.effort_idx2]

    new_start = min(e1[0], e2[0])
    new_end = max(e1[1], e2[1])

    df = session['df']
    merged_data = df.iloc[new_start:new_end]
    new_avg_power = merged_data['power'].mean() if len(merged_data) > 0 else (e1[2] + e2[2]) / 2

    new_efforts = [e for i, e in enumerate(efforts) if i not in [request.effort_idx1, request.effort_idx2]]
    new_efforts.append((new_start, new_end, new_avg_power))
    new_efforts.sort(key=lambda x: x[0])

    session['efforts'] = _normalize_efforts(new_efforts)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": f"Merged efforts {request.effort_idx1} and {request.effort_idx2}",
        "total_efforts": len(new_efforts)
    }


@router.post("/{session_id}/extend")
async def extend_effort(session_id: str, request: ExtendRequest, sessions: SessionsDep):
    """
    Extend an effort before and/or after

    Args:
        request: ExtendRequest with effort_idx and seconds to extend

    Returns:
        JSON confirmation with new time boundaries and duration
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    efforts = session['efforts']
    df = session['df']

    if request.effort_idx >= len(efforts):
        raise HTTPException(status_code=400, detail="Invalid effort index")

    effort = efforts[request.effort_idx]
    start_idx, end_idx, _ = effort

    time_diff = df['time_sec'].diff().median()
    samples_per_sec = 1 / time_diff if time_diff > 0 else 1

    new_start = max(0, start_idx - int(request.extend_before_sec * samples_per_sec))
    new_end = min(len(df), end_idx + int(request.extend_after_sec * samples_per_sec))
    
    # Prevent overlaps with other efforts
    new_start, new_end = _get_non_overlapping_bounds(efforts, request.effort_idx, new_start, new_end)

    extended_data = df.iloc[new_start:new_end]
    new_avg_power = extended_data['power'].mean() if len(extended_data) > 0 else effort[2]

    efforts[request.effort_idx] = (new_start, new_end, new_avg_power)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": f"Extended effort {request.effort_idx}",
        "new_start": int(df.iloc[new_start]['time_sec']),
        "new_end": int(df.iloc[new_end-1]['time_sec']) if new_end > 0 else 0,
        "new_duration": new_end - new_start
    }


@router.post("/{session_id}/split")
async def split_effort(session_id: str, request: SplitRequest, sessions: SessionsDep):
    """
    Split an effort at a specific time

    Args:
        request: SplitRequest with effort_idx and split_time_sec

    Returns:
        JSON confirmation with new total effort count
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    efforts = session['efforts']
    df = session['df']

    if request.effort_idx >= len(efforts):
        raise HTTPException(status_code=400, detail="Invalid effort index")

    effort = efforts[request.effort_idx]
    start_idx, end_idx, _ = effort

    effort_df = df.iloc[start_idx:end_idx]
    split_idx = effort_df[effort_df['time_sec'] >= request.split_time_sec].index

    if len(split_idx) == 0:
        raise HTTPException(status_code=400, detail="Split time not within effort bounds")

    split_idx = split_idx[0]

    data1 = df.iloc[start_idx:split_idx]
    data2 = df.iloc[split_idx:end_idx]

    avg_power1 = data1['power'].mean() if len(data1) > 0 else effort[2]
    avg_power2 = data2['power'].mean() if len(data2) > 0 else effort[2]

    new_efforts = [e for i, e in enumerate(efforts) if i != request.effort_idx]
    new_efforts.append((start_idx, split_idx, avg_power1))
    new_efforts.append((split_idx, end_idx, avg_power2))
    new_efforts.sort(key=lambda x: x[0])

    session['efforts'] = _normalize_efforts(new_efforts)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": f"Split effort {request.effort_idx} at {request.split_time_sec}s",
        "total_efforts": len(new_efforts)
    }


@router.post("/{session_id}/trim")
async def trim_effort(session_id: str, request: TrimRequest, sessions: SessionsDep):
    """
    Trim an effort by removing seconds from start and/or end

    Args:
        effort_idx: Index of effort to trim
        trim_start_sec: Seconds to remove from start (positive value)
        trim_end_sec: Seconds to remove from end (positive value)

    Returns:
        JSON confirmation with new time boundaries
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    efforts = session['efforts']
    df = session['df']

    if request.effort_idx >= len(efforts) or request.effort_idx < 0:
        raise HTTPException(status_code=400, detail="Invalid effort index")

    effort = efforts[request.effort_idx]
    start_idx, end_idx, _ = effort

    time_diff = df['time_sec'].diff().median()
    samples_per_sec = 1 / time_diff if time_diff > 0 else 1

    new_start = start_idx + int(request.trim_start_sec * samples_per_sec)
    new_end = end_idx - int(request.trim_end_sec * samples_per_sec)
    
    # Prevent overlaps with other efforts
    new_start, new_end = _get_non_overlapping_bounds(efforts, request.effort_idx, new_start, new_end)

    if new_start >= new_end:
        raise HTTPException(status_code=400, detail="Trim would result in invalid effort (start >= end)")

    if new_start < 0 or new_end > len(df):
        raise HTTPException(status_code=400, detail="Trim exceeds data bounds")

    trimmed_data = df.iloc[new_start:new_end]
    new_avg_power = trimmed_data['power'].mean() if len(trimmed_data) > 0 else effort[2]

    efforts[request.effort_idx] = (new_start, new_end, new_avg_power)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": (
            f"Trimmed effort {request.effort_idx}: removed "
            f"{request.trim_start_sec}s from start, {request.trim_end_sec}s from end"
        ),
        "new_start_time": int(df.iloc[new_start]['time_sec']),
        "new_end_time": int(df.iloc[new_end-1]['time_sec']) if new_end > 0 else 0,
        "new_duration": new_end - new_start,
        "new_avg_power": int(new_avg_power)
    }


@router.delete("/{session_id}/effort/{effort_idx}")
async def delete_effort(session_id: str, effort_idx: int, sessions: SessionsDep):
    """
    Delete a specific effort by index

    Args:
        effort_idx: Index of effort to delete

    Returns:
        JSON confirmation with effort data that was deleted
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    efforts = session['efforts']

    if effort_idx >= len(efforts) or effort_idx < 0:
        raise HTTPException(status_code=400, detail="Invalid effort index")

    deleted = efforts.pop(effort_idx)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": f"Deleted effort {effort_idx}",
        "deleted_effort": {
            "start": int(session['df'].iloc[deleted[0]]['time_sec']),
            "end": int(session['df'].iloc[deleted[1]-1]['time_sec']) if deleted[1] > 0 else 0,
            "avg_power": deleted[2]
        },
        "remaining_efforts": len(efforts)
    }


@router.delete("/{session_id}/sprint/{sprint_idx}")
async def delete_sprint(session_id: str, sprint_idx: int, sessions: SessionsDep):
    """
    Delete a specific sprint by index

    Args:
        sprint_idx: Index of sprint to delete

    Returns:
        JSON confirmation with sprint data that was deleted
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    sprints = session['sprints']

    if sprint_idx >= len(sprints) or sprint_idx < 0:
        raise HTTPException(status_code=400, detail="Invalid sprint index")

    deleted = sprints.pop(sprint_idx)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": f"Deleted sprint {sprint_idx}",
        "deleted_sprint": {
            "start": deleted.get('start', 0),
            "end": deleted.get('end', 0),
            "avg_power": deleted.get('avg', 0)
        },
        "remaining_sprints": len(sprints)
    }

@router.delete("/{session_id}")
async def delete_session(session_id: str, sessions: SessionsDep):
    """Delete an in-memory session and free related memory."""
    deleted = sessions.pop(session_id, None)
    if deleted is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "deleted", "session_id": session_id}


@router.post("/{session_id}/import")
@router.post("/{session_id}/import-legacy")
async def import_modifications(session_id: str, modifications: LegacyImportRequest, sessions: SessionsDep):
    """
    Import effort modifications from exported JSON

    Expected format:
    {
        "efforts": [{"index": 0, "new_start": 100, "new_end": 200, ...}],
        "deleted_efforts": [2, 4],
        "deleted_sprints": [1, 3]
    }

    Returns:
        JSON confirmation with import results
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']

    deleted_effort_indices = set(modifications.deleted_efforts)
    deleted_sprint_indices = set(modifications.deleted_sprints)

    new_efforts = []
    for effort_mod in modifications.efforts:
        if effort_mod.index in deleted_effort_indices:
            continue

        start_time = effort_mod.new_start
        end_time = effort_mod.new_end

        start_idx_list = df[df['time_sec'] >= start_time].index.tolist()
        start_idx = start_idx_list[0] if start_idx_list else 0

        end_idx_list = df[df['time_sec'] <= end_time].index.tolist()
        end_idx = (end_idx_list[-1] + 1) if end_idx_list else len(df)

        segment_data = df.iloc[start_idx:end_idx]
        avg_power = segment_data['power'].mean() if len(segment_data) > 0 else effort_mod.avg_power

        new_efforts.append((start_idx, end_idx, avg_power))

    session['efforts'] = _normalize_efforts(new_efforts)

    # Remove deleted sprints
    sprints = session.get('sprints', [])
    new_sprints = [sprint for i, sprint in enumerate(sprints) if i not in deleted_sprint_indices]
    session['sprints'] = _normalize_sprints(new_sprints)
    _invalidate_session_caches(session)

    return {
        "success": True,
        "message": "Modifications imported successfully",
        "total_efforts": len(new_efforts),
        "total_sprints": len(new_sprints),
        "deleted_efforts_count": len(deleted_effort_indices),
        "deleted_sprints_count": len(deleted_sprint_indices)
    }


# =============================================================================
# RE-DETECTION ENDPOINTS
# =============================================================================

async def redetect_efforts_impl(
    session_id: str,
    sessions: Dict[str, Dict[str, Any]],
    window_sec: int = 60,
    min_cp_pct: float = 100,
    merge_pct: float = 15,
    trim_win: int = 10,
    trim_low: float = 85,
    extend_win: int = 15,
    extend_low: float = 80
):
    """
    Re-detect efforts with new parameters without re-uploading file.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']
    cp = session.get('cp', 250)

    try:
        efforts = create_efforts(
            df=df,
            cp=cp,
            window_sec=window_sec,
            merge_pct=merge_pct,
            min_cp_pct=min_cp_pct,
            trim_win=trim_win,
            trim_low=trim_low
        )

        efforts = merge_extend(
            df=df,
            efforts=efforts,
            merge_pct=merge_pct,
            trim_win=trim_win,
            trim_low=trim_low,
            extend_win=extend_win,
            extend_low=extend_low
        )

        efforts = split_included(df=df, efforts=efforts)

        session['efforts'] = _normalize_efforts(efforts)
        _invalidate_session_caches(session)

        if 'effort_config' not in session:
            session['effort_config'] = EffortConfig()
        session['effort_config'].window_seconds = window_sec
        session['effort_config'].min_effort_intensity_cp = min_cp_pct
        session['effort_config'].merge_power_diff_percent = merge_pct
        session['effort_config'].trim_window_seconds = trim_win
        session['effort_config'].trim_low_percent = trim_low
        session['effort_config'].extend_window_seconds = extend_win
        session['effort_config'].extend_low_percent = extend_low

        return {
            "success": True,
            "message": "Efforts re-detected successfully",
            "total_efforts": len(efforts),
            "parameters": {
                "window_sec": window_sec,
                "min_cp_pct": min_cp_pct,
                "merge_pct": merge_pct,
                "trim_win": trim_win,
                "trim_low": trim_low,
                "extend_win": extend_win,
                "extend_low": extend_low
            }
        }

    except Exception as e:
        logger.error(f"Error re-detecting efforts: {e}")
        raise HTTPException(status_code=500, detail=f"Error re-detecting efforts: {str(e)}")


async def redetect_sprints_impl(
    session_id: str,
    sessions: Dict[str, Dict[str, Any]],
    min_power: int = 500,
    min_duration_sec: int = 5,
    merge_gap_sec: int = 3,
    cadence_min_rpm: int = 50
):
    """
    Re-detect sprints with new parameters.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']

    try:
        sprints = detect_sprints(
            df=df,
            min_power=min_power,
            min_duration_sec=min_duration_sec,
            merge_gap_sec=merge_gap_sec
        )

        session['sprints'] = _normalize_sprints(sprints)
        _invalidate_session_caches(session)

        if 'sprint_config' not in session:
            session['sprint_config'] = SprintConfig()
        session['sprint_config'].min_power = min_power
        session['sprint_config'].window_seconds = min_duration_sec
        session['sprint_config'].merge_gap_sec = merge_gap_sec
        session['sprint_config'].cadence_min_rpm = cadence_min_rpm

        return {
            "success": True,
            "message": "Sprints re-detected successfully",
            "total_sprints": len(sprints),
            "parameters": {
                "min_power": min_power,
                "min_duration_sec": min_duration_sec,
                "merge_gap_sec": merge_gap_sec,
                "cadence_min_rpm": cadence_min_rpm
            }
        }

    except Exception as e:
        logger.error(f"Error re-detecting sprints: {e}")
        raise HTTPException(status_code=500, detail=f"Error re-detecting sprints: {str(e)}")


@router.post("/{session_id}/redetect-efforts")
async def redetect_efforts_json(session_id: str, params: Dict[str, Any], sessions: SessionsDep):
    """
    Re-detect efforts with new parameters via JSON body (called from dashboard).
    """
    return await redetect_efforts_impl(
        session_id=session_id,
        sessions=sessions,
        window_sec=int(params.get('window_sec', 60)),
        min_cp_pct=float(params.get('min_cp_pct', params.get('min_ftp_pct', 100))),
        merge_pct=float(params.get('merge_pct', 15)),
        trim_win=int(params.get('trim_win', 10)),
        trim_low=float(params.get('trim_low', 85)),
        extend_win=int(params.get('extend_win', 15)),
        extend_low=float(params.get('extend_low', 80))
    )


@router.post("/{session_id}/redetect-sprints")
async def redetect_sprints_json(session_id: str, params: Dict[str, Any], sessions: SessionsDep):
    """
    Re-detect sprints with new parameters via JSON body (called from dashboard).
    """
    return await redetect_sprints_impl(
        session_id=session_id,
        sessions=sessions,
        min_power=int(params.get('min_power', 500)),
        min_duration_sec=int(params.get('min_duration_sec', 5)),
        merge_gap_sec=int(params.get('merge_gap_sec', 3)),
        cadence_min_rpm=int(params.get('cadence_min_rpm', 50))
    )


@router.post("/{session_id}/apply-local-modifications")
async def apply_local_modifications(session_id: str, data: LocalModificationsRequest, sessions: SessionsDep):
    """
    Apply effort/sprint modifications from inspection.html.
    Takes the modified efforts and sprints with new timestamps and updates the session.
    
    This is cleaner than localStorage sync - we just re-analyze using the new timestamps.
    
    Args:
        session_id: Session identifier
        data: {
            "efforts": [{"start": float, "end": float, "label": str}, ...],
            "sprints": [{"start": float, "end": float, "label": str}, ...],
            "deleted_effort_indices": [int, ...],
            "deleted_sprint_indices": [int, ...]
        }
    """
    logger.info(f"apply_local_modifications called for session {session_id}")
    logger.info(f"Received {len(data.efforts)} efforts and {len(data.sprints)} sprints")
    logger.info(f"Deleted indices - efforts: {data.deleted_effort_indices}, sprints: {data.deleted_sprint_indices}")
    
    if session_id not in sessions:
        logger.error(f"Session {session_id} not found")
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        session = sessions[session_id]
        df = session['df']
        
        logger.info(f"DataFrame shape: {df.shape}")
        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        
        # Find the time column
        time_col = None
        for col in ['time_sec', 'time', 'timestamp']:
            if col in df.columns:
                time_col = col
                break
        
        if time_col is None:
            raise ValueError(f"DataFrame missing time column. Available columns: {df.columns.tolist()}")
        
        time_axis = df[time_col].tolist()
        time_array = np.array(time_axis)
        max_idx = len(time_axis) - 1
        
        logger.info(f"Time axis range: {time_axis[0]} to {time_axis[-1]}")
        
        def get_closest_idx(timestamp: float) -> int:
            """Find the closest index for a given timestamp."""
            idx = int(np.searchsorted(time_array, timestamp, side='left'))
            if idx <= 0:
                return 0
            if idx >= len(time_array):
                return max_idx
            prev_idx = idx - 1
            if abs(time_array[idx] - timestamp) < abs(time_array[prev_idx] - timestamp):
                return idx
            return prev_idx
        
        # Convert efforts from timestamps to indices
        new_efforts = []
        deleted_effort_indices = set(data.deleted_effort_indices)
        
        logger.info(f"Processing {len(data.efforts)} efforts, {len(deleted_effort_indices)} deleted")
        
        for i, effort in enumerate(data.efforts):
            if i in deleted_effort_indices:
                logger.info(f"Skipping deleted effort {i}")
                continue  # Skip deleted efforts
                
            start_time = float(effort.start)
            end_time = float(effort.end)
            
            logger.info(f"Effort {i}: start_time={start_time}, end_time={end_time}")
            
            start_idx = get_closest_idx(start_time)
            end_idx = get_closest_idx(end_time) + 1  # +1 to make end_idx exclusive (include selected endpoint)
            
            logger.info(f"Effort {i}: start_idx={start_idx}, end_idx={end_idx}")
            
            # Ensure valid range
            if end_idx <= start_idx:
                end_idx = start_idx + 1
            if end_idx > max_idx:
                end_idx = max_idx
            
            # Calculate average power for this segment
            if 'power' in df.columns:
                power_data = df['power'].iloc[start_idx:end_idx].values
                avg_power = float(np.mean(power_data)) if len(power_data) > 0 else 0.0
            else:
                avg_power = 0.0
            
            logger.info(f"Effort {i}: calculated avg_power={avg_power}")
            new_efforts.append((start_idx, end_idx, avg_power))
        
        # Convert sprints from timestamps to indices
        new_sprints = []
        deleted_sprint_indices = set(data.deleted_sprint_indices)
        
        logger.info(f"Processing {len(data.sprints)} sprints, {len(deleted_sprint_indices)} deleted")
        
        for i, sprint in enumerate(data.sprints):
            if i in deleted_sprint_indices:
                logger.info(f"Skipping deleted sprint {i}")
                continue  # Skip deleted sprints
                
            start_time = float(sprint.start)
            end_time = float(sprint.end)
            
            logger.info(f"Sprint {i}: start_time={start_time}, end_time={end_time}")
            
            start_idx = get_closest_idx(start_time)
            end_idx = get_closest_idx(end_time) + 1  # +1 to make end_idx exclusive (include selected endpoint)
            
            logger.info(f"Sprint {i}: start_idx={start_idx}, end_idx={end_idx}")
            
            # Ensure valid range
            if end_idx <= start_idx:
                end_idx = start_idx + 1
            if end_idx > max_idx:
                end_idx = max_idx
            
            # Calculate average power for this sprint segment
            if 'power' in df.columns:
                power_data = df['power'].iloc[start_idx:end_idx].values
                avg_power = float(np.mean(power_data)) if len(power_data) > 0 else 0.0
            else:
                avg_power = 0.0
            
            logger.info(f"Sprint {i}: calculated avg_power={avg_power}")
            
            sprint_dict = {
                'start': start_idx,
                'end': end_idx,
                'label': sprint.label,
                'avg': avg_power
            }
            new_sprints.append(sprint_dict)
        
        # Update session with new efforts and sprints
        session['efforts'] = new_efforts
        session['sprints'] = new_sprints
        _normalize_session_intervals(session)
        _invalidate_session_caches(session)
        
        logger.info(f"Applied local modifications for session {session_id}: {len(new_efforts)} efforts, {len(new_sprints)} sprints")
        
        return {
            "success": True,
            "message": "Local modifications applied successfully",
            "total_efforts": len(new_efforts),
            "total_sprints": len(new_sprints),
            "session_id": session_id
        }
    
    except Exception as e:
        logger.error(f"Error applying local modifications: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error applying modifications: {str(e)}")


# =============================================================================
# EXPORT ENDPOINTS
# =============================================================================

@router.get("/export/{session_id}/json")
async def export_json_data(session_id: str, sessions: SessionsDep):
    """
    Export all data as JSON: efforts, sprints, statistics, parameters
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']

    efforts_export = []
    for i, (start_idx, end_idx, avg_power) in enumerate(session['efforts']):
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        efforts_export.append({
            "index": i,
            "start_time_sec": float(start_time),
            "end_time_sec": float(end_time),
            "duration_sec": float(end_time - start_time),
            "avg_power_w": float(avg_power),
            "start_idx": int(start_idx),
            "end_idx": int(end_idx)
        })

    sprints_export = []
    for i, sprint in enumerate(session.get('sprints', [])):
        start_idx = sprint.get('start_idx', 0)
        end_idx = sprint.get('end_idx', 0)
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        sprints_export.append({
            "index": i,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "max_power_w": sprint.get('max_power', 0),
            "avg_power_w": sprint.get('avg_power', 0),
            "duration_sec": sprint.get('duration', 0)
        })

    export_data = {
        "session_info": {
            "session_id": session_id,
            "filename": session['filename'],
            "cp": session.get('cp', 250),
            "weight": session['weight']
        },
        "ride_statistics": session.get('stats', {}),
        "efforts": efforts_export,
        "sprints": sprints_export,
        "detection_parameters": {
            "effort_config": {
                "window_seconds": session.get('effort_config', EffortConfig()).window_seconds,
                "min_cp_pct": session.get('effort_config', EffortConfig()).min_effort_intensity_cp,
                "merge_pct": session.get('effort_config', EffortConfig()).merge_power_diff_percent,
                "trim_window": session.get('effort_config', EffortConfig()).trim_window_seconds,
                "extend_window": session.get('effort_config', EffortConfig()).extend_window_seconds
            },
            "sprint_config": {
                "min_power": session.get('sprint_config', SprintConfig()).min_power,
                "window_seconds": session.get('sprint_config', SprintConfig()).window_seconds,
                "merge_gap_sec": session.get('sprint_config', SprintConfig()).merge_gap_sec
            }
        }
    }

    json_content = json.dumps(export_data, indent=2, default=str)

    return StreamingResponse(
        BytesIO(json_content.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=peffort_export_{session_id}.json"}
    )


@router.get("/export/{session_id}/gpx")
async def export_gpx_file(session_id: str, sessions: SessionsDep):
    """
    Export GPS track as GPX file if GPS data is available
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']

    if 'position_lat' not in df.columns or 'position_long' not in df.columns:
        raise HTTPException(status_code=400, detail="No GPS data available for GPX export")

    gps_data = df[(df['position_lat'].notna()) & (df['position_long'].notna()) &
                  (df['position_lat'] != 0) & (df['position_long'] != 0)]

    if len(gps_data) == 0:
        raise HTTPException(status_code=400, detail="No valid GPS coordinates found")

    gpx_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="PEFFORT Web"
     xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>{session['filename']} - PEFFORT Export</name>
    <desc>Cycling activity exported from PEFFORT</desc>
  </metadata>
  <trk>
    <name>Cycling Track</name>
    <trkseg>
'''

    for _, row in gps_data.iterrows():
        lat = row['position_lat']
        lon = row['position_long']
        ele = row.get('altitude', 0)
        time = row['time'].strftime('%Y-%m-%dT%H:%M:%SZ')

        gpx_content += f'      <trkpt lat="{lat:.7f}" lon="{lon:.7f}">\n'
        gpx_content += f'        <ele>{ele:.1f}</ele>\n'
        gpx_content += f'        <time>{time}</time>\n'
        gpx_content += '      </trkpt>\n'

    gpx_content += '''    </trkseg>
  </trk>
</gpx>'''

    return StreamingResponse(
        BytesIO(gpx_content.encode('utf-8')),
        media_type="application/gpx+xml",
        headers={"Content-Disposition": f"attachment; filename=peffort_track_{session_id}.gpx"}
    )


@router.get("/export/{session_id}/csv")
async def export_csv_data(session_id: str, sessions: SessionsDep):
    """
    Export efforts and sprints data as CSV for analysis in Excel/Sheets
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)

    writer.writerow([
        'Type', 'Index', 'Start_Time_Sec', 'End_Time_Sec', 'Duration_Sec',
        'Avg_Power_W', 'Max_Power_W', 'Start_Idx', 'End_Idx'
    ])

    for i, (start_idx, end_idx, avg_power) in enumerate(session['efforts']):
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        writer.writerow([
            'Effort', i, start_time, end_time, end_time - start_time,
            avg_power, '', start_idx, end_idx
        ])

    for i, sprint in enumerate(session.get('sprints', [])):
        start_idx = sprint.get('start_idx', 0)
        end_idx = sprint.get('end_idx', 0)
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        writer.writerow([
            'Sprint', i, start_time, end_time, sprint.get('duration', 0),
            sprint.get('avg_power', 0), sprint.get('max_power', 0), start_idx, end_idx
        ])

    csv_content = csv_buffer.getvalue()
    csv_buffer.close()

    return StreamingResponse(
        BytesIO(csv_content.encode('utf-8')),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=peffort_data_{session_id}.csv"}
    )


@router.post("/export/{session_id}/json-llama")
async def export_json_llama_data(session_id: str, request: ExportJsonLlamaRequest, sessions: SessionsDep):
    """
    Export all data as JSON for Llama training with activity type.
    Includes all data from standard JSON export plus activity type classification.
    
    Valid activity types: training, criterium, road, ITT, TTT
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    # Validate activity type
    valid_types = ["training", "freeride", "criterium", "road", "ITT", "TTT"]
    if request.activity_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid activity_type. Must be one of: {', '.join(valid_types)}"
        )

    session = sessions[session_id]
    df = session['df']

    # Build efforts export
    efforts_export = []
    for i, (start_idx, end_idx, avg_power) in enumerate(session['efforts']):
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        efforts_export.append({
            "index": i,
            "start_time_sec": float(start_time),
            "end_time_sec": float(end_time),
            "duration_sec": float(end_time - start_time),
            "avg_power_w": float(avg_power),
            "start_idx": int(start_idx),
            "end_idx": int(end_idx)
        })

    # Build sprints export
    sprints_export = []
    for i, sprint in enumerate(session.get('sprints', [])):
        # Session sprint dicts are commonly stored as {'start','end','avg','max_power'}.
        # Keep compatibility with both key shapes.
        start_idx = int(sprint.get('start', sprint.get('start_idx', 0)))
        end_idx = int(sprint.get('end', sprint.get('end_idx', 0)))
        start_time = df.iloc[start_idx]['time_sec'] if start_idx < len(df) else 0
        end_time = df.iloc[end_idx-1]['time_sec'] if end_idx > 0 and end_idx <= len(df) else 0

        avg_power_w = float(sprint.get('avg', sprint.get('avg_power', 0)))

        sprints_export.append({
            "index": i,
            "start_idx": start_idx,
            "end_idx": end_idx,
            "avg_power_w": avg_power_w,
            "duration_sec": float(end_time - start_time)
        })

    # Build export data with activity type
    export_data = {
        "session_info": {
            "session_id": session_id,
            "filename": session['filename'],
            "cp": session.get('cp', 250),
            "weight": session.get('weight', 60),
            "activity_type": request.activity_type
        },
        "ride_statistics": session.get('stats', {}),
        "efforts": efforts_export,
        "sprints": sprints_export,
        "detection_parameters": {
            "effort_config": {
                "window_seconds": session.get('effort_config', EffortConfig()).window_seconds,
                "min_cp_pct": session.get('effort_config', EffortConfig()).min_effort_intensity_cp,
                "merge_pct": session.get('effort_config', EffortConfig()).merge_power_diff_percent,
                "trim_window": session.get('effort_config', EffortConfig()).trim_window_seconds,
                "extend_window": session.get('effort_config', EffortConfig()).extend_window_seconds
            },
            "sprint_config": {
                "min_power": session.get('sprint_config', SprintConfig()).min_power,
                "window_seconds": session.get('sprint_config', SprintConfig()).window_seconds,
                "merge_gap_sec": session.get('sprint_config', SprintConfig()).merge_gap_sec
            }
        }
    }

    json_content = json.dumps(export_data, indent=2, default=str)

    # Extract filename without extension and add suffix
    fit_filename = session['filename']  # e.g., "20260425_ride.fit"
    base_name = Path(fit_filename).stem  # e.g., "20260425_ride"
    export_filename = f"{base_name}.json"

    return StreamingResponse(
        BytesIO(json_content.encode('utf-8')),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename={export_filename}"}
    )


@router.post("/import-modifications/{session_id}")
@router.post("/{session_id}/import-modifications")
async def import_dashboard_modifications(session_id: str, modifications: DashboardImportRequest, sessions: SessionsDep):
    """
    Import effort modifications from JSON file for dashboard.
    Validates that modifications are for the correct session/file.
    
    Note: This is a separate endpoint from /{session_id}/import. This one is used
    by the dashboard UI and includes additional validation and session_id matching.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    try:
        # Log warning if session ID doesn't match (can happen when reloading same FIT file)
        # but proceed anyway - the file content is what matters, not the session ID
        if modifications.session_id != session_id:
            logger.warning(
                f"Session ID mismatch during import: JSON was from session {modifications.session_id}, "
                f"but importing to session {session_id}. This is normal when importing to a new session of the same FIT file."
            )

        logger.info(f"Importing modifications: {len(modifications.efforts)} efforts, {len(modifications.sprints)} sprints")
        logger.debug(f"Deleted sprints indices: {modifications.deleted_sprints}")

        session = sessions[session_id]

        # Normalize deleted indices for efforts and sprints
        deleted_efforts = set(modifications.deleted_efforts)
        deleted_sprints = set(modifications.deleted_sprints)

        # Apply modifications to efforts
        original_efforts = session.get('efforts', [])
        modified_efforts = []

        df = session['df']
        time_axis = df['time_sec'].tolist()
        time_array = np.array(time_axis)  # Convert once for efficient lookups
        max_idx = len(time_axis) - 1
        has_power_column = 'power' in df.columns  # Check once outside the loop

        # Reconstruct efforts with modifications
        for effort_data in modifications.efforts:
            # Skip if this effort is marked as deleted in the payload
            if effort_data.deleted:
                continue

            # Find original effort by index if available, otherwise create new
            effort_idx = effort_data.index

            # If the original index is explicitly listed as deleted, do not reintroduce it
            if effort_idx is not None and effort_idx in deleted_efforts:
                continue

            if effort_idx is not None and 0 <= effort_idx < len(original_efforts):
                # Modify existing effort
                orig_start_idx, orig_end_idx, orig_avg_power = original_efforts[effort_idx]

                # Detect if new_start/new_end are indices (small integers) or timestamps (floats > ~1000)
                start_value = float(effort_data.new_start)
                end_value = float(effort_data.new_end)
                
                if start_value < 100000:
                    # Direct indices
                    new_start_idx = int(start_value)
                    new_end_idx = int(end_value)
                else:
                    # Convert timestamps to indices
                    new_start_idx = int(np.argmin(np.abs(time_array - start_value)))
                    new_end_idx = int(np.argmin(np.abs(time_array - end_value)))

                # Clamp to valid bounds
                new_start_idx = max(0, min(new_start_idx, max_idx))
                new_end_idx = max(0, min(new_end_idx, max_idx))

                # Ensure ordering: start < end
                if new_start_idx > new_end_idx:
                    logger.warning(
                        "Swapping reversed indices for effort %s: start %s > end %s",
                        effort_idx,
                        new_start_idx,
                        new_end_idx,
                    )
                    new_start_idx, new_end_idx = new_end_idx, new_start_idx

                # Skip zero-length or invalid efforts
                if new_start_idx == new_end_idx:
                    logger.warning(
                        "Skipping zero-length effort at index %s (start_idx == end_idx == %s)",
                        effort_idx,
                        new_start_idx,
                    )
                    continue

                # Recompute avg_power from the DataFrame slice when possible
                if has_power_column:
                    effort_slice = df.iloc[new_start_idx:new_end_idx]
                    if not effort_slice.empty:
                        avg_power = float(effort_slice['power'].mean())
                    else:
                        avg_power = float(orig_avg_power)
                else:
                    # Fallback to original avg_power if power column is missing
                    avg_power = float(orig_avg_power)

                modified_efforts.append((new_start_idx, new_end_idx, avg_power))
            else:
                # This is a new effort - detect if indices or timestamps
                start_value = float(effort_data.new_start)
                end_value = float(effort_data.new_end)
                
                if start_value < 100000:
                    # Direct indices
                    start_idx = int(start_value)
                    end_idx = int(end_value)
                else:
                    # Convert timestamps to indices
                    start_idx = int(np.argmin(np.abs(time_array - start_value)))
                    end_idx = int(np.argmin(np.abs(time_array - end_value)))

                # Clamp to valid bounds
                start_idx = max(0, min(start_idx, max_idx))
                end_idx = max(0, min(end_idx, max_idx))

                # Ensure ordering: start < end
                if start_idx > end_idx:
                    logger.warning(
                        "Swapping reversed indices for new effort: start %s > end %s",
                        start_idx,
                        end_idx,
                    )
                    start_idx, end_idx = end_idx, start_idx

                # Skip zero-length or invalid efforts
                if start_idx == end_idx:
                    logger.warning(
                        "Skipping zero-length new effort with start_idx == end_idx == %s",
                        start_idx,
                    )
                    continue

                # Recompute avg_power from the DataFrame slice when possible
                if has_power_column:
                    effort_slice = df.iloc[start_idx:end_idx]
                    if not effort_slice.empty:
                        avg_power = float(effort_slice['power'].mean())
                    else:
                        avg_power = float(effort_data.avg_power)
                else:
                    # Fallback to any provided avg_power, if present
                    avg_power = float(effort_data.avg_power)

                modified_efforts.append((start_idx, end_idx, avg_power))

        # Update session with modified efforts
        session['efforts'] = _normalize_efforts(modified_efforts)

        # Process sprints: convert from timestamps to indices
        modified_sprints = []
        
        # Helper function to convert timestamp to index (reuse from efforts processing)
        def get_sprint_closest_idx(timestamp: float) -> int:
            """Find the closest index for a given timestamp."""
            idx = int(np.searchsorted(time_array, timestamp, side='left'))
            if idx <= 0:
                return 0
            if idx >= len(time_array):
                return max_idx
            prev_idx = idx - 1
            if abs(time_array[idx] - timestamp) < abs(time_array[prev_idx] - timestamp):
                return idx
            return prev_idx
        
        for sprint_idx, sprint_data in enumerate(modifications.sprints):
            # Skip if this sprint is marked as deleted
            if sprint_idx in deleted_sprints:
                continue
            
            # Detect if start/end are indices (small integers) or timestamps (floats > ~1000)
            # If they're small integers < 100000, treat them as indices; otherwise convert from timestamps
            start_value = float(sprint_data.start)
            end_value = float(sprint_data.end)
            
            # Heuristic: if value < 100000, likely an index; if > 100000, likely a timestamp
            if start_value < 100000:
                # Direct indices
                start_idx = int(start_value)
                end_idx = int(end_value)
            else:
                # Convert timestamps to indices
                start_idx = get_sprint_closest_idx(start_value)
                end_idx = get_sprint_closest_idx(end_value)
            
            # Ensure valid range
            if end_idx <= start_idx:
                end_idx = start_idx + 1
            if end_idx > max_idx:
                end_idx = max_idx
            if start_idx < 0:
                start_idx = 0
            
            # Use provided avg_power, or calculate from df if not provided
            if sprint_data.avg is not None:
                avg_power = float(sprint_data.avg)
            elif has_power_column:
                power_data = df['power'].iloc[start_idx:end_idx].values
                avg_power = float(np.mean(power_data)) if len(power_data) > 0 else 0.0
            else:
                avg_power = 0.0
            
            # Use provided max_power, or calculate from df if not provided
            if sprint_data.max_power is not None:
                max_power = float(sprint_data.max_power)
            elif has_power_column:
                power_data = df['power'].iloc[start_idx:end_idx].values
                max_power = float(np.max(power_data)) if len(power_data) > 0 else 0.0
            else:
                max_power = 0.0
            
            sprint_dict = {
                'start': start_idx,
                'end': end_idx,
                'label': sprint_data.label,
                'avg': avg_power,
                'max_power': max_power,
                'color': sprint_data.color
            }
            modified_sprints.append(sprint_dict)
        
        session['sprints'] = _normalize_sprints(modified_sprints)

        _invalidate_session_caches(session)
        
        logger.info(f"Successfully imported {len(modified_efforts)} efforts and {len(modified_sprints)} sprints to session {session_id}")

        return {"success": True, "message": f"Imported {len(modified_efforts)} efforts and {len(modified_sprints)} sprints successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error importing modifications: {e}")
        raise HTTPException(status_code=400, detail=f"Error importing modifications: {str(e)}")


@router.get("/export-modifications/{session_id}")
@router.get("/{session_id}/export-modifications")
async def export_modifications(session_id: str, sessions: SessionsDep):
    """
    Export current effort/sprint modifications as JSON (for dashboard download).
    Returns original efforts/sprints as "modifications" that can be imported.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]
    df = session['df']
    efforts = session['efforts']
    sprints = session['sprints']

    # Convert efforts to modification format (keeping indices intact for exact round-trip)
    efforts_modifications = []
    for i, (start_idx, end_idx, avg_power) in enumerate(efforts):
        # Get actual time duration in seconds from DataFrame
        start_time = df['time_sec'].iloc[start_idx] if start_idx < len(df) else 0
        # For end_time, use the timestamp of the LAST included point (end_idx - 1)
        end_time = df['time_sec'].iloc[min(end_idx - 1, len(df) - 1)] if end_idx > 0 else 0
        duration_sec = float(end_time - start_time)
        
        efforts_modifications.append({
            'index': i,
            'new_start': int(start_idx),  # Keep as index
            'new_end': int(end_idx),      # Keep as index
            'duration': duration_sec,     # Actual duration in seconds
            'avg_power': float(avg_power),
            'label': f"Effort {i+1}",
            'deleted': False
        })

    # Convert sprints to modification format (keeping indices intact for exact round-trip)
    sprints_modifications = []
    for i, sprint_dict in enumerate(sprints):
        start_idx = sprint_dict['start']
        end_idx = sprint_dict['end']
        # Get actual time duration in seconds from DataFrame
        start_time = df['time_sec'].iloc[start_idx] if start_idx < len(df) else 0
        # For end_time, use the timestamp of the LAST included point (end_idx - 1)
        end_time = df['time_sec'].iloc[min(end_idx - 1, len(df) - 1)] if end_idx > 0 else 0
        duration_sec = float(end_time - start_time)
        
        sprints_modifications.append({
            'start': int(start_idx),    # Keep as index
            'end': int(end_idx),        # Keep as index
            'label': sprint_dict.get('label', f"Sprint {i+1}"),
            'color': sprint_dict.get('color', '#000000'),
            'avg': float(sprint_dict.get('avg', 0.0)),
            'duration': duration_sec,   # Actual duration in seconds
            'max_power': float(sprint_dict.get('max_power', 0.0))
        })

    # Create modifications JSON
    data = {
        'session_id': session_id,
        'efforts': efforts_modifications,
        'sprints': sprints_modifications,
        'deleted_efforts': [],
        'deleted_sprints': [],
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'total_efforts_original': len(efforts),
        'total_efforts_active': len(efforts),
        'total_sprints_original': len(sprints),
        'total_sprints_active': len(sprints)
    }

    return data


@router.api_route("/export/{session_id}/html-report", methods=["GET", "POST"])
async def export_html_report(session_id: str, request: Request, sessions: SessionsDep):
    """
    Export a fully standalone interactive HTML report identical to the Altimetria D3 tab.
    All data is embedded — no server needed to open it.

    Accepts optional POST body: { "zones": [...] } with user-customized zone colors
    read from localStorage in the browser. If provided, these override the server
    defaults so the report matches exactly what the user sees in the Inspection tab.
    """
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found")

    session = sessions[session_id]

    try:
        from routes.altimetria_d3 import get_chart_data_json

        # Default zones — identical to inspection.html defaultZones.
        # Used whenever the browser does not send valid custom zones.
        DEFAULT_ZONES = [
            {'min': 0,   'max': 60,  'color': '#009e80', 'name': 'Z1'},
            {'min': 60,  'max': 80,  'color': '#009e00', 'name': 'Z2'},
            {'min': 80,  'max': 90,  'color': '#ffcb0e', 'name': 'Z3'},
            {'min': 90,  'max': 105, 'color': '#ff7f0e', 'name': 'Z4'},
            {'min': 105, 'max': 135, 'color': '#dd0447', 'name': 'Z5'},
            {'min': 135, 'max': 300, 'color': '#6633cc', 'name': 'Z6'},
            {'min': 300, 'max': 999, 'color': '#504861', 'name': 'Z7'},
        ]

        chart_data = json.loads(get_chart_data_json(session))

        # Always start with defaults, then override with user's custom values from browser
        chart_data['intensity_zones'] = DEFAULT_ZONES

        if request is not None:
            try:
                body = await request.json()
                if body:
                    if 'zones' in body and isinstance(body['zones'], list) and len(body['zones']) > 0:
                        chart_data['intensity_zones'] = body['zones']
                    if 'cp' in body and body['cp'] and isinstance(body['cp'], (int, float)) and body['cp'] > 0:
                        chart_data['cp'] = float(body['cp'])
                    # Add manual inspection flags
                    if 'efforts_modified' in body:
                        chart_data['efforts_modified'] = bool(body['efforts_modified'])
                    if 'sprints_modified' in body:
                        chart_data['sprints_modified'] = bool(body['sprints_modified'])
            except Exception:
                pass  # No body or JSON parse error — keep defaults

        chart_data_json = json.dumps(chart_data)
        safe_chart_data_json = re.sub(
            r"</script>",
            r"<\\/script>",
            chart_data_json,
            flags=re.IGNORECASE
        )
        filename = session.get('filename', 'Activity')
        filename_escaped = html_module.escape(filename)

        # Read template and substitute Jinja2 placeholders with real values
        template_path = Path(__file__).resolve().parent.parent / "templates" / "altimetria_d3.html"
        html = template_path.read_text(encoding='utf-8')

        html = html.replace('{{ filename }}', filename_escaped)
        html = html.replace('{{ chart_data_json | safe }}', safe_chart_data_json)

        # Best effort: inline D3 so the exported report does not depend on network/CDN.
        d3_url = "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"
        d3_tag_pattern = r'<script\s+src="https://cdnjs\.cloudflare\.com/ajax/libs/d3/7\.9\.0/d3\.min\.js"></script>'
        try:
            with urllib.request.urlopen(d3_url, timeout=8) as resp:
                d3_js = resp.read().decode('utf-8')
            html = re.sub(
                d3_tag_pattern,
                lambda _m: f"<script>\n{d3_js}\n</script>",
                html,
                count=1,
            )
        except Exception:
            logger.warning("Could not inline d3.min.js in exported HTML; keeping CDN reference", exc_info=True)

        # Inline local scripts so the exported report works fully offline.
        # Without this, /static/js URLs are broken when opening the file directly.
        static_js_dir = Path(__file__).resolve().parent.parent / "static" / "js"
        try:
            peffort_common_js = (static_js_dir / "peffort_common.js").read_text(encoding='utf-8')
            html = re.sub(
                r'<script\s+src="/static/js/peffort_common\.js(?:\?v=[^"]+)?"></script>',
                lambda _m: f"<script>\n{peffort_common_js}\n</script>",
                html,
                count=1,
            )
        except Exception:
            logger.warning("Could not inline peffort_common.js in exported HTML", exc_info=True)

        try:
            altimetria_d3_js = (static_js_dir / "altimetria_d3.js").read_text(encoding='utf-8')
            html = re.sub(
                r'<script\s+src="/static/js/altimetria_d3\.js(?:\?v=[^"]+)?"></script>',
                lambda _m: f"<script>\n{altimetria_d3_js}\n</script>",
                html,
                count=1,
            )
        except Exception:
            logger.warning("Could not inline altimetria_d3.js in exported HTML", exc_info=True)

        # Remove the storage listener (irrelevant in a standalone file)
        storage_block = re.search(
            r'<script>\s*// ── storage listener.*?</script>',
            html, re.DOTALL
        )
        if storage_block:
            html = html.replace(storage_block.group(0), '')

        # Remove Jinja2 block tags left in the template
        html = html.replace('{% raw %}', '').replace('{% endraw %}', '')

        # Replace session placeholder also after script inlining
        # because inline JS may contain the same token.
        html = html.replace('{{ session_id }}', session_id)

        # Add a slim header banner
        export_banner = f"""
<div id="export-banner" style="
    position: fixed; top: 0; left: 0; right: 0; z-index: 9999;
    background: linear-gradient(135deg, #1e293b, #0f172a);
    color: #94a3b8; font-size: 11px; padding: 4px 12px;
    display: flex; justify-content: space-between; align-items: center;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    border-bottom: 1px solid #334155;
">
    <span>🚴 <strong style="color:#60a5fa">PEFFORT Report</strong> — {filename_escaped}</span>
    <span style="color:#475569">Exported interactive report · bFactor</span>
</div>
<style>
    #container {{ margin-top: 28px; height: calc(100vh - 28px) !important; }}
    html, body {{ overflow: hidden; }}
</style>
"""
        html = html.replace('<body>', '<body>' + export_banner, 1)

        safe_name = re.sub(r'[^\w.\-]', '_', filename.replace('.fit', '')).strip('_') or 'report'
        return StreamingResponse(
            BytesIO(html.encode('utf-8')),
            media_type="text/html",
            headers={
                "Content-Disposition": f'attachment; filename="peffort_report_{safe_name}.html"'
            }
        )

    except Exception as e:
        logger.error(f"Error generating HTML report: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error generating report: {str(e)}")


__all__ = [
    'router',
    'setup_api_router',
    'redetect_efforts_impl',
    'redetect_sprints_impl',
    'import_modifications',
    'import_dashboard_modifications',
    'export_modifications',
]
