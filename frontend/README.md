# Riven Frontend

React + Vite + TypeScript frontend for the Riven UI.

## UI Structure

- Shared page primitives: `src/components/ui/PagePrimitives.tsx`
- Route templates: `src/viewTemplates.tsx`
- Goal: keep headers, panels, and page layout consistent across all routes.

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
