"""Sign in with Google, and only the emails in ALLOWED_EMAILS get in.

On Cloud Run deploy.sh sets these (the secrets come from Secret Manager):
    ALLOWED_EMAILS        "you@gmail.com" (comma-separated for more than one)
    GOOGLE_CLIENT_ID      the OAuth client made in the Google Cloud console (see DEPLOY.md)
    GOOGLE_CLIENT_SECRET  its secret
    SECRET_KEY            signs the session cookie
    TASKS_AUDIENCE, SCHEDULER_EMAIL   who may call /tasks/… (the nightly Cloud Scheduler job)

Without ALLOWED_EMAILS there is no sign-in at all, which is fine on your own computer (127.0.0.1) but never
on Cloud Run: there the app refuses to start rather than run open.

The flow is Google's standard one for websites: /login sends you to Google, Google sends you back to
/auth/callback with a one-time code, the server swaps it for a signed ID token, checks it and the email,
and keeps you signed in with a cookie for SESSION_DAYS.
"""
import os
import secrets
from datetime import timedelta
from functools import wraps
from urllib.parse import urlencode

import requests
from flask import Blueprint, abort, jsonify, redirect, request, session, url_for
from google.auth.transport.requests import Request
from google.oauth2 import id_token

ALLOWED = {e.strip().lower() for e in os.environ.get("ALLOWED_EMAILS", "").split(",") if e.strip()}
CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
ON_CLOUD_RUN = bool(os.environ.get("K_SERVICE"))
SESSION_DAYS = 90
GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"

# Anyone may fetch these: they hold no data, and browsers ask for some of them without the cookie
PUBLIC = {"/login", "/auth/callback", "/logout", "/manifest.webmanifest", "/icon.svg", "/sw.js"}

bp = Blueprint("auth", __name__)


def init(app):
    if not ALLOWED:
        if ON_CLOUD_RUN:
            raise RuntimeError("ALLOWED_EMAILS is not set: refusing to run on Cloud Run without sign-in")
        return
    if not (CLIENT_ID and CLIENT_SECRET and os.environ.get("SECRET_KEY")):
        raise RuntimeError("ALLOWED_EMAILS is set, so GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and SECRET_KEY are needed")
    app.secret_key = os.environ["SECRET_KEY"]
    app.config.update(SESSION_COOKIE_SECURE=ON_CLOUD_RUN, SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(days=SESSION_DAYS))
    app.register_blueprint(bp)
    app.before_request(_require_sign_in)


def _require_sign_in():
    path = request.path
    if path in PUBLIC or path.startswith("/tasks/") or session.get("email") in ALLOWED:
        return None
    if path.startswith(("/api/", "/receipts/")):
        return jsonify({"error": "Signed out"}), 401
    return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))


def _safe_next(target):
    """Only ever go back to a page of this site after signing in."""
    return target if target and target.startswith("/") and not target.startswith("//") else "/"


@bp.get("/login")
def login():
    session["state"], session["nonce"] = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    session["next"] = _safe_next(request.args.get("next"))
    return redirect(GOOGLE_AUTH + "?" + urlencode({
        "client_id": CLIENT_ID, "redirect_uri": url_for("auth.callback", _external=True),
        "response_type": "code", "scope": "openid email", "state": session["state"],
        "nonce": session["nonce"], "prompt": "select_account"}))


@bp.get("/auth/callback")
def callback():
    if not request.args.get("code") or request.args.get("state") != session.pop("state", None):
        abort(400, "Sign-in expired or was started elsewhere: go back and try again.")
    r = requests.post(GOOGLE_TOKEN, timeout=15, data={
        "code": request.args["code"], "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": url_for("auth.callback", _external=True), "grant_type": "authorization_code"})
    if not r.ok:
        abort(400, f"Google refused the sign-in: {r.text[:200]}")
    claims = id_token.verify_oauth2_token(r.json()["id_token"], Request(), CLIENT_ID)
    email = (claims.get("email") or "").lower()
    if claims.get("nonce") != session.pop("nonce", None) or not claims.get("email_verified"):
        abort(400, "Sign-in could not be verified: try again.")
    if email not in ALLOWED:
        abort(403, f"{email} is not allowed to use this app.")
    back_to = _safe_next(session.get("next"))
    session.clear()
    session.permanent = True
    session["email"] = email
    return redirect(back_to)


@bp.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def task(fn):
    """For /tasks/… routes: only the Cloud Scheduler job (or anyone, when there is no sign-in at all)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if ALLOWED:
            header = request.headers.get("Authorization", "")
            if not os.environ.get("TASKS_AUDIENCE"):  # without it any Google token's audience would pass
                abort(403)
            try:
                claims = id_token.verify_oauth2_token(header.removeprefix("Bearer "), Request(),
                                                      os.environ.get("TASKS_AUDIENCE"))
            except ValueError:
                abort(403)
            if claims.get("email") != os.environ.get("SCHEDULER_EMAIL") or not claims.get("email_verified"):
                abort(403)
        return fn(*args, **kwargs)
    return wrapper
