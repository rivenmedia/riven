# Riven SPA - Contributor Guide

This folder contains the Alpine.js + Jinja SPA for Riven. No build step required.

## File Map (UI Element → Files)

| UI Element | Template | JS Logic |
|------------|----------|----------|
| Login / API key form | `templates/components/api_key_form.html` | `static/js/auth.js` |
| Nav bar | `templates/components/nav.html` | `static/js/router.js` |
| Media card (poster, title) | `templates/components/media_card.html` | `static/js/components/media_card.js` |
| Library grid | `templates/views/library.html` | `static/js/views/library.js` |
| Dashboard stats | `templates/views/dashboard.html` | `static/js/views/dashboard.js` |
| VFS stats table | `templates/views/vfs_stats.html` | `static/js/views/vfs_stats.js` |
| Explore / Search | `templates/views/explore.html` | `static/js/views/explore.js` |
| Trending | `templates/views/trending.html` | `static/js/views/trending.js` |
| Item detail (actions, streams, player) | `templates/views/item_detail.html` | `static/js/views/item_detail.js` |
| Calendar | `templates/views/calendar.html` | `static/js/views/calendar.js` |
| Mount | `templates/views/mount.html` | `static/js/views/mount.js` |

## Structure

- `templates/` - Jinja2 HTML (base, components, views)
- `static/js/` - ES modules (api, router, auth, views)
- `static/css/` - base, layout, components, views

## Adding a New View

1. Create `templates/views/myview.html` with `data-slot` attributes
2. Add `<template id="view-myview">` to `base.html`
3. Create `static/js/views/myview.js` with `export async function load(route, container)`
4. Register in `app.js` VIEW_LOADERS and router ROUTES
