"""
Home route - FIT file upload form
"""

import logging
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from dependencies import SessionsDep

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Jinja2 templates - set by setup_home_router()
_templates: Jinja2Templates = None


def setup_home_router(sessions_dict: Dict[str, Any], templates_dir: Path = None):
    """Setup the home router with shared sessions dictionary and templates"""
    global _templates

    if templates_dir is None:
        templates_dir = Path(__file__).parent.parent / "templates"
    _templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/")
async def home(request: Request, sessions: SessionsDep):
    """Home page with FIT file upload form"""
    _ = sessions
    return _templates.TemplateResponse(
        request=request,
        name="home.html",
        context={"request": request}
    )
