import { describe, expect, it } from 'vitest';
import type { BatchSummary } from './dto';
import { ApiError } from './http';
import { DEBRIEF_GRACE_MS, FAST_POLL_MS, SLOW_POLL_MS, batchNeedsPolling, batchRefetchInterval, jobRefetchInterval, pollDelay } from './polling';

const T0 = Date.parse('2026-10-01T10:00:00Z');

function batch(over: Partial<BatchSummary> & { review?: number } = {}): BatchSummary {
  const { review = 0, ...rest } = over;
  return {
    id: 'bat_x',
    source: 'drop',
    status: 'done',
    title: null,
    visitor: false,
    startedAt: new Date(T0 - 60_000).toISOString(),
    finishedAt: new Date(T0).toISOString(),
    counts: { items: 3, accepted: 3, duplicate: 0, rejected: 0, processing: 0, filed: 3 - review, review, unreadable: 0, failed: 0 },
    groupId: 'grp_x',
    debrief: null,
    ...rest,
  };
}

describe('C2 §1.5 batch polling', () => {
  it('polls while the batch is running', () => {
    expect(batchNeedsPolling(batch({ status: 'running', finishedAt: null }), T0)).toBe(true);
  });

  it('polls while the debrief is generating, even on a finished batch', () => {
    const b = batch({ debrief: { interviewId: 'int_x', status: 'generating', openQuestions: 0 } });
    expect(batchNeedsPolling(b, T0 + 10 * 60_000)).toBe(true);
  });

  it('stops at done when the debrief is ready', () => {
    const b = batch({ review: 2, debrief: { interviewId: 'int_x', status: 'ready', openQuestions: 2 } });
    expect(batchNeedsPolling(b, T0)).toBe(false);
  });

  it('stops at done when nothing went to review and there is no debrief', () => {
    expect(batchNeedsPolling(batch({ review: 0 }), T0 + 1_000)).toBe(false);
  });

  it('keeps polling for 30 s after finishedAt while a review-bound batch has no debrief, then stops', () => {
    const b = batch({ review: 1 });
    expect(batchNeedsPolling(b, T0)).toBe(true);
    expect(batchNeedsPolling(b, T0 + DEBRIEF_GRACE_MS - 1)).toBe(true);
    expect(batchNeedsPolling(b, T0 + DEBRIEF_GRACE_MS)).toBe(false);
  });

  it('polls every 2 s for the first minute, then every 5 s', () => {
    expect(pollDelay(0)).toBe(FAST_POLL_MS);
    expect(pollDelay(59_999)).toBe(FAST_POLL_MS);
    expect(pollDelay(60_000)).toBe(SLOW_POLL_MS);
    const running = batch({ status: 'running', finishedAt: null });
    expect(batchRefetchInterval(running, null, T0 + 30_000, T0)).toBe(2_000);
    expect(batchRefetchInterval(running, null, T0 + 90_000, T0)).toBe(5_000);
  });

  it('stops on 401 and 423, and before the first response', () => {
    const running = batch({ status: 'running', finishedAt: null });
    expect(batchRefetchInterval(running, new ApiError(401, 'unauthenticated', 'x'), T0, T0)).toBe(false);
    expect(batchRefetchInterval(running, new ApiError(423, 'locked', 'x'), T0, T0)).toBe(false);
    expect(batchRefetchInterval(running, new ApiError(500, 'internal', 'x'), T0, T0)).toBe(2_000);
    expect(batchRefetchInterval(undefined, null, T0, T0)).toBe(false);
  });
});

describe('C2 §1.5 export polling', () => {
  it('polls every 2 s for the first minute, then every 5 s, while building', () => {
    expect(jobRefetchInterval('building', 'building', null, 0)).toBe(FAST_POLL_MS);
    expect(jobRefetchInterval('building', 'building', null, 59_000)).toBe(FAST_POLL_MS);
    expect(jobRefetchInterval('building', 'building', null, 60_000)).toBe(SLOW_POLL_MS);
  });

  it('stops when ready or failed, before the first answer, and on 401 or 423', () => {
    expect(jobRefetchInterval('ready', 'building', null, 0)).toBe(false);
    expect(jobRefetchInterval('failed', 'building', null, 0)).toBe(false);
    expect(jobRefetchInterval(undefined, 'building', null, 0)).toBe(false);
    expect(jobRefetchInterval('building', 'building', new ApiError(423, 'locked', 'x'), 0)).toBe(false);
  });
});
