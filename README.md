## SIMRAI – Spotify‑Induced Music Recommendation AI

SIMRAI turns a free‑text mood like _“rainy midnight drive with someone you miss”_ into a Spotify queue you can play or export as a playlist in **your** account.

---

## Live Demo (Render)

- **Web UI**: `https://simrai.onrender.com`  
- **API**: `https://simrai-api.onrender.com`
  - Health: `https://simrai-api.onrender.com/health`
  - Docs (Swagger): `https://simrai-api.onrender.com/docs`

> Render free tier: the API may take **20–60 seconds** to wake up after being idle. If the first request is slow or briefly errors, wait and try again.

---

## What It Does (In One Glance)

- **Mood‑first discovery** – start with a feeling instead of a playlist or genre.
- **Metadata‑only ranking** – uses Spotify search + metadata (popularity, year, track/album text); it does **not** rely on blocked audio‑features endpoints.
- **Optional Groq AI** – a Groq‑hosted open model (if `GROQ_API_KEY` is set) refines the mood vector; otherwise a fast rule‑based engine runs locally.
- **Spotify OAuth + playlist export** – connect your own Spotify once, then create a SIMRAI playlist in your account with a single button.
- **Two front‑ends** – a Typer CLI and a React/Tailwind web UI (friends/family‑friendly).

SIMRAI uses only standard Spotify Web API endpoints for **search** and **playlist creation** and never stores your Spotify password or client secret in the browser.

---

## Tech Snapshot

- **Backend**: Python 3.10+, FastAPI, httpx
- **Spotify**: OAuth authorization‑code flow; Web API search + playlist endpoints (metadata‑driven)
- **AI**: Optional Groq client (e.g. Llama‑3‑style model) plus deterministic heuristics
- **Frontend**: React + Vite + TypeScript + Tailwind CSS
- **Tests/CI**: pytest + pytest‑cov, GitHub Actions, coverage gate at 70%+

---

## Local Quick Start

### 1. Clone & install

```bash
git clone https://github.com/ajay-drew/Spotify-Induced-Music-Recommendation-AI.git
cd Spotify-Induced-Music-Recommendation-AI

python -m venv venv
venv\Scripts\activate  # Windows
# or
source venv/bin/activate  # Linux/macOS

pip install -r requirements.txt
pip install -e .
```

### 2. Configure env vars

Create a `.env` file in the project root:

```env
SIMRAI_SPOTIFY_CLIENT_ID=your_spotify_client_id
SIMRAI_SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

# Optional: Groq for smarter mood interpretation
GROQ_API_KEY=your_groq_api_key
SIMRAI_GROQ_MODEL=llama-3.1-8b-instant
```

In your **Spotify Developer Dashboard** app settings, configure redirect URIs:

- **Local dev**: `http://127.0.0.1:8000/auth/callback`  
- **Production (Render)**: `https://simrai-api.onrender.com/auth/callback`

> Spotify requires loopback addresses (e.g. `127.0.0.1`) for local dev – `localhost` is not allowed.

### 3. Run CLI mode

```bash
simrai queue "rainy midnight drive with someone you miss" --length 15
```

Key flags:

- `--length` / `-n`: number of tracks (8–30, default 12)
- `--intense`: bias toward higher energy
- `--soft`: bias toward lower energy

### 4. Run backend + web UI

**Windows (recommended):**

```cmd
run_all.cmd
```

This will start:

- Backend API at `http://127.0.0.1:8000`
- Frontend at `http://127.0.0.1:5658`

Open `http://127.0.0.1:5658` in your browser.

**Manual (all platforms):**

Backend:

```bash
simrai serve  # FastAPI on http://127.0.0.1:8000
```

Frontend:

```bash
cd web
npm install
npm run dev -- --host 127.0.0.1 --port 5658
```

Then browse to `http://127.0.0.1:5658`.

---

## How the Model & API Work (Short Version)

1. **Interpret mood** – free‑text mood → valence/energy + preferences (popular/obscure, recent/classic) via rule‑based logic + optional Groq refinement.
2. **Search Spotify** – use Spotify search API to fetch candidate tracks for the interpreted query.
3. **Score using metadata** – rank tracks using popularity, release year, and text cues from track/album names (e.g. “acoustic”, “remix”, “club”) to synthesize valence/energy.
4. **Build a queue** – produce an ordered list of tracks that gently moves energy/valence in the intended direction, in either:
   - **Track count mode** (N best tracks), or  
   - **Duration mode** (approximate total minutes ±3 min).
5. **Export (optional)** – once connected via OAuth, the backend creates a playlist and adds the queued tracks; the web UI exposes this as a “Create Playlist” button.

All OAuth tokens and Spotify secrets stay on the backend; the browser only sees high‑level status and track data.

---

## Testing & CI

- Local tests:

  ```bash
  pytest pythontests --cov=src/simrai --cov-fail-under=70
  ```

- GitHub Actions (`.github/workflows/tests.yml`) runs:
  - Backend tests with coverage
  - Frontend build (`npm ci && npm run build` in `web/`)

---

## Created By

**Ajay A**

- **Email**: `drewjay05@gmail.com`  
- **LinkedIn**: `https://www.linkedin.com/in/ajay-drew/`

SIMRAI is designed as a compact, end‑to‑end project you can share with friends, family, and recruiters: mood‑driven queues, real Spotify OAuth, a clean web UI, and a tested Python backend.
