"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api/health";

type Connection = "checking" | "connected" | "unavailable";

export default function Home() {
  const [connection, setConnection] = useState<Connection>("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    getHealth(controller.signal)
      .then(() => { if (!controller.signal.aborted) setConnection("connected"); })
      .catch(() => { if (!controller.signal.aborted) setConnection("unavailable"); });
    return () => controller.abort();
  }, [attempt]);

  function checkAgain() {
    setConnection("checking");
    setAttempt((value) => value + 1);
  }

  return (
    <div className="shell">
      <header><span className="mark" aria-hidden="true">M</span><span>ML Studio</span>
        <span className="local">Local workspace</span></header>
      <main>
        <p className="eyebrow">Application foundation</p>
        <h1>Your workspace starts here.</h1>
        <p className="tagline">Visual ML. Real code. Reproducible experiments.</p>
        <section className="connection" aria-labelledby="backend-title">
          <div><h2 id="backend-title">Backend connection</h2>
            <p className="explanation">A live check of the API and its local database.</p></div>
          <div className="status-row">
            <p className={"status " + connection} role="status" aria-live="polite">
              <span className="dot" aria-hidden="true" />
              {connection === "connected" ? "Connected" : connection === "checking" ? "Checking…" : "Unavailable"}
            </p>
            <button onClick={checkAgain} disabled={connection === "checking"}>Check again</button>
          </div>
          {connection === "unavailable" && <p className="help">The backend could not be reached or is not ready. Start the local backend, then check again.</p>}
          {connection === "connected" && <p className="help">The API is responding and can access SQLite.</p>}
        </section>
        <p className="footnote">Project and experiment workflows will arrive in subsequent phases.</p>
      </main>
      <footer>ML Studio <span>Application foundation · Phase 0</span></footer>
    </div>
  );
}
