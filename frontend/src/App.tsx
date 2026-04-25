import { useEffect, useState } from 'react';

type HealthResponse = {
  status: string;
  service: string;
};

export function App() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetch('/api/health', { signal: controller.signal })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Backend returned ${response.status}`);
        }
        return response.json() as Promise<HealthResponse>;
      })
      .then(setHealth)
      .catch((currentError: Error) => {
        if (currentError.name !== 'AbortError') {
          setError(currentError.message);
        }
      });

    return () => controller.abort();
  }, []);

  return (
    <main className="shell">
      <section className="status-panel" aria-labelledby="app-title">
        <p className="eyebrow">Federal Center SW</p>
        <h1 id="app-title">TypeScript frontend with a Python API</h1>
        <p className="lede">
          This starter app uses React, Vite, TypeScript, and FastAPI. The status below is loaded from the backend through the Vite proxy.
        </p>

        <div className="health-row" role="status" aria-live="polite">
          <span className={health ? 'indicator ok' : error ? 'indicator error' : 'indicator'} />
          <span>
            {health ? `${health.service}: ${health.status}` : error ? `Backend unavailable: ${error}` : 'Checking backend status...'}
          </span>
        </div>
      </section>
    </main>
  );
}
