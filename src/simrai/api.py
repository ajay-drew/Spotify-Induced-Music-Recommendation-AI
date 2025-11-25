"""
FastAPI microservice for SIMRAI.

Exposes a simple JSON API:

- POST /queue
  Request body:
    {
      "mood": "rainy midnight drive with someone you miss",
      "length": 12,
      "intense": false,
      "soft": false
    }
  Response body:
    {
      "mood": "...",
      "mood_vector": {"valence": 0.4, "energy": 0.3},
      "summary": "This queue starts ...",
      "tracks": [
        {
          "name": "...",
          "artists": "...",
          "uri": "spotify:track:...",
          "valence": 0.42,
          "energy": 0.35
        },
        ...
      ]
    }
"""

from __future__ import annotations

import logging
from typing import List, Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel
import secrets
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .config import load_config, get_default_config_dir
from .pipeline import QueueResult, QueueTrack, generate_queue
from .spotify import SpotifyError

logger = logging.getLogger(__name__)

# Rate limiter to prevent hitting Spotify/Groq API limits
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SIMRAI API",
    description="SIMRAI – Spotify-Induced Music Recommendation AI (metadata-only, read-only).",
    version="0.1.0",
)

# Add rate limit handler and middleware
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# Allow local web frontends (e.g. React dev server on localhost:5658) and the hosted
# Render static site (https://simrai.onrender.com) to call the API.
# Credentials enabled for session cookies.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5658",
        "http://127.0.0.1:5658",
        "https://simrai.onrender.com",
    ],
    allow_credentials=True,  # Required for cookies
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueueRequest(BaseModel):
    mood: str
    length: int = 12
    intense: bool = False
    soft: bool = False


class QueueTrackOut(BaseModel):
    name: str
    artists: str
    uri: str
    valence: float
    energy: float


class MoodVectorOut(BaseModel):
    valence: float
    energy: float


class QueueResponse(BaseModel):
    mood: str
    mood_vector: MoodVectorOut
    summary: str
    tracks: List[QueueTrackOut]


@app.get("/health", tags=["system"])
def health() -> dict:
    logger.debug("Health check endpoint called")
    return {"status": "ok"}


@limiter.limit("10/minute")  # Max 10 queue generations per minute per IP
@app.post("/queue", response_model=QueueResponse, tags=["queue"])
def create_queue(body: QueueRequest, request: Request) -> QueueResponse:
    logger.info(f"API queue request: mood={body.mood!r}, length={body.length}, intense={body.intense}, soft={body.soft}")
    try:
        # generate_queue automatically tries AI if available, falls back to rule-based
        result: QueueResult = generate_queue(
            body.mood,
            length=body.length,
            intense=body.intense,
            soft=body.soft,
        )
        logger.info(f"API queue generated: {len(result.tracks)} tracks")
    except SpotifyError as exc:
        logger.error(f"Spotify error in API queue endpoint: {exc}")
        raise HTTPException(status_code=502, detail=f"Spotify error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - safety net
        logger.exception(f"Internal error in API queue endpoint: {exc}")
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    if not result.tracks:
        logger.warning(f"No tracks found for API queue request: mood={body.mood!r}")
        # Return 200 with empty list; the client can decide what to do.
        return QueueResponse(
            mood=result.mood_text,
            mood_vector=MoodVectorOut(
                valence=result.mood_vector.valence,
                energy=result.mood_vector.energy,
            ),
            summary=result.summary,
            tracks=[],
        )

    tracks: List[QueueTrackOut] = [
        QueueTrackOut(
            name=t.name,
            artists=t.artists,
            uri=t.uri,
            valence=t.valence,
            energy=t.energy,
        )
        for t in result.tracks
    ]

    return QueueResponse(
        mood=result.mood_text,
        mood_vector=MoodVectorOut(
            valence=result.mood_vector.valence,
            energy=result.mood_vector.energy,
        ),
        summary=result.summary,
        tracks=tracks,
    )


SPOTIFY_AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

_oauth_http = httpx.Client(timeout=10.0)
_cfg = load_config()
_config_dir = get_default_config_dir()
_tokens_dir = _config_dir / "spotify_tokens"  # Directory for per-user tokens
_oauth_states: dict[str, float] = {}  # state -> timestamp (for expiry cleanup)
_sessions: dict[str, str] = {}  # session_id -> user_id mapping


class SearchRequest(BaseModel):
    query: str
    type: str = "track"
    limit: int = 20


class CreatePlaylistRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    public: bool = False


class AddTracksRequest(BaseModel):
    playlist_id: str
    uris: List[str]


class SpotifyUserOut(BaseModel):
    id: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None


class UnlinkSpotifyOut(BaseModel):
    status: str


def _get_token_path(user_id: str) -> Path:
    """Get the token file path for a specific user."""
    _tokens_dir.mkdir(parents=True, exist_ok=True)
    # Use user_id as filename (sanitized)
    safe_user_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in user_id)
    return _tokens_dir / f"{safe_user_id}.json"


def _load_tokens(user_id: str) -> Optional[dict]:
    """Load tokens for a specific user."""
    token_path = _get_token_path(user_id)
    if not token_path.exists():
        return None
    try:
        import json

        with token_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save_tokens(user_id: str, data: dict) -> None:
    """Save tokens for a specific user."""
    import json

    token_path = _get_token_path(user_id)
    _tokens_dir.mkdir(parents=True, exist_ok=True)
    with token_path.open("w", encoding="utf-8") as f:
        json.dump(data, f)


def _delete_tokens(user_id: str) -> None:
    """Delete tokens for a specific user."""
    token_path = _get_token_path(user_id)
    try:
        token_path.unlink()
    except FileNotFoundError:
        pass


def _get_session_user_id(request: Request) -> str:
    """
    Get the user_id for the current session from cookies.
    Raises HTTPException if no session found.
    """
    session_id = request.cookies.get("simrai_session")
    if not session_id or session_id not in _sessions:
        logger.warning("No valid session found in request")
        raise HTTPException(
            status_code=401,
            detail="No active session. Please connect your Spotify account."
        )
    return _sessions[session_id]


def _get_user_access_token(user_id: str) -> str:
    """
    Return a valid user access token for a specific user, refreshing if needed.

    This keeps tokens on disk under the user's config dir and never exposes
    them to the frontend. Supports multiple concurrent users.
    """
    import time

    tokens = _load_tokens(user_id)
    if not tokens:
        logger.warning(f"User access token requested for {user_id} but no tokens found")
        raise HTTPException(status_code=401, detail="Spotify is not connected. Visit /auth/login.")

    access_token = tokens.get("access_token")
    expires_at = tokens.get("expires_at")
    refresh_token = tokens.get("refresh_token")

    if not access_token or not expires_at or not refresh_token:
        logger.warning(f"User access token requested for {user_id} but tokens are invalid")
        raise HTTPException(status_code=401, detail="Spotify tokens are invalid. Reconnect via /auth/login.")

    if time.time() < float(expires_at) - 10:
        logger.debug(f"Using cached access token for {user_id}")
        return access_token

    # Refresh
    logger.info(f"Refreshing expired access token for {user_id}")
    if not _cfg.spotify.client_id or not _cfg.spotify.client_secret:
        logger.error("Cannot refresh token: client ID/secret missing")
        raise HTTPException(status_code=500, detail="Spotify client ID/secret missing for refresh.")

    try:
        resp = _oauth_http.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
            auth=(_cfg.spotify.client_id, _cfg.spotify.client_secret),
        )
    except httpx.HTTPError as exc:
        logger.error(f"Failed to contact Spotify token endpoint for refresh: {exc}")
        raise HTTPException(status_code=502, detail=f"Failed to contact Spotify token endpoint: {exc}") from exc

    if resp.status_code != 200:
        logger.error(f"Spotify token refresh failed: {resp.status_code} {resp.text}")
        raise HTTPException(
            status_code=502,
            detail=f"Spotify token refresh failed: {resp.status_code} {resp.text}",
        )

    data = resp.json()
    new_access_token = data.get("access_token")
    expires_in = int(data.get("expires_in", 3600))

    if not new_access_token:
        logger.error("Spotify token refresh response missing access_token")
        raise HTTPException(status_code=502, detail="Spotify token refresh response missing access_token.")

    import time as _t

    tokens["access_token"] = new_access_token
    tokens["expires_at"] = _t.time() + expires_in
    _save_tokens(user_id, tokens)
    logger.info(f"Access token refreshed successfully for {user_id}")
    return new_access_token


@app.get("/auth/login", tags=["auth"])
def auth_login() -> RedirectResponse:
    """
    Redirect the user to Spotify's authorize page to connect their account.

    This is designed for local use: visit http://localhost:8000/auth/login
    in your browser, approve the app, and then come back to SIMRAI.
    """
    from urllib.parse import urlencode
    import secrets
    import time

    logger.info("OAuth login initiated")
    client_id = _cfg.spotify.client_id
    # Redirect URI is managed in the Spotify Developer dashboard; SIMRAI always
    # uses the standard local callback path.
    redirect_uri = "http://localhost:8000/auth/callback"

    if not client_id:
        logger.error("OAuth login failed: SIMRAI_SPOTIFY_CLIENT_ID not set")
        raise HTTPException(
            status_code=500,
            detail="SIMRAI_SPOTIFY_CLIENT_ID is not set. Cannot start OAuth login.",
        )

    # Generate unique state for this OAuth flow (prevents race conditions)
    state = secrets.token_urlsafe(32)
    _oauth_states[state] = time.time()
    
    # Clean up expired states (older than 10 minutes)
    current_time = time.time()
    expired_states = [s for s, t in _oauth_states.items() if current_time - t > 600]
    for s in expired_states:
        del _oauth_states[s]
    
    scopes = "playlist-modify-private playlist-modify-public"
    logger.debug(f"OAuth state generated: {state[:8]}..., redirect_uri={redirect_uri}")

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
        "show_dialog": "true",  # Force consent screen + account picker every time
    }
    url = f"{SPOTIFY_AUTHORIZE_URL}?{urlencode(params)}"
    logger.info("Redirecting to Spotify authorization page with explicit consent")
    return RedirectResponse(url, status_code=302)


@app.get("/auth/callback", tags=["auth"])
def auth_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    error_description: Optional[str] = Query(None),
) -> HTMLResponse:
    """
    Spotify redirects here after the user approves or denies access.

    Only connects if the user explicitly approved. If denied, shows an error message.
    """
    global _last_oauth_state

    # Check if user denied access
    if error:
        error_msg = error_description or error
        logger.warning(f"OAuth callback: user denied access - {error_msg}")
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>SIMRAI – Connection Denied</title>
            <style>
              body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 1.5rem;
                background: #1e1e1e;
                color: #cccccc;
                text-align: center;
              }}
              h1 {{ color: #f48771; }}
            </style>
          </head>
          <body>
            <h1>Connection Denied</h1>
            <p>You chose not to connect your Spotify account.</p>
            <p style="color: #858585; font-size: 0.9em;">{error_msg}</p>
            <script>
              try {{
                if (window.opener) {{
                  window.opener.postMessage({{ type: "simrai-spotify-denied", error: "{error}" }}, "*");
                }}
                setTimeout(function () {{ window.close(); }}, 2000);
              }} catch (e) {{
                // ignore
              }}
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    # User must have approved - verify we have the authorization code
    if not code:
        logger.warning("OAuth callback: no authorization code received")
        html = """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>SIMRAI – Connection Error</title>
            <style>
              body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 1.5rem;
                background: #1e1e1e;
                color: #cccccc;
                text-align: center;
              }
              h1 { color: #f48771; }
            </style>
          </head>
          <body>
            <h1>Connection Error</h1>
            <p>No authorization code received. Please try again.</p>
            <script>
              setTimeout(function () { window.close(); }, 2000);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    if not _cfg.spotify.client_id or not _cfg.spotify.client_secret:
        raise HTTPException(
            status_code=500,
            detail="Spotify client ID/secret are not configured.",
        )

    if not _cfg.spotify.redirect_uri:
        redirect_uri = "http://localhost:8000/auth/callback"
    else:
        redirect_uri = _cfg.spotify.redirect_uri

    # Verify state to prevent CSRF attacks (supports concurrent OAuth flows)
    if not state or state not in _oauth_states:
        logger.error(f"OAuth callback: invalid or expired state (CSRF protection)")
        html = """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>SIMRAI – Security Error</title>
            <style>
              body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 1.5rem;
                background: #1e1e1e;
                color: #cccccc;
                text-align: center;
              }
              h1 { color: #f48771; }
            </style>
          </head>
          <body>
            <h1>Security Error</h1>
            <p>Invalid OAuth state. Please try connecting again.</p>
            <script>
              setTimeout(function () { window.close(); }, 2000);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)
    
    # Remove used state to prevent replay attacks
    del _oauth_states[state]

    # Exchange authorization code for tokens (only happens if user approved)
    logger.info("Exchanging authorization code for tokens")
    try:
        resp = _oauth_http.post(
            SPOTIFY_TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
            auth=(_cfg.spotify.client_id, _cfg.spotify.client_secret),
        )
    except httpx.HTTPError as exc:
        logger.error(f"Failed to contact Spotify token endpoint: {exc}")
        raise HTTPException(status_code=502, detail=f"Failed to contact Spotify token endpoint: {exc}") from exc

    if resp.status_code != 200:
        logger.error(f"Spotify token exchange failed: {resp.status_code} {resp.text}")
        html = f"""
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>SIMRAI – Connection Error</title>
            <style>
              body {{
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 1.5rem;
                background: #1e1e1e;
                color: #cccccc;
                text-align: center;
              }}
              h1 {{ color: #f48771; }}
            </style>
          </head>
          <body>
            <h1>Connection Error</h1>
            <p>Failed to exchange authorization code for tokens.</p>
            <p style="color: #858585; font-size: 0.9em;">Status: {resp.status_code}</p>
            <script>
              setTimeout(function () {{ window.close(); }}, 2000);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    data = resp.json()
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    expires_in = int(data.get("expires_in", 3600))

    if not access_token or not refresh_token:
        logger.error("Spotify token response missing required tokens")
        html = """
        <!DOCTYPE html>
        <html lang="en">
          <head>
            <meta charset="utf-8" />
            <title>SIMRAI – Connection Error</title>
            <style>
              body {
                font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding: 1.5rem;
                background: #1e1e1e;
                color: #cccccc;
                text-align: center;
              }
              h1 { color: #f48771; }
            </style>
          </head>
          <body>
            <h1>Connection Error</h1>
            <p>Spotify response missing required tokens.</p>
            <script>
              setTimeout(function () { window.close(); }, 2000);
            </script>
          </body>
        </html>
        """
        return HTMLResponse(content=html)

    # Get user ID to save tokens per-user (supports concurrent users)
    import time
    
    logger.info("OAuth callback successful, fetching user ID")
    try:
        me_resp = _oauth_http.get(
            f"{SPOTIFY_API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Failed to fetch user ID: {exc}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch user ID: {exc}") from exc
    
    if not me_resp.is_success:
        logger.error(f"Failed to fetch user ID: {me_resp.status_code} {me_resp.text}")
        raise HTTPException(status_code=502, detail=f"Failed to fetch user ID: {me_resp.text}")
    
    user_id = me_resp.json().get("id")
    if not user_id:
        logger.error("Spotify /me response missing user id")
        raise HTTPException(status_code=502, detail="Spotify /me response missing user id.")
    
    logger.info(f"Saving tokens for user: {user_id}")
    token_data = {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": time.time() + expires_in,
        "scope": data.get("scope"),
        "token_type": data.get("token_type"),
        "user_id": user_id,  # Store user_id with tokens
    }
    _save_tokens(user_id, token_data)
    
    # Create session for this user
    session_id = secrets.token_urlsafe(32)
    _sessions[session_id] = user_id
    logger.info(f"Created session for user: {user_id}")

    # Return success page with session cookie
    html = """
    <!DOCTYPE html>
    <html lang="en">
      <head>
        <meta charset="utf-8" />
        <title>SIMRAI – Spotify Connected</title>
        <style>
          body {
            font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            padding: 1.5rem;
            background: #1e1e1e;
            color: #cccccc;
            text-align: center;
          }
          h1 { color: #4ec9b0; }
        </style>
      </head>
      <body>
        <h1>Spotify Connected ✅</h1>
        <p>Your Spotify account has been connected successfully.</p>
        <p style="color: #858585; font-size: 0.9em;">You can close this window and return to SIMRAI.</p>
        <script>
          try {
            if (window.opener) {
              window.opener.postMessage({ type: "simrai-spotify-connected" }, "*");
            }
            // Give the opener a moment to process, then close.
            setTimeout(function () { window.close(); }, 1500);
          } catch (e) {
            // ignore
          }
        </script>
      </body>
    </html>
    """
    response = HTMLResponse(content=html)
    # Set session cookie (httponly for security, samesite=lax for OAuth callback)
    response.set_cookie(
        key="simrai_session",
        value=session_id,
        httponly=True,
        samesite="lax",
        max_age=86400 * 30,  # 30 days
    )
    return response


@app.post("/api/search", tags=["spotify"])
def api_search(body: SearchRequest, request: Request) -> JSONResponse:
    """
    Proxy to Spotify's search endpoint using the connected user's access token.
    """
    logger.info(f"API search request: query={body.query!r}, type={body.type}, limit={body.limit}")
    user_id = _get_session_user_id(request)
    token = _get_user_access_token(user_id)

    params = {
        "q": body.query,
        "type": body.type,
        "limit": max(1, min(body.limit, 50)),
    }

    try:
        resp = _oauth_http.get(
            f"{SPOTIFY_API_BASE_URL}/search",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Error calling Spotify search API: {exc}")
        raise HTTPException(status_code=502, detail=f"Error calling Spotify search: {exc}") from exc

    if not resp.is_success:
        logger.error(f"Spotify search API error: {resp.status_code} {resp.text}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Spotify search error: {resp.text}",
        )

    logger.debug(f"Spotify search successful: {len(resp.json().get('tracks', {}).get('items', []))} results")
    return JSONResponse(resp.json())


@app.get("/api/me", response_model=SpotifyUserOut, tags=["spotify"])
def api_me(request: Request) -> SpotifyUserOut:
    """
    Return basic profile information for the connected Spotify user.
    """
    logger.debug("API /me endpoint called")
    user_id = _get_session_user_id(request)
    token = _get_user_access_token(user_id)

    try:
        resp = _oauth_http.get(
            f"{SPOTIFY_API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Error calling Spotify /me API: {exc}")
        raise HTTPException(status_code=502, detail=f"Error calling Spotify /me: {exc}") from exc

    if not resp.is_success:
        logger.error(f"Spotify /me API error: {resp.status_code} {resp.text}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Spotify /me error: {resp.text}",
        )

    data = resp.json()
    images = data.get("images") or []
    avatar_url: Optional[str] = None
    if isinstance(images, list) and images and isinstance(images[0], dict):
        avatar_url = images[0].get("url")

    user_id = data.get("id") or ""
    display_name = data.get("display_name")
    logger.info(f"Retrieved Spotify user profile: {user_id} ({display_name})")

    return SpotifyUserOut(id=user_id, display_name=display_name, avatar_url=avatar_url)


@app.post("/api/unlink-spotify", response_model=UnlinkSpotifyOut, tags=["spotify"])
def api_unlink_spotify(request: Request, response: Response) -> UnlinkSpotifyOut:
    """
    "Unlink" the Spotify account for this SIMRAI instance by deleting stored tokens.

    This does not revoke the token server-side with Spotify, but it ensures SIMRAI
    no longer has access until the user connects again.
    """
    logger.info("Unlinking Spotify account")
    
    # Get user_id from session
    session_id = request.cookies.get("simrai_session")
    if session_id and session_id in _sessions:
        user_id = _sessions[session_id]
        _delete_tokens(user_id)
        del _sessions[session_id]
        logger.info(f"Spotify tokens deleted for user: {user_id}")
    
    # Clear session cookie
    response.delete_cookie("simrai_session")

    return UnlinkSpotifyOut(status="unlinked")


@limiter.limit("5/minute")  # Max 5 playlist creations per minute per IP
@app.post("/api/create-playlist", tags=["spotify"])
def api_create_playlist(body: CreatePlaylistRequest, request: Request) -> JSONResponse:
    """
    Create a playlist in the connected user's Spotify account.
    """
    logger.info(f"Creating playlist: name={body.name!r}, description={body.description!r}, public={body.public}")
    user_id = _get_session_user_id(request)
    token = _get_user_access_token(user_id)

    try:
        me_resp = _oauth_http.get(
            f"{SPOTIFY_API_BASE_URL}/me",
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Error calling Spotify /me for playlist creation: {exc}")
        raise HTTPException(status_code=502, detail=f"Error calling Spotify /me: {exc}") from exc

    if not me_resp.is_success:
        logger.error(f"Spotify /me error during playlist creation: {me_resp.status_code} {me_resp.text}")
        raise HTTPException(
            status_code=me_resp.status_code,
            detail=f"Spotify /me error: {me_resp.text}",
        )

    user_id = me_resp.json().get("id")
    if not user_id:
        logger.error("Spotify /me response missing user id")
        raise HTTPException(status_code=502, detail="Spotify /me response missing user id.")

    name = body.name or "SIMRAI Playlist"
    description = body.description or "Brewed by SIMRAI"

    payload = {
        "name": name,
        "description": description,
        "public": body.public,
    }

    try:
        pl_resp = _oauth_http.post(
            f"{SPOTIFY_API_BASE_URL}/users/{user_id}/playlists",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Error creating Spotify playlist: {exc}")
        raise HTTPException(status_code=502, detail=f"Error creating Spotify playlist: {exc}") from exc

    if not pl_resp.is_success:
        logger.error(f"Spotify create playlist error: {pl_resp.status_code} {pl_resp.text}")
        raise HTTPException(
            status_code=pl_resp.status_code,
            detail=f"Spotify create playlist error: {pl_resp.text}",
        )

    data = pl_resp.json()
    playlist_id = data.get("id")
    external_url = data.get("external_urls", {}).get("spotify")
    logger.info(f"Playlist created successfully: {playlist_id} ({external_url})")

    return JSONResponse(
        {
            "playlist_id": playlist_id,
            "url": external_url,
        }
    )


@limiter.limit("10/minute")  # Max 10 track additions per minute per IP
@app.post("/api/add-tracks", tags=["spotify"])
def api_add_tracks(body: AddTracksRequest, request: Request) -> JSONResponse:
    """
    Add tracks to an existing Spotify playlist for the connected user.
    """
    logger.info(f"Adding {len(body.uris)} tracks to playlist: {body.playlist_id}")
    user_id = _get_session_user_id(request)
    token = _get_user_access_token(user_id)

    if not body.uris:
        logger.warning("Add tracks request with no URIs provided")
        raise HTTPException(status_code=400, detail="No track URIs provided.")

    payload = {"uris": body.uris}

    try:
        resp = _oauth_http.post(
            f"{SPOTIFY_API_BASE_URL}/playlists/{body.playlist_id}/tracks",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
    except httpx.HTTPError as exc:
        logger.error(f"Error adding tracks to Spotify playlist: {exc}")
        raise HTTPException(status_code=502, detail=f"Error adding tracks to Spotify playlist: {exc}") from exc

    if not resp.is_success:
        logger.error(f"Spotify add tracks error: {resp.status_code} {resp.text}")
        raise HTTPException(
            status_code=resp.status_code,
            detail=f"Spotify add tracks error: {resp.text}",
        )

    data = resp.json()
    logger.info(f"Tracks added successfully to playlist {body.playlist_id}")
    return JSONResponse({"snapshot_id": data.get("snapshot_id")})
