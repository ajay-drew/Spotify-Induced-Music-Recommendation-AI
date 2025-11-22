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

from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .pipeline import QueueResult, QueueTrack, generate_queue
from .spotify import SpotifyError


app = FastAPI(
    title="SIMRAI API",
    description="SIMRAI – Spotify-Induced Music Recommendation AI (metadata-only, read-only).",
    version="0.1.0",
)

# Allow local web frontends (e.g. React dev server on localhost:5658) to call the API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5658",
        "http://127.0.0.1:5658",
    ],
    allow_credentials=False,
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
    return {"status": "ok"}


@app.post("/queue", response_model=QueueResponse, tags=["queue"])
def create_queue(body: QueueRequest) -> QueueResponse:
    try:
        result: QueueResult = generate_queue(
            body.mood,
            length=body.length,
            intense=body.intense,
            soft=body.soft,
        )
    except SpotifyError as exc:
        raise HTTPException(status_code=502, detail=f"Spotify error: {exc}") from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise HTTPException(status_code=500, detail=f"Internal error: {exc}") from exc

    if not result.tracks:
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



