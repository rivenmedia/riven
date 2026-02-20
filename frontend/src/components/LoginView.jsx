import { useState } from "react";

export default function LoginView({ loading, error, onSubmit }) {
  const [apiKey, setApiKey] = useState("");

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = apiKey.trim();
    if (!trimmed || loading) {
      return;
    }
    await onSubmit(trimmed);
  }

  return (
    <div className="login-shell">
      <div className="login-panel">
        <h1>Riven</h1>
        <p className="login-subtitle">
          Manage movies, TV shows, discovery graph, and backend operations in
          one place.
        </p>
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="api-key">API Key</label>
          <input
            autoComplete="off"
            id="api-key"
            onChange={(event) => setApiKey(event.target.value)}
            placeholder="Paste API key"
            required
            type="password"
            value={apiKey}
          />
          <p
            className="error-msg"
            hidden={!error}
            role="alert"
          >
            {error}
          </p>
          <button
            className="btn btn--primary btn--block"
            disabled={loading}
            type="submit"
          >
            {loading ? "Connecting..." : "Connect"}
          </button>
        </form>
        <div className="login-links">
          <a href="/api/v1/" rel="noreferrer" target="_blank">
            OpenAPI JSON
          </a>
          <a href="/scalar" rel="noreferrer" target="_blank">
            Scalar Docs
          </a>
        </div>
      </div>
    </div>
  );
}
