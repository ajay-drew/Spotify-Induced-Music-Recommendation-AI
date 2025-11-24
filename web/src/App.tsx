import React, { useEffect, useState } from "react";

type Track = {
  name: string;
  artists: string;
  uri: string;
  valence: number;
  energy: number;
};

type QueueResponse = {
  mood: string;
  mood_vector: { valence: number; energy: number };
  summary: string;
  tracks: Track[];
};

type SpotifyUser = {
  id: string;
  display_name: string | null;
  avatar_url: string | null;
};

// In development, we hit the local FastAPI backend; in production (Render),
// VITE_API_URL is set to the deployed API URL (e.g. https://simrai-api.onrender.com).
const API_BASE = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

function bar(value: number, width = 10): string {
  const v = Math.max(0, Math.min(1, value));
  const filled = Math.round(v * width);
  const empty = width - filled;
  return "█".repeat(filled) + "·".repeat(empty);
}

const App: React.FC = () => {
  const [mood, setMood] = useState("");
  const [length, setLength] = useState(12);
  const [intense, setIntense] = useState(false);
  const [soft, setSoft] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<QueueResponse | null>(null);
  const [copied, setCopied] = useState(false);
  const [playlistLoading, setPlaylistLoading] = useState(false);
  const [playlistUrl, setPlaylistUrl] = useState<string | null>(null);
  const [playlistMessage, setPlaylistMessage] = useState<string | null>(null);
  const [spotifyConnected, setSpotifyConnected] = useState(false);
  const [showConnectedToast, setShowConnectedToast] = useState(false);
  const [spotifyUser, setSpotifyUser] = useState<SpotifyUser | null>(null);
  const [profileOpen, setProfileOpen] = useState(false);

  const metadataOnly = !!data && data.summary.includes("Audio features endpoint is unavailable");

  const fetchSpotifyUser = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/me`);
      if (!resp.ok) {
        return;
      }
      const json = (await resp.json()) as SpotifyUser;
      setSpotifyUser(json);
      setSpotifyConnected(true);
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    const handler = (event: MessageEvent) => {
      const payload = event.data as any;
      if (!payload) return;
      if (payload.type === "simrai-spotify-connected") {
        setSpotifyConnected(true);
        setPlaylistMessage("Spotify is connected. You can now create playlists.");
        setShowConnectedToast(true);
        setTimeout(() => setShowConnectedToast(false), 2500);
        fetchSpotifyUser();
      } else if (payload.type === "simrai-spotify-denied") {
        setError("Spotify connection was denied. Please try again if you want to connect.");
        setSpotifyConnected(false);
        setSpotifyUser(null);
      }
    };

    window.addEventListener("message", handler);
    return () => window.removeEventListener("message", handler);
  }, []);

  const startSpotifyConnect = () => {
    window.open(
      `${API_BASE}/auth/login`,
      "simrai-spotify-connect",
      "width=480,height=640"
    );
  };

  const handleUnlinkSpotify = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/unlink-spotify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!resp.ok) {
        throw new Error("Unlink failed");
      }
      setSpotifyConnected(false);
      setSpotifyUser(null);
      setPlaylistMessage(null);
      setShowConnectedToast(false);
      setProfileOpen(false);
    } catch {
      setError("Could not unlink Spotify account.");
    }
  };

  const handleCopyUris = async () => {
    if (!data || !data.tracks.length) return;
    const text = data.tracks.map((t) => t.uri).join("\n");
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      setError("Could not copy URIs to clipboard.");
    }
  };

  const handleCreatePlaylist = async () => {
    if (!data || !data.tracks.length) {
      setError("No tracks to export. Generate a queue first.");
      return;
    }
    setPlaylistMessage(null);
    setPlaylistUrl(null);
    setError(null);
    setPlaylistLoading(true);

    const uris = data.tracks.map((t) => t.uri);
    const name =
      mood.trim().length > 0 ? `SIMRAI – ${mood.trim().slice(0, 40)}` : "SIMRAI Playlist";

    try {
      const createResp = await fetch(`${API_BASE}/api/create-playlist`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name,
          description: "Brewed by SIMRAI",
          public: false,
        }),
      });

      if (createResp.status === 401) {
        setPlaylistMessage(
          "Spotify is not connected. Connect your account first."
        );
        return;
      }

      if (!createResp.ok) {
        const text = await createResp.text();
        throw new Error(`Create playlist failed: ${createResp.status} ${text}`);
      }

      const created = (await createResp.json()) as { playlist_id: string; url?: string };

      const addResp = await fetch(`${API_BASE}/api/add-tracks`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          playlist_id: created.playlist_id,
          uris,
        }),
      });

      if (!addResp.ok) {
        const text = await createResp.text();
        throw new Error(`Add tracks failed: ${addResp.status} ${text}`);
      }

      setPlaylistUrl(created.url ?? null);
      setPlaylistMessage("Playlist created in your Spotify account!");
    } catch (err: any) {
      setError(err.message ?? "Something went wrong while creating the playlist.");
    } finally {
      setPlaylistLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mood.trim()) {
      setError("Please describe a mood first.");
      return;
    }
    setError(null);
    setLoading(true);
    setCopied(false);
    try {
      const resp = await fetch(`${API_BASE}/queue`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mood, length, intense, soft }),
      });
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`API error ${resp.status}: ${text}`);
      }
      const json = (await resp.json()) as QueueResponse;
      setData(json);
    } catch (err: any) {
      setError(err.message ?? "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-cursor-bg text-cursor-text p-8">
      {/* Profile menu */}
      <div className="fixed top-4 right-4 z-30">
        <button
          type="button"
          className="flex items-center gap-2 px-3 py-1.5 bg-cursor-surface hover:bg-cursor-surfaceHover border border-cursor-border rounded-md text-sm transition-colors"
          onClick={() => setProfileOpen((open) => !open)}
        >
          {spotifyUser?.avatar_url ? (
            <img
              src={spotifyUser.avatar_url}
              alt={spotifyUser.display_name ?? "Spotify user"}
              className="h-5 w-5 rounded-full object-cover"
            />
          ) : (
            <span className="text-cursor-textMuted">👤</span>
          )}
          <span className="text-sm">
            {spotifyConnected && spotifyUser?.display_name
              ? spotifyUser.display_name
              : "Not connected"}
          </span>
          <span className="text-cursor-textMuted">▾</span>
        </button>

        {profileOpen && (
          <div className="mt-2 w-48 bg-cursor-surface border border-cursor-border rounded-md shadow-lg overflow-hidden">
            {!spotifyConnected ? (
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-cursor-surfaceHover transition-colors"
                onClick={() => {
                  startSpotifyConnect();
                  setProfileOpen(false);
                }}
              >
                Connect to Spotify
              </button>
            ) : (
              <button
                type="button"
                className="w-full text-left px-3 py-2 text-sm text-cursor-error hover:bg-cursor-surfaceHover transition-colors"
                onClick={handleUnlinkSpotify}
              >
                Unlink Spotify
              </button>
            )}
          </div>
        )}
      </div>

      <div className="max-w-4xl mx-auto space-y-6">
        {/* Header */}
        <header className="space-y-1">
          <h1 className="text-2xl font-semibold text-cursor-text">
            SIMRAI
          </h1>
          <p className="text-sm text-muted">
            {mood.trim()
              ? `Mood: "${mood.trim().slice(0, 40)}${mood.trim().length > 40 ? "…" : ""}"`
              : "Describe your mood to generate a music queue"}
          </p>
          {data && (
            <p className="text-xs text-dim font-mono">
              Valence: {data.mood_vector.valence.toFixed(2)} · Energy: {data.mood_vector.energy.toFixed(2)}
            </p>
          )}
        </header>

        {/* Form */}
        <form onSubmit={handleSubmit} className="card space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Mood</label>
            <textarea
              className="input-field h-24 resize-none"
              placeholder='e.g. "rainy midnight drive with someone you miss"'
              value={mood}
              onChange={(e) => setMood(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div>
              <label className="block text-sm font-medium mb-2">
                Length: {length} tracks
              </label>
              <input
                type="range"
                min={8}
                max={30}
                value={length}
                onChange={(e) => setLength(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={intense}
                onChange={(e) => setIntense(e.target.checked)}
                className="rounded"
              />
              <span>Intense</span>
            </label>
            <label className="flex items-center gap-2 text-sm cursor-pointer">
              <input
                type="checkbox"
                checked={soft}
                onChange={(e) => setSoft(e.target.checked)}
                className="rounded"
              />
              <span>Soft</span>
            </label>
          </div>

          <div className="flex items-center justify-between pt-2">
            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
            >
              {loading ? "Generating..." : "Generate Queue"}
            </button>
            {data && (
              <button
                type="button"
                className="btn-secondary"
                onClick={handleCreatePlaylist}
                disabled={playlistLoading || !data.tracks.length}
              >
                {playlistLoading ? "Creating..." : "Create Playlist"}
              </button>
            )}
          </div>

          {error && (
            <p className="text-sm text-cursor-error">{error}</p>
          )}
          {playlistMessage && (
            <p className="text-sm text-muted">
              {playlistMessage}{" "}
              {playlistUrl && (
                <a
                  href={playlistUrl}
                  target="_blank"
                  rel="noreferrer"
                  className="text-cursor-accent hover:text-cursor-accentHover underline"
                >
                  Open in Spotify
                </a>
              )}
            </p>
          )}
          {spotifyConnected && showConnectedToast && !playlistMessage && (
            <p className="text-sm text-cursor-success">Spotify connected</p>
          )}
        </form>

        {/* Queue Results */}
        {data && data.tracks.length > 0 && (
          <section className="card space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <h2 className="text-lg font-semibold">Queue</h2>
                <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                  metadataOnly
                    ? "bg-cursor-warning/20 text-cursor-warning"
                    : "bg-cursor-success/20 text-cursor-success"
                }`}>
                  {metadataOnly ? "Metadata Only" : "Full Features"}
                </span>
              </div>
              <p className="text-sm text-muted max-w-md text-right">
                {data.summary}
              </p>
            </div>

            <div className="flex items-center justify-between text-sm text-muted">
              <span>
                {data.tracks.length} tracks · Valence: {data.mood_vector.valence.toFixed(2)} · Energy: {data.mood_vector.energy.toFixed(2)}
              </span>
              <button
                type="button"
                className="btn-secondary text-xs"
                onClick={handleCopyUris}
                disabled={!data.tracks.length}
              >
                {copied ? "Copied!" : "Copy URIs"}
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-sm">
                <thead>
                  <tr className="text-left text-muted border-b border-cursor-border">
                    <th className="pb-2 pr-4 font-medium">#</th>
                    <th className="pb-2 pr-4 font-medium">Track</th>
                    <th className="pb-2 pr-4 font-medium">Artist</th>
                    <th className="pb-2 pr-4 font-medium">Valence</th>
                    <th className="pb-2 pr-4 font-medium">Energy</th>
                    <th className="pb-2 pr-4 font-medium hidden sm:table-cell">URI</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tracks.map((t, idx) => (
                    <tr
                      key={t.uri}
                      className={`border-b border-cursor-border hover:bg-cursor-surfaceHover transition-colors ${
                        idx % 2 === 0 ? "" : "bg-cursor-surface/30"
                      }`}
                    >
                      <td className="py-3 pr-4 text-muted font-mono">{idx + 1}</td>
                      <td className="py-3 pr-4 font-medium">{t.name}</td>
                      <td className="py-3 pr-4 text-muted">{t.artists}</td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs">{t.valence.toFixed(2)}</span>
                          <span className="text-xs text-muted font-mono">{bar(t.valence, 8)}</span>
                        </div>
                      </td>
                      <td className="py-3 pr-4">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs">{t.energy.toFixed(2)}</span>
                          <span className="text-xs text-muted font-mono">{bar(t.energy, 8)}</span>
                        </div>
                      </td>
                      <td className="py-3 pr-4 hidden sm:table-cell">
                        <a
                          href={t.uri}
                          target="_blank"
                          rel="noreferrer"
                          className="text-cursor-accent hover:text-cursor-accentHover text-xs underline"
                        >
                          open
                        </a>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default App;
