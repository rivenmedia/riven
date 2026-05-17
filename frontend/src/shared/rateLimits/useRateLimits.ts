import { useCallback, useEffect, useState } from 'react';
import { apiGet } from '../api/api';
import type { RateLimitsResponse } from './types';

const POLL_MS = 3000;

export function useRateLimits(owner?: string) {
  const [data, setData] = useState<RateLimitsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const path = owner
      ? `/rate_limits?owner=${encodeURIComponent(owner)}`
      : '/rate_limits';
    const res = await apiGet<RateLimitsResponse>(path);
    if (res.ok && res.data) {
      setData(res.data);
      setError(null);
    } else {
      setData(null);
      setError(res.error || 'Failed to load rate limits');
    }
  }, [owner]);

  useEffect(() => {
    void load();
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load]);

  return { data, error, limiters: data?.limiters ?? [] };
}
