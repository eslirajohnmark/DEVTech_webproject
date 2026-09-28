"""CSRF token helper.

Registered in app.py as:
    app.jinja_env.globals['csrf_token'] = generate_csrf

Every technician template puts it into a <meta> tag so the JS layer
can read it and attach it as X-CSRFToken on every fetch().
"""
from flask_wtf.csrf import generate_csrf


def inject_csrf_token():
    """Context processor form. Returns a dict that gets merged into
    every Jinja render context."""
    return dict(csrf_token=generate_csrf)