# Frontend Build Output

`src/static/ui` is generated output from the Node/React frontend package in `/frontend`.

- Source app: `/frontend`
- Build command: `make frontend-build` (or `npm --prefix frontend run build`)
- Output served by FastAPI: `src/static/ui/index.html` and `src/static/ui/assets/*`
- Backend serves only the frontend bundle at `/` and `/static/ui/*`

The previous Jinja2 template-based UI in `src/templates` has been removed.
All frontend source JS/CSS is now managed under `frontend/src`.
