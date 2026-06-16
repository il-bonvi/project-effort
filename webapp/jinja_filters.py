"""
jinja_filters.py — Custom Jinja2 filters for peffort templates.
Register in app.py with:
    from jinja_filters import register_filters
    register_filters(templates)
"""


def duration_filter(seconds) -> str:
    """Convert integer seconds to mm:ss or h:mm:ss."""
    try:
        s = int(seconds)
    except (TypeError, ValueError):
        return "—"
    if s < 0:
        return "—"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def register_filters(templates):
    """
    Call this after creating Jinja2Templates instance.

    Example in app.py / main.py:
        templates = Jinja2Templates(directory="templates")
        from jinja_filters import register_filters
        register_filters(templates)
    """
    templates.env.filters["duration"] = duration_filter
