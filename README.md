# SIMRAI – Spotify-Induced Music Recommendation AI

**SIMRAI** turns free‑text mood descriptions into curated Spotify queues and optional playlists.  
You type *“rainy midnight drive with someone you miss”* → SIMRAI builds a queue and (if you connect Spotify) can export it as a playlist to **your** account.

---

## Why SIMRAI is Better Than Spotify’s Built‑In Recommendations

### 🎯 **Mood‑First Discovery**
- **Spotify**: You start from artists, tracks, or static playlists.
- **SIMRAI**: You start from a *feeling* – “pre‑exam focus”, “end‑of‑summer nostalgia”, “boss fight energy” – and get a queue shaped around that mood.

### 🧠 **Groq‑Backed + Rule‑Based Brain**
- Uses a lightweight **Groq** model (optional) plus deterministic rules to:
  - Estimate valence/energy from your text.
  - Decide newer vs. older, popular vs. obscure preferences.

### ⚙️ **Metadata‑Only, API‑Friendly**
- No reliance on Spotify’s blocked audio‑features/recommendations for new apps.
- Uses **search + metadata** (popularity, year, text heuristics) to score tracks.

### 🔒 **Safer OAuth & Multi‑User Ready**
- Explicit Spotify OAuth consent (with `show_dialog=true`) and account picker.
- Tokens stored **per user** on the backend, tied to a session cookie.
- Rate‑limited endpoints to avoid 429s and abuse.

### 🧪 **Real Tests & CI**
- Pytest suite with coverage gate (`--cov-fail-under=70`).
- GitHub Actions CI runs Python tests + coverage and builds the React frontend on every push/PR to `main`.

---

## Where to Access SIMRAI

### 🌐 Hosted (Render)

- **Frontend (Web UI)**: `https://simrai.onrender.com`
- **Backend (FastAPI API)**: `https://simrai-api.onrender.com`
  - Health: `https://simrai-api.onrender.com/health`
  - Docs (Swagger): `https://simrai-api.onrender.com/docs`

#### ⚠️ Cold Start (Render Free Tier)

The backend (`simrai-api`) runs on Render’s **free tier**:

- If the service has been idle for a while, Render **scales it down to zero**.
- The **first request after inactivity** will experience a **cold start**:
  - Expect **~20–60 seconds** delay before the first successful response.
  - You may briefly see 5xx errors or timeouts during warm‑up.
- Once warm, responses are fast and normal.

**Tip:** If the web UI seems stuck on “brewing” for the first time, wait ~30 seconds and try again – that’s just the container waking up.

---

## Quick Start (Local)

### Prerequisites

- Python 3.10+
- Node.js 18+ (for web UI)
- Spotify Developer Account (free)

### 1. Clone & Install

```bash
git clone https://github.com/ajay-drew/Spotify-Induced-Music-Recommendation-AI.git
cd Spotify-Induced-Music-Recommendation-AI

python -m venv venv
# Windows
venv\Scripts\activate
# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
pip install -e .
```

### 2. Configure Environment

Create a `.env` file in the project root:

```env
SIMRAI_SPOTIFY_CLIENT_ID=your_client_id
SIMRAI_SPOTIFY_CLIENT_SECRET=your_client_secret

# Optional Groq AI enhancement
GROQ_API_KEY=your_groq_api_key
SIMRAI_GROQ_MODEL=llama-3.1-8b-instant

# Optional logging level (DEBUG, INFO, WARNING, ERROR)
SIMRAI_LOG_LEVEL=INFO
```

In your **Spotify Developer Dashboard** app settings:

- Add this redirect URI:
  - `http://localhost:8000/auth/callback`

SIMRAI’s backend always uses this callback; Spotify Dev is the single source of truth for redirect URIs.

### 3. CLI Mode

Generate a queue from command line:

```bash
simrai queue "rainy midnight drive" --length 15
```

Options:

- `--length` / `-n`: Queue length (8–30, default: 12)
- `--intense`: Bias toward higher energy
- `--soft`: Bias toward lower energy, gentler vibes

### 4. Web UI Mode (Local)

1. **Start the backend**
   ```bash
   simrai serve
   ```
   Backend runs on `http://localhost:8000`

2. **Start the frontend** (in a new terminal)
   ```bash
   cd web
   npm install
   npm run dev
   ```
   Frontend runs on `http://localhost:5658`

3. **Open your browser**
   - Navigate to `http://localhost:5658`
   - Enter your mood description
   - Click **Brew Queue** to generate recommendations
   - Connect Spotify (optional) to export playlists

#### Windows Quick Start

Use the provided batch files:

```cmd
run_all.cmd    # Starts both backend and frontend
run_cli.cmd    # Runs CLI mode only
```

---

## Project Structure

```text
├── src/simrai/          # Python package
│   ├── cli.py           # CLI entrypoint (queue / serve)
│   ├── api.py           # FastAPI endpoints (queue, OAuth, playlist, profile)
│   ├── pipeline.py      # Queue generation logic (metadata-first, no audio-features)
│   ├── mood.py          # Mood interpretation (rule-based core + optional Groq refinement)
│   ├── spotify.py       # Spotify integration (search + metadata only)
│   └── agents.py        # Lightweight compatibility stubs (no CrewAI)
├── web/                 # React + Vite + Tailwind frontend
│   ├── src/
│   └── package.json
├── pythontests/         # Python test suite
├── .github/workflows/   # GitHub Actions tests & frontend build
├── render.yaml          # Render deployment (backend + static frontend)
└── requirements.txt     # Python dependencies
```

---

## Architecture

For a detailed production-grade system architecture diagram with data flows, security layers, and deployment infrastructure, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## How It Works

1. **Mood Interpretation**
   - Your text is analyzed to extract:
     - Emotional valence (positive/negative)
     - Energy level (calm/intense)
     - Search terms and preferences (popular/obscure, recent/classics)
   - Optional Groq model refines this interpretation when `GROQ_API_KEY` is set.

2. **Spotify Search**
   - Uses Spotify’s search API to find candidate tracks matching the interpreted query.

3. **Smart Ranking**
   - Ranks tracks using:
     - Popularity scores
     - Release year
     - Track/album name analysis (“acoustic”, “remix”, etc.)
     - Mood preferences

4. **Queue Generation**
   - Creates an ordered queue with a gentle energy progression.
   - Produces synthetic valence/energy values per track using metadata alone.

5. **Optional Playlist Export**
   - After you connect Spotify via OAuth:
     - `/api/create-playlist` creates a playlist in your account.
     - `/api/add-tracks` adds the brewed queue URIs to that playlist.

---

## Monitoring Logs

SIMRAI uses Python’s built‑in `logging` module with a rotating log file plus console output.

- **Log location** (via `platformdirs.user_config_dir`):
  - Linux/macOS: typically `~/.config/simrai/logs/simrai.log`
  - Windows: `%LOCALAPPDATA%\Project57\simrai\logs\simrai.log`

View logs in real-time:

```bash
# Linux/macOS (adjust path if needed)
tail -f ~/.config/simrai/logs/simrai.log

# Windows PowerShell
Get-Content "$env:LOCALAPPDATA\Project57\simrai\logs\simrai.log" -Wait -Tail 50
```

Configure log level via environment variable:

```bash
export SIMRAI_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

---

## Testing & CI

Run the test suite with coverage (matches CI):

```bash
pytest pythontests --cov=src/simrai --cov-report=term-missing --cov-report=xml --cov-fail-under=70
```

GitHub Actions (`.github/workflows/tests.yml`) runs:

- **Python tests & coverage** (with `pip install -e .` so `simrai` imports work).
- **Frontend build** in `web/` (`npm ci && npm run build`).

Protect `main` by requiring these checks to pass before merging.

---

## License & Contributing

- **License**: See `LICENSE`.
- **Contributions**: Issues and PRs are welcome – especially around new mood heuristics, better metadata scoring, or UX improvements to the web UI.

---

## Done By

**Ajay A**

- **Email**: [drewjay05@gmail.com](mailto:drewjay05@gmail.com)
- **LinkedIn**: [https://www.linkedin.com/in/ajay-drew/](https://www.linkedin.com/in/ajay-drew/)


