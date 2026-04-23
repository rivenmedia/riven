# Riven Frontend

React + Vite + TypeScript frontend for the Riven UI.

## UI Structure

```
src/
  app/         # app shell, route/view wiring, route types
  components/  # React components
  services/    # API/auth/router/notify/status tracking utilities
  ui/          # reusable DOM UI helpers (media card, media type toggle)
  views/       # page logic modules
  styles/      # global styles
```

## Commands

- Install deps: `npm install`
- Dev server (with API proxy): `npm run dev`
- Type check: `npm run typecheck`
- Production build: `npm run build`

## Local .env (git-ignored)

Create `frontend/.env.local` (it is git-ignored) from `frontend/.env.local.example`.

Example:

```bash
cp .env.local.example .env.local
```

Vite exposes only `VITE_`-prefixed variables to the browser bundle. For dev convenience, you can set:

```bash
VITE_API_KEY=...         # used by the UI if sessionStorage key is not set
VITE_BACKEND_URL=...     # dev proxy target
```

## Dev Proxy

The dev server proxies backend endpoints to `http://localhost:8080` by default.

Override backend target:

```bash
VITE_BACKEND_URL=http://localhost:9000 npm run dev
```

Point at a backend by IP:

```bash
VITE_BACKEND_HOST=192.168.1.170 npm run dev
```

Or with an explicit port/proto:

```bash
VITE_BACKEND_HOST=192.168.1.170 VITE_BACKEND_PORT=8080 VITE_BACKEND_PROTO=http npm run dev
```

## Build Output

`npm run build` emits files to:

`../src/static/ui`

FastAPI serves `src/static/ui/index.html` at `/` when present.
