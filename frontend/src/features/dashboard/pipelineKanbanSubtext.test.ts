import { describe, expect, it } from 'vitest';
import {
  KANBAN_COUNTDOWN_WINDOW_SEC,
  resolveKanbanSubtextKind,
  secondsUntilRunAt,
} from './pipelineKanbanSubtext';
import {
  deriveCardStatus,
  formatRunningStepSubtext,
  type PipelineCardLike,
} from './serviceSetupMessages';

const NOW = Date.parse('2026-05-21T18:00:00.000Z');

function card(overrides: Partial<PipelineCardLike> = {}): PipelineCardLike {
  return {
    in_flight: false,
    actively_running: false,
    deferred: false,
    pipeline_phase: 'queued_download',
    ...overrides,
  };
}

describe('secondsUntilRunAt', () => {
  it('returns seconds until run_at', () => {
    expect(secondsUntilRunAt('2026-05-21T18:00:20.000Z', NOW)).toBe(20);
  });

  it('returns negative when run_at is past', () => {
    expect(secondsUntilRunAt('2026-05-21T17:59:50.000Z', NOW)).toBe(-10);
  });
});

describe('resolveKanbanSubtextKind', () => {
  it('prefers pool wait over due run_at', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          in_flight: true,
          actively_running: false,
          run_at: '2026-05-21T17:59:50.000Z',
        }),
        NOW,
      ),
    ).toBe('pool_wait');
  });

  it('shows countdown only within 30s window', () => {
    expect(
      resolveKanbanSubtextKind(
        card({ run_at: '2026-05-21T18:00:15.000Z', deferred: true }),
        NOW,
      ),
    ).toBe('countdown');

    expect(
      resolveKanbanSubtextKind(
        card({ run_at: '2026-05-21T18:01:00.000Z', deferred: true }),
        NOW,
      ),
    ).toBe('phase');
  });

  it('shows next when run_at passed and still pending', () => {
    expect(
      resolveKanbanSubtextKind(
        card({ run_at: '2026-05-21T17:59:00.000Z', deferred: false }),
        NOW,
      ),
    ).toBe('next');
  });

  it('does not show next when actively running', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          run_at: '2026-05-21T17:59:00.000Z',
          in_flight: true,
          actively_running: true,
          activity: 'Stream 1/1 · downloading on realdebrid',
        }),
        NOW,
      ),
    ).toBe('activity');
  });

  it('does not show next for failed items', () => {
    expect(
      resolveKanbanSubtextKind(
        card({ run_at: '2026-05-21T17:59:00.000Z', state: 'Failed' }),
        NOW,
      ),
    ).toBe('phase');
  });

  it('uses recently_finished before next for success', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          pipeline_phase: 'recently_finished',
          completion_outcome: 'success',
          run_at: '2026-05-21T17:59:00.000Z',
        }),
        NOW,
      ),
    ).toBe('recently_finished');
  });

  it('uses phase subtext for failed recently_finished', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          pipeline_phase: 'recently_finished',
          completion_outcome: 'failed',
          state: 'Failed',
          run_at: '2026-05-21T17:59:00.000Z',
        }),
        NOW,
      ),
    ).toBe('phase');
  });

  it('prefers activity for actively running symlink', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          in_flight: true,
          actively_running: true,
          pipeline_phase: 'symlinking',
          activity: 'Creating library symlinks',
        }),
        NOW,
      ),
    ).toBe('activity');
  });

  it('does not show next for deferred download', () => {
    expect(
      resolveKanbanSubtextKind(
        card({
          run_at: '2026-05-21T17:59:00.000Z',
          deferred: true,
          pipeline_phase: 'queued_download_deferred',
        }),
        NOW,
      ),
    ).toBe('phase');
  });

  it('window constant is 30 seconds', () => {
    expect(KANBAN_COUNTDOWN_WINDOW_SEC).toBe(30);
    const atBoundary = new Date(NOW + 30 * 1000).toISOString();
    expect(resolveKanbanSubtextKind(card({ run_at: atBoundary }), NOW)).toBe(
      'countdown',
    );
    const outside = new Date(NOW + 31 * 1000).toISOString();
    expect(resolveKanbanSubtextKind(card({ run_at: outside }), NOW)).toBe('phase');
  });
});

describe('formatRunningStepSubtext', () => {
  it('prefixes symlink and post-processing steps', () => {
    expect(
      formatRunningStepSubtext('symlinking', 'Creating library symlinks'),
    ).toBe('Symlink — Creating library symlinks');
    expect(formatRunningStepSubtext('post_processing', 'Fetching subtitles')).toBe(
      'Post-processing — Fetching subtitles',
    );
  });
});

describe('deriveCardStatus', () => {
  it('marks recently finished success as completed', () => {
    expect(
      deriveCardStatus(
        card({
          pipeline_phase: 'recently_finished',
          completion_outcome: 'success',
        }),
      ),
    ).toBe('completed');
  });

  it('marks deferred download as deferred', () => {
    expect(
      deriveCardStatus(
        card({
          deferred: true,
          pipeline_phase: 'queued_download_deferred',
        }),
      ),
    ).toBe('deferred');
  });
});
