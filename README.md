# SIMRAI - Spotify-Induced Music Recommendation AI

**SIMRAI** transforms your mood into a perfectly curated Spotify playlist. Just describe how you feel, and SIMRAI creates a personalized queue that matches your emotional state.

## Why SIMRAI is Better Than Spotify's Recommendations

### 🎯 **Mood-Based Discovery**
- **Spotify**: Requires you to know what you want to listen to (artist, song, genre)
- **SIMRAI**: Just describe your mood ("rainy midnight drive with someone you miss") and get instant recommendations

### 🧠 **AI-Powered Interpretation**
- **Spotify**: Relies on listening history and collaborative filtering
- **SIMRAI**: Uses a lightweight Groq-backed model (plus rule-based logic) to understand nuanced emotional descriptions and translate them into precise musical parameters (valence, energy, intensity)

### 🎨 **Creative & Flexible**
- **Spotify**: Limited to existing playlists and algorithmic suggestions
- **SIMRAI**: Generates unique queues on-demand based on any mood description, even abstract concepts like "main character energy from mid 2010's"

### 🔒 **Privacy-First**
- **Spotify**: Tracks your listening habits and builds a profile
- **SIMRAI**: Runs locally, processes moods without storing personal data, optional OAuth only for playlist creation

### ⚡ **Metadata-Driven Intelligence**
- **Spotify**: Uses audio features that may be restricted for new apps
- **SIMRAI**: Leverages popularity, release year, and text analysis to create smart recommendations even without audio features

## Features

- 🎵 **CLI Tool**: Generate queues from command line
- 🌐 **Web UI**: Beautiful React interface with real-time queue generation
- 🤖 **AI Enhancement**: Optional Groq-powered mood interpretation (free tier)
- 📊 **Metadata Analysis**: Smart ranking using popularity, year, and track metadata
- 🎧 **Playlist Export**: One-click export to Spotify playlists (OAuth)
- 📝 **Comprehensive Logging**: Built-in logging for debugging and monitoring

## Quick Start

### Prerequisites

- Python 3.10+
- Node.js 18+ (for web UI)
- Spotify Developer Account (free)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/Spotify-Induced-Music-Recommendation-AI.git
   cd Spotify-Induced-Music-Recommendation-AI
   ```

2. **Set up Python environment**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/macOS
   source venv/bin/activate
   
   pip install -r requirements.txt
   pip install -e .
   ```

3. **Set up Spotify credentials**
   
   Create a `.env` file in the project root:
   ```env
   SIMRAI_SPOTIFY_CLIENT_ID=your_client_id
   SIMRAI_SPOTIFY_CLIENT_SECRET=your_client_secret
   SIMRAI_SPOTIFY_REDIRECT_URI=http://localhost:8000/auth/callback
   ```
   
   Get your credentials:
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
   - Create a new app
   - Copy Client ID and Client Secret
   - Add `http://localhost:8000/auth/callback` as a redirect URI

4. **Optional: Set up AI enhancement**
   ```env
   GROQ_API_KEY=your_groq_api_key
   SIMRAI_GROQ_MODEL=llama-3.1-8b-instant
   ```
   
   Get a free API key at [Groq Console](https://console.groq.com/)

### Usage

#### CLI Mode

Generate a queue from command line:
```bash
simrai queue "rainy midnight drive" --length 15
```

Options:
- `--length` / `-n`: Queue length (8-30, default: 12)
- `--intense`: Bias toward higher energy
- `--soft`: Bias toward lower energy, gentler vibes

#### Web UI Mode

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
   - Click "Brew Queue" to generate recommendations
   - Connect Spotify (optional) to export playlists

#### Windows Quick Start

Use the provided batch files:
```cmd
run_all.cmd    # Starts both backend and frontend
run_cli.cmd    # Runs CLI mode only
```

## Project Structure

```
├── src/simrai/          # Python package
│   ├── cli.py          # CLI entrypoint
│   ├── api.py          # FastAPI endpoints
│   ├── pipeline.py     # Queue generation logic (metadata-first, no audio-features)
│   ├── mood.py         # Mood interpretation (rule-based core + optional Groq refinement)
│   ├── spotify.py      # Spotify integration
│   └── agents.py       # Lightweight compatibility stubs (no CrewAI)
├── web/                # React frontend
│   ├── src/
│   └── package.json
├── pythontests/        # Test suite
└── requirements.txt    # Python dependencies
```

## How It Works

1. **Mood Interpretation**: Your text is analyzed to extract:
   - Emotional valence (positive/negative)
   - Energy level (calm/intense)
   - Search terms and preferences

2. **Spotify Search**: Searches Spotify using interpreted keywords

3. **Smart Ranking**: Ranks tracks using:
   - Popularity scores
   - Release year
   - Track/album name analysis
   - Mood preferences (popular/obscure, recent/classics)

4. **Queue Generation**: Creates an ordered queue with gentle energy progression

5. **Optional AI Enhancement**: Uses a single Groq-powered model call to refine mood interpretation (no complex agent framework)

## Monitoring Logs

Logs are automatically saved to:
- **Linux/macOS**: `~/.simrai/logs/simrai.log`
- **Windows**: `%LOCALAPPDATA%\Project57\simrai\logs\simrai.log`

View logs in real-time:
```bash
# Linux/macOS
tail -f ~/.simrai/logs/simrai.log

# Windows PowerShell
Get-Content "$env:LOCALAPPDATA\Project57\simrai\logs\simrai.log" -Wait -Tail 50
```

Set log level via environment variable:
```bash
export SIMRAI_LOG_LEVEL=DEBUG  # DEBUG, INFO, WARNING, ERROR
```

## Testing

Run the test suite:
```bash
pytest pythontests/ --cov=src/simrai --cov-report=term-missing
```

## License

See [LICENSE](LICENSE) file for details.

## Contributing

Contributions welcome! Please feel free to submit a Pull Request.

## Support

For issues and questions, please open an issue on GitHub.

