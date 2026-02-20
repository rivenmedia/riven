/**
 * API client - fetch wrapper with x-api-key and 401 handling.
 */

const API_BASE = '/api/v1';

function getApiKey() {
  return sessionStorage.getItem('riven_api_key');
}

function clearAuth() {
  sessionStorage.removeItem('riven_api_key');
  window.location.href = '/';
}

function buildQueryString(params = {}) {
  const searchParams = new URLSearchParams();

  Object.entries(params).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') {
      return;
    }

    if (Array.isArray(value)) {
      value.forEach((item) => {
        if (item !== undefined && item !== null && item !== '') {
          searchParams.append(key, String(item));
        }
      });
      return;
    }

    searchParams.append(key, String(value));
  });

  const qs = searchParams.toString();
  return qs ? `?${qs}` : '';
}

async function parseResponsePayload(response) {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return response.json().catch(() => null);
  }

  const text = await response.text().catch(() => '');
  return text || null;
}

function extractError(payload, fallbackStatus) {
  if (!payload) return `Request failed (${fallbackStatus})`;
  if (typeof payload === 'string') return payload;
  if (typeof payload.detail === 'string') return payload.detail;
  if (typeof payload.message === 'string') return payload.message;
  return `Request failed (${fallbackStatus})`;
}

export async function apiFetch(path, options = {}) {
  const key = getApiKey();
  if (!key) {
    return {
      ok: false,
      status: 401,
      data: null,
      error: 'Missing API key',
    };
  }

  const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
  const headers = {
    'x-api-key': key,
    ...options.headers,
  };

  const hasBody = options.body !== undefined && options.body !== null;
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
  if (hasBody && !isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  try {
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401) {
      clearAuth();
      return {
        ok: false,
        status: 401,
        data: null,
        error: 'Unauthorized',
      };
    }

    const data = await parseResponsePayload(response);
    return {
      ok: response.ok,
      status: response.status,
      data,
      error: response.ok ? null : extractError(data, response.status),
    };
  } catch (error) {
    console.error('API fetch error:', error);
    return {
      ok: false,
      status: 0,
      data: null,
      error: 'Network request failed',
    };
  }
}

export async function apiGet(path, params = {}) {
  return apiFetch(`${path}${buildQueryString(params)}`);
}

export async function apiPost(path, body = {}) {
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  return apiFetch(path, {
    method: 'POST',
    body: isFormData ? body : JSON.stringify(body),
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
