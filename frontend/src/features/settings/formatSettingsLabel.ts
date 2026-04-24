/** Human-readable key: `_` → spaces, first character uppercased. */
export function formatSettingsKeyLabel(raw: string): string {
  const s = raw.split('_').join(' ').trim();
  if (!s) return raw;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** e.g. `post_processing` or `content.listrr` → `Post processing` / `Content · Listrr` */
export function formatSettingsRouteLabel(routeKey: string): string {
  const i = routeKey.indexOf('.');
  if (i < 0) return formatSettingsKeyLabel(routeKey);
  return `${formatSettingsKeyLabel(routeKey.slice(0, i))} · ${formatSettingsKeyLabel(routeKey.slice(i + 1))}`;
}
