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

const API_BASE = "http://localhost:8000";

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
   const [recentMoods, setRecentMoods] = useState<string[]>([]);
  const [copied, setCopied] = useState(false);

  const metadataOnly = !!data && data.summary.includes("Audio features endpoint is unavailable");

  useEffect(() => {
    const stored = window.localStorage.getItem("simrai_recent_moods");
    if (stored) {
      try {
        const arr = JSON.parse(stored);
        if (Array.isArray(arr)) {
          setRecentMoods(arr);
        }
      } catch {
        // ignore
      }
    }
  }, []);

  const rememberMood = (m: string) => {
    const trimmed = m.trim();
    if (!trimmed) return;
    setRecentMoods((prev) => {
      const next = [trimmed, ...prev.filter((p) => p !== trimmed)].slice(0, 5);
      window.localStorage.setItem("simrai_recent_moods", JSON.stringify(next));
      return next;
    });
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

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!mood.trim()) {
      setError("Please describe a mood first.");
      return;
    }
    setError(null);
    setLoading(true);
    setCopied(false);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/queue?theme=mario`, {
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
      rememberMood(mood);
    } catch (err: any) {
      setError(err.message ?? "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-full flex items-center justify-center p-4">
      <div className="max-w-5xl w-full space-y-4">
        {/* Mario-like HUD header */}
        <header className="pixel-panel p-3 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div className="flex items-center gap-2">
            <img
              src="/sprites/mushroom-badge.png"
              alt="SIMRAI mascot"
              className="w-6 h-6 pixel-sprite"
            />
            <h1 className="pixel-heading text-mario-red">
              SIMRAI <span className="text-mario-gold">DJ</span>
            </h1>
          </div>
          <div className="text-[9px] text-mario-dark/80 flex flex-col sm:items-end leading-tight">
            <span>WORLD 1-1</span>
            {data ? (
              <span>
                MOOD VEC: {data.mood_vector.valence.toFixed(2)} /{" "}
                {data.mood_vector.energy.toFixed(2)}
              </span>
            ) : (
              <span>MOOD VEC: -- / --</span>
            )}
          </div>
        </header>

        <form onSubmit={handleSubmit} className="pixel-panel p-4 space-y-3">
          <div className="qblock-panel p-3 pl-8">
            <label className="pixel-heading block mb-2 text-mario-dark">Mood</label>
            <textarea
              className="pixel-input h-20 resize-none"
              placeholder='e.g. "rainy midnight drive with someone you miss"'
              value={mood}
              onChange={(e) => setMood(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div>
              <label className="pixel-heading block mb-1 text-mario-dark">
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
            <label className="inline-flex items-center gap-2 mt-2 sm:mt-5 text-mario-dark/90">
              <input
                type="checkbox"
                checked={intense}
                onChange={(e) => setIntense(e.target.checked)}
              />
              <span className="pixel-heading flex items-center gap-1">
                <img
                  src="/sprites/mushroom-badge.png"
                  alt=""
                  className="w-3 h-3 pixel-sprite"
                />
                Intense
              </span>
            </label>
            <label className="inline-flex items-center gap-2 mt-2 sm:mt-5 text-mario-dark/90">
              <input
                type="checkbox"
                checked={soft}
                onChange={(e) => setSoft(e.target.checked)}
              />
              <span className="pixel-heading flex items-center gap-1">
                <img src="/sprites/star-badge.png" alt="" className="w-3 h-3 pixel-sprite" />
                Soft
              </span>
            </label>
          </div>

          <div className="flex items-center justify-between gap-3 pt-2">
            <div className="flex items-center gap-2">
              <button
                type="submit"
                aria-label="Brew queue"
                className={`pipe-btn pixel-border pixel-hover flex items-center gap-2 ${
                  loading ? "opacity-80 cursor-wait" : ""
                }`}
                disabled={loading}
              >
                {loading ? (
                  <>
                    <img
                      src="/sprites/mario-run-1.png"
                      className="w-5 h-5 pixel-sprite"
                      alt=""
                    />
                    <span>Brew-ing...</span>
                  </>
                ) : (
                  <>
                    <img
                      src="/sprites/pipe-top.png"
                      className="w-5 h-5 pixel-sprite"
                      alt=""
                    />
                    <span>Start (Warp Pipe)</span>
                  </>
                )}
              </button>
              {recentMoods.length > 0 && (
                <div className="flex flex-wrap gap-1 text-[9px] text-mario-dark/80">
                  {recentMoods.map((m) => (
                    <button
                      key={m}
                      type="button"
                      className="pixel-button"
                      onClick={() => setMood(m)}
                    >
                      use: {m.length > 14 ? `${m.slice(0, 14)}…` : m}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {data && (
              <div className="text-[10px] text-mario-dark/80">
                Mood vector: valence {data.mood_vector.valence.toFixed(2)}, energy{" "}
                {data.mood_vector.energy.toFixed(2)}
              </div>
            )}
          </div>

          {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
        </form>

        {data && data.tracks.length > 0 && (
          <section className="pixel-panel p-4 space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <div className="flex items-center gap-2">
                <h2 className="pixel-heading text-mario-dark">Queue</h2>
                <span
                  className={`pixel-pill ${
                    metadataOnly ? "bg-mario-gold/80" : "bg-mario-pipe/80"
                  }`}
                >
                  {metadataOnly ? (
                    <>
                      <img
                        src="/sprites/star-badge.png"
                        alt=""
                        className="w-3 h-3 pixel-sprite"
                      />
                      MODE: METADATA-ONLY
                    </>
                  ) : (
                    <>
                      <img
                        src="/sprites/mushroom-badge.png"
                        alt=""
                        className="w-3 h-3 pixel-sprite"
                      />
                      MODE: FULL FEATURES
                    </>
                  )}
                </span>
              </div>
              <p className="text-[10px] text-pastelInk/70 max-w-md text-right">{data.summary}</p>
            </div>

            <div className="flex items-center justify-between text-[10px] text-mario-dark/80">
              <p>
                Tracks: {data.tracks.length} · Mood vector:{" "}
                {data.mood_vector.valence.toFixed(2)} ⭐ {data.mood_vector.energy.toFixed(2)} ★
              </p>
              <button
                type="button"
                className="pipe-btn pixel-border pixel-hover text-[10px]"
                onClick={handleCopyUris}
                disabled={!data.tracks.length}
              >
                {copied ? "1-up! Copied!" : "Copy URIs"}
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="min-w-full text-[10px]">
                <thead>
                  <tr className="text-left text-mario-dark/80">
                    <th className="pr-2">#</th>
                    <th className="pr-2">Track</th>
                    <th className="pr-2">Artist</th>
                    <th className="pr-2">Valence</th>
                    <th className="pr-2">Energy</th>
                    <th className="pr-2 hidden sm:table-cell">URI</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tracks.map((t, idx) => (
                    <tr
                      key={t.uri}
                      className={`${
                        idx % 2 === 0 ? "bg-white/60" : "bg-white/40"
                      } hover:bg-pastelMint/40`}
                    >
                      <td className="pr-2 py-1">{idx + 1}</td>
                      <td className="pr-2 py-1 text-[11px] font-semibold">{t.name}</td>
                      <td className="pr-2 py-1 text-[10px] text-pastelInk/80">{t.artists}</td>
                      <td className="pr-2 py-1 whitespace-nowrap">
                        {t.valence.toFixed(2)}{" "}
                        <span className="font-mono text-[9px]">{bar(t.valence)}</span>
                      </td>
                      <td className="pr-2 py-1 whitespace-nowrap">
                        {t.energy.toFixed(2)}{" "}
                        <span className="font-mono text-[9px]">{bar(t.energy)}</span>
                      </td>
                      <td className="pr-2 py-1 hidden sm:table-cell">
                        <a
                          href={t.uri}
                          target="_blank"
                          rel="noreferrer"
                          className="underline text-pastelSky"
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


