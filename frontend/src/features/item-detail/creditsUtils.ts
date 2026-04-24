/** Whether TMDB credits payload has any cast (incl. guest) or crew entries. */
export function creditsHaveContent(c: unknown): boolean {
  if (!c || typeof c !== 'object') return false;
  const o = c as Record<string, unknown>;
  const n =
    (Array.isArray(o.cast) ? o.cast.length : 0) +
    (Array.isArray(o.guest_stars) ? o.guest_stars.length : 0) +
    (Array.isArray(o.crew) ? o.crew.length : 0);
  return n > 0;
}
