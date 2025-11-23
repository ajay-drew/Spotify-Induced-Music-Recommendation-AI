"""
Small standalone CLI to explore Spotify track metadata for a given song.

Usage (from repo root, after setting SIMRAI_SPOTIFY_CLIENT_ID/SECRET in .env):

    python dummy/track_metadata_cli.py "rainy midnight drive"

This is a learning tool: it shows which pieces of metadata (and, where
available, audio features and artist genres) Spotify exposes for tracks.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Any, Dict, List, Optional

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table


SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE_URL = "https://api.spotify.com/v1"

app = typer.Typer(help="Inspect Spotify track metadata for learning about songs and genres.")
console = Console()


def _get_access_token() -> str:
    """Obtain a client-credentials access token using env-configured app keys."""
    load_dotenv()
    client_id = os.getenv("SIMRAI_SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SIMRAI_SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        console.print(
            "[red]SIMRAI_SPOTIFY_CLIENT_ID / SIMRAI_SPOTIFY_CLIENT_SECRET are missing.[/red]\n"
            "Add them to a .env file in the project root or export them in your shell."
        )
        raise typer.Exit(1)

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
    with httpx.Client(timeout=10.0) as client:
        resp = client.post(
            SPOTIFY_TOKEN_URL,
            data={"grant_type": "client_credentials"},
            headers={"Authorization": f"Basic {auth_header}"},
        )
    if resp.status_code != 200:
        console.print(
            f"[red]Failed to obtain Spotify token:[/red] {resp.status_code} {resp.text}"
        )
        raise typer.Exit(1)

    data = resp.json()
    token = data.get("access_token")
    if not token:
        console.print("[red]Spotify token response missing access_token.[/red]")
        raise typer.Exit(1)
    return token


def _search_tracks(token: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
    """Search for tracks by free-text query."""
    params = {"q": query, "type": "track", "limit": max(1, min(limit, 10))}
    headers = {"Authorization": f"Bearer {token}"}
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(f"{SPOTIFY_API_BASE_URL}/search", params=params, headers=headers)
    if not resp.is_success:
        console.print(
            f"[red]Spotify search error:[/red] {resp.status_code} {resp.text}"
        )
        raise typer.Exit(1)
    return resp.json().get("tracks", {}).get("items", []) or []


def _fetch_audio_features(token: str, track_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Try to fetch audio features (danceability, energy, valence, tempo, etc.).

    Some newer Spotify apps are blocked from this endpoint; we handle 403/other
    failures gracefully and return an empty mapping.
    """
    if not track_ids:
        return {}

    headers = {"Authorization": f"Bearer {token}"}
    params = {"ids": ",".join(track_ids[:100])}
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{SPOTIFY_API_BASE_URL}/audio-features",
            params=params,
            headers=headers,
        )
    if not resp.is_success:
        console.print(
            "[yellow]Audio features not available for this app or request "
            f"({resp.status_code}). Skipping detailed audio analysis.[/yellow]"
        )
        return {}

    features_by_id: Dict[str, Dict[str, Any]] = {}
    for item in resp.json().get("audio_features", []) or []:
        tid = item.get("id")
        if tid:
            features_by_id[tid] = item
    return features_by_id


def _fetch_artist_objects(token: str, artist_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """
    Fetch full artist objects for up to 50 artists.

    Returns a mapping {artist_id: artist_json}.
    """
    unique_ids = list({aid for aid in artist_ids if aid})
    if not unique_ids:
        return {}

    headers = {"Authorization": f"Bearer {token}"}
    params = {"ids": ",".join(unique_ids[:50])}
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{SPOTIFY_API_BASE_URL}/artists",
            params=params,
            headers=headers,
        )
    if not resp.is_success:
        console.print(
            "[yellow]Could not fetch artist data:[/yellow] "
            f"{resp.status_code} {resp.text}"
        )
        return {}

    artists_by_id: Dict[str, Dict[str, Any]] = {}
    for artist in resp.json().get("artists", []) or []:
        aid = artist.get("id")
        if aid:
            artists_by_id[aid] = artist
    return artists_by_id


def _duration_ms_to_mmss(duration_ms: Optional[int]) -> str:
    if not duration_ms:
        return "?:??"
    total_seconds = duration_ms // 1000
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


@app.command()
def inspect(
    query: str = typer.Argument(..., help="Song or song + artist, e.g. 'blinding lights the weeknd'."),
    limit: int = typer.Option(3, min=1, max=10, help="How many top matches to inspect."),
) -> None:
    """
    Look up tracks on Spotify and print their metadata (and, where available,
    audio features and artist genres) to help you understand what a 'track'
    looks like under the hood.
    """
    console.print(
        "[bold cyan]SIMRAI dummy :: Track metadata explorer[/bold cyan]\n"
        f"Searching Spotify for: [magenta]{query!r}[/magenta]\n"
    )

    token = _get_access_token()
    tracks = _search_tracks(token, query, limit=limit)
    if not tracks:
        console.print("[yellow]No tracks found for that query.[/yellow]")
        raise typer.Exit(0)

    # Basic overview table.
    table = Table(title="Top matches", show_lines=False)
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Name", style="bold")
    table.add_column("Artists", style="magenta")
    table.add_column("Album", style="green")
    table.add_column("Year", justify="right")
    table.add_column("Popularity", justify="right")
    table.add_column("Duration", justify="right")

    track_ids: List[str] = []
    artist_ids: List[str] = []

    for idx, t in enumerate(tracks, start=1):
        name = t.get("name", "<unknown>")
        artists = ", ".join(a.get("name", "") for a in t.get("artists", []) or [])
        album = (t.get("album") or {}).get("name", "<unknown>")
        release_date = (t.get("album") or {}).get("release_date") or ""
        year = release_date[:4] if len(release_date) >= 4 else "----"
        popularity = t.get("popularity", 0)
        duration = _duration_ms_to_mmss(t.get("duration_ms"))

        table.add_row(
            str(idx),
            name,
            artists,
            album,
            str(year),
            str(popularity),
            duration,
        )

        tid = t.get("id")
        if tid:
            track_ids.append(tid)
        for a in t.get("artists", []) or []:
            aid = a.get("id")
            if aid:
                artist_ids.append(aid)

    console.print(table)

    # Deeper dive: artists, genres, and audio features for the first track(s).
    artists_by_id = _fetch_artist_objects(token, artist_ids)
    features_by_track = _fetch_audio_features(token, track_ids)

    for idx, t in enumerate(tracks, start=1):
        console.rule(f"[bold]Track {idx} detailed metadata[/bold]")
        tid = t.get("id")
        track_artists = t.get("artists", []) or []
        artist_names = [a.get("name", "") for a in track_artists]
        per_artist_genres = {}
        per_artist_raw = {}
        for i, a in enumerate(track_artists):
            aid = a.get("id") or ""
            name_key = a.get("name") or f"artist-{i}"
            artist_obj = artists_by_id.get(aid, {})
            per_artist_genres[name_key] = artist_obj.get("genres", []) or []
            per_artist_raw[name_key] = artist_obj

        overview = {
            "id": tid,
            "name": t.get("name"),
            "artists": artist_names,
            "artist_genres": per_artist_genres,
            "album": (t.get("album") or {}).get("name"),
            "album_release_date": (t.get("album") or {}).get("release_date"),
            "track_number": t.get("track_number"),
            "disc_number": t.get("disc_number"),
            "duration_ms": t.get("duration_ms"),
            "duration_human": _duration_ms_to_mmss(t.get("duration_ms")),
            "explicit": t.get("explicit"),
            "popularity": t.get("popularity"),
            "uri": t.get("uri"),
            "preview_url": t.get("preview_url"),
            "is_local": t.get("is_local"),
            "available_markets_count": len(t.get("available_markets") or []),
        }

        console.print("[bold]Core track + artist/album metadata:[/bold]")
        console.print_json(json.dumps(overview))

        # Full raw track object (everything Spotify returns for this track).
        console.print("\n[bold]Raw track object from Spotify:[/bold]")
        console.print_json(json.dumps(t))

        # Full raw artist objects (includes genres, images, followers, etc.).
        for artist_label, artist_obj in per_artist_raw.items():
            if not artist_obj:
                continue
            console.print(f"\n[bold]Raw artist object:[/bold] {artist_label}")
            console.print_json(json.dumps(artist_obj))

        feats = features_by_track.get(tid or "", {})
        if feats:
            audio_summary = {
                key: feats.get(key)
                for key in (
                    "danceability",
                    "energy",
                    "valence",
                    "tempo",
                    "loudness",
                    "speechiness",
                    "acousticness",
                    "instrumentalness",
                    "liveness",
                )
            }
            console.print("\n[bold]Audio features (psychoacoustic-ish):[/bold]")
            console.print_json(json.dumps(audio_summary))

            console.print("\n[bold]Raw audio_features object from Spotify:[/bold]")
            console.print_json(json.dumps(feats))
        else:
            console.print(
                "\n[dim]No audio features available for this track (or endpoint blocked).[/dim]"
            )


if __name__ == "__main__":
    app()


