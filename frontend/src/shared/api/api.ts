/**
 * API client - fetch wrapper with x-api-key and 401 handling.
 */

const API_BASE = '/api/v1';

type QueryValue = string | number | boolean | null | undefined;
type QueryParams = Record<string, QueryValue | QueryValue[]>;

export interface ApiResult<T = any> {
  ok: boolean;
  status: number;
  data: T | null;
  error: string | null;
}

function getApiKey(): string | null {
  return sessionStorage.getItem('riven_api_key');
}

function clearAuth(): void {
  sessionStorage.removeItem('riven_api_key');
  window.location.href = '/';
}

function buildQueryString(params: QueryParams = {}): string {
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

async function parseResponsePayload(response: Response): Promise<any | null> {
  const contentType = response.headers.get('content-type') || '';

  if (contentType.includes('application/json')) {
    return response.json().catch(() => null);
  }

  const text = await response.text().catch(() => '');
  return text || null;
}

function extractError(payload: unknown, fallbackStatus: number): string {
  if (!payload) return `Request failed (${fallbackStatus})`;
  if (typeof payload === 'string') return payload;
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'detail' in payload &&
    typeof (payload as { detail?: unknown }).detail === 'string'
  ) {
    return (payload as { detail: string }).detail;
  }
  if (
    typeof payload === 'object' &&
    payload !== null &&
    'message' in payload &&
    typeof (payload as { message?: unknown }).message === 'string'
  ) {
    return (payload as { message: string }).message;
  }
  return `Request failed (${fallbackStatus})`;
}

export async function apiFetch<T = any>(
  path: string,
  options: RequestInit = {},
): Promise<ApiResult<T>> {
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
  const headers: Record<string, string> = {
    'x-api-key': key,
  };
  if (options.headers) {
    const requestHeaders = new Headers(options.headers);
    requestHeaders.forEach((value, keyName) => {
      headers[keyName] = value;
    });
  }

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

    const data = (await parseResponsePayload(response)) as T | null;
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

export async function apiGet<T = any>(
  path: string,
  params: QueryParams = {},
): Promise<ApiResult<T>> {
  return apiFetch(`${path}${buildQueryString(params)}`);
}

export async function apiPost<T = any>(
  path: string,
  body: Record<string, unknown> | FormData = {},
): Promise<ApiResult<T>> {
  const isFormData = typeof FormData !== 'undefined' && body instanceof FormData;
  return apiFetch(path, {
    method: 'POST',
    body: isFormData ? body : JSON.stringify(body),
  });
}

export async function apiDelete<T = any>(
  path: string,
  body: Record<string, unknown> = {},
): Promise<ApiResult<T>> {
  return apiFetch(path, {
    method: 'DELETE',
    body: JSON.stringify(body),
  });
}

export function getStreamUrl(itemId: string | number): string {
  const key = getApiKey();
  return `${API_BASE}/stream/file/${itemId}?api_key=${encodeURIComponent(key || '')}`;
}
