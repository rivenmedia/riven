# Frontend Build Output

`src/static/ui` is generated output from the Node/React frontend package in `/frontend`.

- Source app: `/frontend`
- Build command: `make frontend-build` (or `npm --prefix frontend run build`)
- Output served by FastAPI: `src/static/ui/index.html` and `src/static/ui/assets/*`

Legacy JS/CSS modules in `src/static/js` and `src/static/css` are still used by the React shell during migration.

The previous Jinja2 template-based UI in `src/templates` has been removed.
