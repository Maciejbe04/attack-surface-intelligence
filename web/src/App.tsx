import { useEffect, useState } from "react";

type Health = {
  status: string;
  database: boolean;
};

export function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health/")
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        return response.json();
      })
      .then((data: Health) => setHealth(data))
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="shell">
      <header className="brand">
        <p className="eyebrow">Attack Surface Intelligence</p>
        <h1>SurfaceX</h1>
        <p className="lede">Local discovery console scaffold. Full MVP UI lands next.</p>
      </header>

      <section className="panel" aria-live="polite">
        <h2>API health</h2>
        {error && <p className="error">Unreachable: {error}</p>}
        {!error && !health && <p className="muted">Checking…</p>}
        {health && (
          <dl className="facts">
            <div>
              <dt>Status</dt>
              <dd>{health.status}</dd>
            </div>
            <div>
              <dt>Database</dt>
              <dd>{health.database ? "connected" : "down"}</dd>
            </div>
          </dl>
        )}
      </section>
    </main>
  );
}
