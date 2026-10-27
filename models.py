from __future__ import annotations

from functools import wraps

from flask import abort, redirect, request, session, url_for

from database import get_db


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    db = get_db()
    return db.execute("SELECT * FROM users WHERE id = ? AND active = 1", (user_id,)).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapped(*args, **kwargs):
            user = current_user()
            if user is None or user["role"] not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator
