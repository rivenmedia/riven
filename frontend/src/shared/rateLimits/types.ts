export type LimiterSnapshot = {
  key: string;
  label: string;
  owner: string;
  tokens: number;
  capacity: number;
  rate_per_second: number;
  utilization_pct: number;
  next_token_in_seconds: number;
  priority: string;
  warn_at_pct: number;
  breaker_state: string;
  breaker_failures: number;
  breaker_recovery_in_seconds: number;
};

export type RateLimitsResponse = {
  limiters: LimiterSnapshot[];
  by_owner: Record<string, string[]>;
};
