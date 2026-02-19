/**
 * API client - fetch wrapper with x-api-key and 401 handling
 */

const API_BASE = '/api/v1';

function getApiKey() {
  return sessionStorage.getItem('riven_api_key');
}

function clearAuth() {
  sessionStorage.removeItem('riven_api_key');
  window.location.href = '/';
}

export async function apiFetch(path, options = {}) {
  const key = getApiKey();
  if (!key) {
    return { ok: false, status: 401, data: null };
  }
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const headers = {
    'Content-Type': 'application/json',
    'x-api-key': key,
    ...options.headers,
  };
  try {
    const res = await fetch(url, { ...options, headers });
    if (res.status === 401) {
      clearAuth();
      return { ok: false, status: 401, data: null };
    }
    const data = res.ok ? await res.json().catch(() => null) : null;
    return { ok: res.ok, status: res.status, data };
  } catch (err) {
    console.error('API fetch error:', err);
    return { ok: false, status: 0, data: null };
  }
}

export async function apiGet(path, params = {}) {
  const qs = new URLSearchParams(params).toString();
  const url = qs ? `${path}?${qs}` : path;
  return apiFetch(url);
}

export async function apiPost(path, body = {}) {
  return apiFetch(path, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function apiDelete(path, body = {}) {
  return apiFetch(path, {
    method: 'DELETE',
    body: JSON.stringify(body),
  });
}

export function getStreamUrl(itemId) {
  const key = getApiKey();
  return `${API_BASE}/stream/file/${itemId}?api_key=${encodeURIComponent(key || '')}`;
}
