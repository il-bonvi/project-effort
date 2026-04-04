"""FastAPI dependencies shared across route modules."""

from typing import Dict, Any, Annotated

from fastapi import Depends, HTTPException, Request


def get_sessions(request: Request) -> Dict[str, Dict[str, Any]]:
    sessions = getattr(request.app.state, "sessions", None)
    if sessions is None:
        raise HTTPException(status_code=500, detail="Session store not initialized")
    return sessions


SessionsDep = Annotated[Dict[str, Dict[str, Any]], Depends(get_sessions)]
