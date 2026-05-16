/**
 * Auth - API key validation and sessionStorage
 */

const KEY = 'riven_api_key';
const SUPPRESS_VITE_API_KEY = 'riven_suppress_vite_api_key';

function getEnvKey(): string | null {
  if (!import.meta.env.DEV) return null;
  try {
    if (sessionStorage.getItem(SUPPRESS_VITE_API_KEY) === '1') return null;
  } catch (_) {
    return null;
  }
  const fromEnv = import.meta.env.VITE_API_KEY;
  return typeof fromEnv === 'string' && fromEnv.length > 0 ? fromEnv : null;
}

/** After a real HTTP 401 in dev, stop using VITE_API_KEY for this tab until setKey(). */
export function suppressDevViteKeyAfter401(): void {
  if (!import.meta.env.DEV) return;
  try {
    sessionStorage.setItem(SUPPRESS_VITE_API_KEY, '1');
  } catch (_) {}
}

export function hasKey() {
  return !!sessionStorage.getItem(KEY) || !!getEnvKey();
}

export function getKey() {
  return sessionStorage.getItem(KEY) || getEnvKey();
}

export function setKey(key: string) {
  sessionStorage.setItem(KEY, key);
  try {
    sessionStorage.removeItem(SUPPRESS_VITE_API_KEY);
  } catch (_) {}
}

export function clearKey() {
  sessionStorage.removeItem(KEY);
}

export async function validateKey(key: string) {
  const res = await fetch('/api/v1/health', {
    headers: { 'x-api-key': key },
  });
  return res.ok;
}

export async function login(key: string) {
  const ok = await validateKey(key);
  if (ok) {
    setKey(key);
    return true;
  }
  return false;
}

export function logout() {
  clearKey();
  window.location.href = '/';
}
