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

## Dev Proxy

The dev server proxies backend endpoints to `http://localhost:8080` by default.

Override backend target:

```bash
VITE_BACKEND_URL=http://localhost:9000 npm run dev
```

## Build Output

`npm run build` emits files to:

`../src/static/ui`

FastAPI serves `src/static/ui/index.html` at `/` when present.
