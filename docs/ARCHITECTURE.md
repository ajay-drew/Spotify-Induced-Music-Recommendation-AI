# SIMRAI System Architecture

## Production-Grade System Architecture Diagram

```mermaid
graph TB
    subgraph "Client Layer"
        WEB[Web Browser<br/>React + TypeScript<br/>Tailwind CSS]
        CLI[CLI Client<br/>Typer + Rich]
    end

    subgraph "CDN / Static Hosting"
        STATIC[Static Assets<br/>Vite Build<br/>simrai.onrender.com]
    end

    subgraph "Application Layer - Frontend"
        REACT[React App<br/>App.tsx]
        STATE[State Management<br/>useState/useEffect]
        AUTH_UI[OAuth UI Flow<br/>Popup Handler]
    end

    subgraph "Application Layer - Backend API"
        API[FastAPI Server<br/>Port 8000<br/>simrai-api.onrender.com]
        ROUTES[API Routes<br/>/queue, /auth/*, /api/*]
        MIDDLEWARE[Middleware<br/>CORS, Rate Limiting<br/>Session Management]
    end

    subgraph "Business Logic Layer"
        MOOD[Mood Interpreter<br/>mood.py<br/>Rule-based + Groq]
        PIPELINE[Queue Pipeline<br/>pipeline.py<br/>Metadata Ranking]
        SPOTIFY_SVC[Spotify Service<br/>spotify.py<br/>Search + Metadata]
    end

    subgraph "Authentication & Authorization"
        OAUTH[OAuth Manager<br/>PKCE Flow<br/>State Validation]
        SESSION[Session Manager<br/>Cookie-based<br/>User Identification]
        TOKEN_STORE[Token Storage<br/>Per-User Files<br/>~/.config/simrai/tokens/]
    end

    subgraph "Data Layer"
        CACHE[In-Memory Cache<br/>Search Results<br/>Token Refresh]
        LOGS[Logging System<br/>RotatingFileHandler<br/>~/.config/simrai/logs/]
    end

    subgraph "External Services"
        SPOTIFY_API[Spotify Web API<br/>Search, Metadata<br/>Playlist Management]
        GROQ_API[Groq API<br/>LLM Inference<br/>Mood Refinement]
    end

    subgraph "Infrastructure"
        RENDER_BACKEND[Render Backend<br/>Docker Container<br/>Free Tier]
        RENDER_FRONTEND[Render Static Site<br/>CDN Distribution<br/>Free Tier]
        GITHUB[GitHub<br/>Source Control<br/>CI/CD]
    end

    subgraph "CI/CD Pipeline"
        ACTIONS[GitHub Actions<br/>.github/workflows/]
        PYTEST[Pytest Suite<br/>50 Tests<br/>Coverage Gate 70%+]
        BUILD[Frontend Build<br/>npm ci && npm run build]
    end

    %% Client to Frontend
    WEB -->|HTTPS| STATIC
    STATIC --> REACT
    REACT --> STATE
    REACT --> AUTH_UI
    CLI -->|Direct Import| MOOD
    CLI -->|Direct Import| PIPELINE

    %% Frontend to Backend
    REACT -->|REST API<br/>POST /queue| API
    REACT -->|OAuth Flow<br/>GET /auth/login| API
    AUTH_UI -->|postMessage<br/>Origin Validation| API
    REACT -->|Session Cookie<br/>credentials: include| API

    %% API Layer
    API --> ROUTES
    ROUTES --> MIDDLEWARE
    MIDDLEWARE -->|Rate Limit<br/>10/min queue<br/>5/min playlist| ROUTES
    MIDDLEWARE -->|CORS<br/>allowCredentials| ROUTES
    MIDDLEWARE -->|Session Cookie<br/>User ID| SESSION

    %% Business Logic Flow
    ROUTES -->|Queue Request| MOOD
    MOOD -->|Mood Vector<br/>Search Terms| PIPELINE
    PIPELINE -->|Search Query| SPOTIFY_SVC
    SPOTIFY_SVC -->|Metadata Results| PIPELINE
    PIPELINE -->|Ranked Queue| ROUTES

    %% OAuth Flow
    ROUTES -->|OAuth Init| OAUTH
    OAUTH -->|State Token<br/>CSRF Protection| SESSION
    OAUTH -->|Redirect| SPOTIFY_API
    SPOTIFY_API -->|Auth Code| OAUTH
    OAUTH -->|Token Exchange| TOKEN_STORE
    SESSION -->|User ID| TOKEN_STORE

    %% Playlist Flow
    ROUTES -->|Create Playlist| SPOTIFY_SVC
    SPOTIFY_SVC -->|User Token| TOKEN_STORE
    SPOTIFY_SVC -->|API Calls| SPOTIFY_API

    %% External Services
    MOOD -->|Optional<br/>Rate Limited| GROQ_API
    GROQ_API -->|Refined Mood| MOOD
    SPOTIFY_SVC -->|Search API<br/>Metadata Only| SPOTIFY_API

    %% Data Layer
    SPOTIFY_SVC -->|Cache Results| CACHE
    CACHE -->|Retrieve| SPOTIFY_SVC
    API -->|Log Events| LOGS
    PIPELINE -->|Log Processing| LOGS
    MOOD -->|Log AI Calls| LOGS

    %% Infrastructure
    API -->|Deploy| RENDER_BACKEND
    STATIC -->|Deploy| RENDER_FRONTEND
    RENDER_BACKEND -->|Health Check<br/>/health| API
    RENDER_FRONTEND -->|Static Files| STATIC

    %% CI/CD
    GITHUB -->|Push/PR| ACTIONS
    ACTIONS -->|Run Tests| PYTEST
    ACTIONS -->|Build Frontend| BUILD
    ACTIONS -->|Deploy| RENDER_BACKEND
    ACTIONS -->|Deploy| RENDER_FRONTEND

    %% Styling
    classDef frontend fill:#61dafb,stroke:#20232a,stroke-width:2px,color:#000
    classDef backend fill:#009688,stroke:#004d40,stroke-width:2px,color:#fff
    classDef external fill:#1db954,stroke:#191414,stroke-width:2px,color:#fff
    classDef infrastructure fill:#6c757d,stroke:#343a40,stroke-width:2px,color:#fff
    classDef security fill:#dc3545,stroke:#721c24,stroke-width:2px,color:#fff
    classDef data fill:#ffc107,stroke:#856404,stroke-width:2px,color:#000

    class WEB,REACT,STATE,AUTH_UI,STATIC frontend
    class API,ROUTES,MIDDLEWARE,MOOD,PIPELINE,SPOTIFY_SVC backend
    class SPOTIFY_API,GROQ_API external
    class RENDER_BACKEND,RENDER_FRONTEND,GITHUB,ACTIONS infrastructure
    class OAUTH,SESSION,TOKEN_STORE security
    class CACHE,LOGS data
```

## Data Flow Diagrams

### Queue Generation Flow

```mermaid
sequenceDiagram
    participant User
    participant React
    participant FastAPI
    participant MoodParser
    participant GroqAPI
    participant Pipeline
    participant SpotifyAPI
    participant Cache

    User->>React: Submit mood text
    React->>FastAPI: POST /queue {mood, length, flags}
    FastAPI->>MoodParser: interpret_mood(text)
    
    alt Groq API Available
        MoodParser->>GroqAPI: LLM Call (rate limited)
        GroqAPI-->>MoodParser: Refined mood vector
    end
    
    MoodParser-->>FastAPI: MoodInterpretation
    FastAPI->>Pipeline: generate_queue(mood, length)
    Pipeline->>SpotifyAPI: Search tracks (query)
    
    alt Cache Hit
        Cache-->>Pipeline: Cached results
    else Cache Miss
        SpotifyAPI-->>Pipeline: Search results
        Pipeline->>Cache: Store results
    end
    
    Pipeline->>Pipeline: Rank by metadata<br/>(popularity, year, heuristics)
    Pipeline->>Pipeline: Generate synthetic<br/>valence/energy
    Pipeline-->>FastAPI: QueueResponse
    FastAPI-->>React: JSON {tracks, summary}
    React-->>User: Display queue
```

### OAuth & Playlist Export Flow

```mermaid
sequenceDiagram
    participant User
    participant React
    participant FastAPI
    participant SpotifyOAuth
    participant SpotifyAPI
    participant TokenStore
    participant Session

    User->>React: Click "Connect Spotify"
    React->>FastAPI: GET /auth/login
    FastAPI->>SpotifyOAuth: Generate state token
    SpotifyOAuth->>Session: Store state (CSRF)
    FastAPI-->>React: Redirect to Spotify
    
    User->>SpotifyAPI: Authorize (show_dialog=true)
    SpotifyAPI-->>FastAPI: GET /auth/callback?code=...
    FastAPI->>SpotifyOAuth: Validate state
    SpotifyOAuth->>Session: Verify state token
    
    FastAPI->>SpotifyAPI: Exchange code for tokens
    SpotifyAPI-->>FastAPI: access_token, refresh_token
    FastAPI->>SpotifyAPI: GET /me (get user_id)
    SpotifyAPI-->>FastAPI: user_id
    
    FastAPI->>TokenStore: Save tokens per user_id
    FastAPI->>Session: Create session cookie
    FastAPI-->>React: HTML (postMessage + close)
    React->>React: Update state (connected)
    
    User->>React: Click "Create Playlist"
    React->>FastAPI: POST /api/create-playlist
    FastAPI->>Session: Get user_id from cookie
    FastAPI->>TokenStore: Load tokens (user_id)
    FastAPI->>SpotifyAPI: POST /playlists (create)
    SpotifyAPI-->>FastAPI: playlist_id, url
    
    FastAPI->>SpotifyAPI: POST /playlists/{id}/tracks
    SpotifyAPI-->>FastAPI: Success
    FastAPI-->>React: Playlist URL
    React-->>User: Show playlist link
```

## Component Interaction Diagram

```mermaid
graph LR
    subgraph "Frontend Components"
        A[App.tsx<br/>Main Component]
        B[Mood Form<br/>Input & Controls]
        C[Queue Table<br/>Results Display]
        D[Profile Menu<br/>Spotify Connect]
    end

    subgraph "Backend Modules"
        E[api.py<br/>FastAPI Routes]
        F[mood.py<br/>Mood Interpretation]
        G[pipeline.py<br/>Queue Generation]
        H[spotify.py<br/>Spotify Client]
        I[config.py<br/>Configuration]
    end

    subgraph "External Integrations"
        J[Spotify Web API]
        K[Groq API]
    end

    A --> B
    A --> C
    A --> D
    B -->|POST /queue| E
    D -->|GET /auth/login| E
    D -->|POST /api/create-playlist| E
    
    E -->|interpret_mood| F
    E -->|generate_queue| G
    F -->|Optional| K
    G -->|search_tracks| H
    G -->|get_metadata| H
    H -->|HTTP Requests| J
    E -->|get_config| I

    style A fill:#61dafb
    style E fill:#009688
    style J fill:#1db954
    style K fill:#ff6b6b
```

## Security Architecture

```mermaid
graph TB
    subgraph "Security Layers"
        CORS[CORS Middleware<br/>allowCredentials<br/>Origin Validation]
        RATE[Rate Limiting<br/>slowapi<br/>IP-based]
        OAUTH_SEC[OAuth Security<br/>State Validation<br/>PKCE]
        SESSION_SEC[Session Security<br/>HttpOnly Cookies<br/>SameSite]
        XSS[XSS Protection<br/>postMessage Origin<br/>Content Security]
    end

    subgraph "Attack Vectors Mitigated"
        CSRF[CSRF Attacks<br/>OAuth State Tokens]
        DOS[DDoS Protection<br/>Rate Limits]
        XSS_ATTACK[XSS Attacks<br/>Origin Validation]
        TOKEN_LEAK[Token Leakage<br/>Server-side Storage]
    end

    CORS --> CSRF
    RATE --> DOS
    OAUTH_SEC --> CSRF
    SESSION_SEC --> TOKEN_LEAK
    XSS --> XSS_ATTACK

    style CORS fill:#dc3545,color:#fff
    style RATE fill:#dc3545,color:#fff
    style OAUTH_SEC fill:#dc3545,color:#fff
    style SESSION_SEC fill:#dc3545,color:#fff
    style XSS fill:#dc3545,color:#fff
```

## Deployment Architecture

```mermaid
graph TB
    subgraph "Source Control"
        GIT[GitHub Repository<br/>Source Code]
    end

    subgraph "CI/CD Pipeline"
        GH_ACTIONS[GitHub Actions<br/>.github/workflows/tests.yml]
        TEST[Pytest Suite<br/>50 Tests<br/>Coverage 70%+]
        BUILD[Frontend Build<br/>npm ci && npm run build]
    end

    subgraph "Build Artifacts"
        DOCKER[Docker Image<br/>FastAPI Backend]
        STATIC_BUILD[Static Build<br/>web/dist/]
    end

    subgraph "Production Infrastructure"
        RENDER_API[Render Backend<br/>Docker Service<br/>simrai-api.onrender.com]
        RENDER_WEB[Render Static Site<br/>CDN<br/>simrai.onrender.com]
    end

    subgraph "Monitoring & Logs"
        LOGS[Application Logs<br/>RotatingFileHandler<br/>~/.config/simrai/logs/]
        HEALTH[Health Endpoint<br/>/health]
    end

    GIT -->|Push/PR| GH_ACTIONS
    GH_ACTIONS --> TEST
    GH_ACTIONS --> BUILD
    TEST -->|Pass| BUILD
    BUILD --> DOCKER
    BUILD --> STATIC_BUILD
    DOCKER -->|Deploy| RENDER_API
    STATIC_BUILD -->|Deploy| RENDER_WEB
    RENDER_API --> LOGS
    RENDER_API --> HEALTH

    style GIT fill:#24292e,color:#fff
    style GH_ACTIONS fill:#2088ff,color:#fff
    style RENDER_API fill:#6c757d,color:#fff
    style RENDER_WEB fill:#6c757d,color:#fff
```

## Technology Stack Summary

| Layer | Technology | Purpose |
|-------|------------|---------|
| **Frontend** | React 18+ | UI Framework |
| | TypeScript | Type Safety |
| | Vite | Build Tool |
| | Tailwind CSS | Styling |
| **Backend** | Python 3.10+ | Runtime |
| | FastAPI | Web Framework |
| | Typer | CLI Framework |
| | Rich | CLI UI |
| **AI/ML** | Groq API | LLM Inference |
| | LangChain | LLM Abstraction |
| **Music API** | Spotify Web API | Music Data |
| **Auth** | OAuth 2.0 + PKCE | Authentication |
| **Infrastructure** | Docker | Containerization |
| | Render | Hosting |
| | GitHub Actions | CI/CD |
| **Testing** | pytest | Test Framework |
| | pytest-cov | Coverage |
| | Cypress | E2E Tests |

