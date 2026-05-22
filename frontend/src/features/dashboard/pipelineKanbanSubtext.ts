import {
  isRunAtWithinSeconds,
  secondsUntilRunAt,
} from '../../shared/ui/LiveTimer';
import type { PipelineCardLike } from './serviceSetupMessages';

/** Show live countdown on Activity cards when run_at is this many seconds away or less. */
export const KANBAN_COUNTDOWN_WINDOW_SEC = 30;

export type KanbanSubtextKind =
  | 'pool_wait'
  | 'activity'
  | 'recently_finished'
  | 'countdown'
  | 'next'
  | 'phase';

export { isRunAtWithinSeconds, secondsUntilRunAt };

/** Resolve which subtext line to show on an Activity Kanban card (pill stays Wait/Run/Fail). */
export function resolveKanbanSubtextKind(
  item: PipelineCardLike,
  nowMs: number = Date.now(),
): KanbanSubtextKind {
  if (item.pipeline_phase === 'recently_finished') {
    if (
      item.completion_outcome === 'failed' ||
      item.state === 'Failed'
    ) {
      return 'phase';
    }
    if (item.run_at) {
      return 'recently_finished';
    }
    return 'phase';
  }

  if (item.in_flight && item.actively_running) {
    return 'activity';
  }

  if (item.in_flight && !item.actively_running) {
    return 'pool_wait';
  }

  if (item.activity?.trim()) {
    return 'activity';
  }

  const until = secondsUntilRunAt(item.run_at, nowMs);

  if (
    until != null &&
    until > 0 &&
    until <= KANBAN_COUNTDOWN_WINDOW_SEC &&
    !item.in_flight
  ) {
    return 'countdown';
  }

  if (
    !item.actively_running &&
    until != null &&
    until <= 0 &&
    item.state !== 'Failed' &&
    item.pipeline_phase !== 'queued_download_deferred'
  ) {
    return 'next';
  }

  return 'phase';
}
