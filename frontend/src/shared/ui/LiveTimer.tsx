import { useEffect, useRef, useState } from 'react';
import { formatRelativeSeconds, parseApiDate, secondsSinceApiDate } from '../utils/utils';

function formatElapsedSeconds(seconds: number): string {
  const sec = Math.max(0, Math.round(seconds));
  if (sec < 60) return `${sec}s`;
  const min = Math.floor(sec / 60);
  const rem = sec % 60;
  if (min < 60) return rem > 0 ? `${min}m ${rem}s` : `${min}m`;
  const hr = Math.floor(min / 60);
  const minRem = min % 60;
  return minRem > 0 ? `${hr}h ${minRem}m` : `${hr}h`;
}

/** Countdown from an ISO timestamp (client clock); ticks every second. */
export function LiveCountdownToIso({
  iso,
  className = 'activity-kanban__subtext-timer',
}: {
  iso: string;
  className?: string;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [iso]);

  const target = parseApiDate(iso)?.getTime();
  if (target == null || !Number.isFinite(target)) return <span className={className}>—</span>;

  const remaining = Math.max(0, Math.round((target - Date.now()) / 1000));
  if (remaining <= 0) {
    return <span className={className}>Ready</span>;
  }

  return (
    <span className={className}>{formatRelativeSeconds(remaining, 'future')}</span>
  );
}

/** Elapsed time since an ISO timestamp; ticks every second. */
export function LiveElapsedIso({
  iso,
  className = 'downloader-live-elapsed',
}: {
  iso: string;
  className?: string;
}) {
  const [, setTick] = useState(0);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [iso]);

  const age = secondsSinceApiDate(iso);
  if (age == null) return <span className={className}>—</span>;
  return <span className={className}>{formatElapsedSeconds(age)}</span>;
}

/**
 * Countdown from server-reported seconds remaining at poll time.
 * Used only for aggregate queue stats (not per-item cards).
 */
export function LiveServerCountdown({
  initialSeconds,
  className = 'downloader-live-countdown',
}: {
  initialSeconds: number;
  className?: string;
}) {
  const anchorRef = useRef({ polledAt: Date.now(), seconds: initialSeconds });
  const [, setTick] = useState(0);

  useEffect(() => {
    anchorRef.current = { polledAt: Date.now(), seconds: initialSeconds };
  }, [initialSeconds]);

  useEffect(() => {
    const id = window.setInterval(() => setTick((n) => n + 1), 1000);
    return () => window.clearInterval(id);
  }, [initialSeconds]);

  const elapsed = (Date.now() - anchorRef.current.polledAt) / 1000;
  const remaining = Math.max(0, anchorRef.current.seconds - elapsed);

  return (
    <strong className={className}>{formatRelativeSeconds(remaining, 'future')}</strong>
  );
}

export function secondsUntilRunAt(
  iso: string | null | undefined,
  nowMs: number = Date.now(),
): number | null {
  if (!iso) return null;
  const target = parseApiDate(iso)?.getTime();
  if (target == null || !Number.isFinite(target)) return null;
  return Math.round((target - nowMs) / 1000);
}

export function isRunAtWithinSeconds(
  iso: string | null | undefined,
  maxSeconds: number,
  nowMs: number = Date.now(),
): boolean {
  const until = secondsUntilRunAt(iso, nowMs);
  return until != null && until > 0 && until <= maxSeconds;
}

export function isRunAtInFuture(iso: string | null | undefined): boolean {
  const until = secondsUntilRunAt(iso);
  return until != null && until > 0;
}
