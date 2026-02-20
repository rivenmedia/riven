/**
 * Auth - API key validation and sessionStorage
 */

const KEY = 'riven_api_key';

export function hasKey() {
  return !!sessionStorage.getItem(KEY);
}

export function getKey() {
  return sessionStorage.getItem(KEY);
}

export function setKey(key) {
  sessionStorage.setItem(KEY, key);
}

export function clearKey() {
  sessionStorage.removeItem(KEY);
}

export async function validateKey(key) {
  const res = await fetch('/api/v1/health', {
    headers: { 'x-api-key': key },
  });
  return res.ok;
}

export async function login(key) {
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
