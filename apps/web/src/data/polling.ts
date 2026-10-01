import { ApiError } from './http';
import type { BatchSummary } from './dto';

export const FAST_POLL_MS = 2_000;
export const SLOW_POLL_MS = 5_000;
export const FAST_POLL_WINDOW_MS = 60_000;
export const DEBRIEF_GRACE_MS = 30_000;
export const SHELL_POLL_MS = 15_000;

export function pollStopsOn(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 423);
}

export function pollDelay(pollingForMs: number): number {
  return pollingForMs < FAST_POLL_WINDOW_MS ? FAST_POLL_MS : SLOW_POLL_MS;
}

/** C2 §1.5: poll while running or generating a debrief; keep going 30 s past `finishedAt` while a review-bound batch has no debrief yet. */
export function batchNeedsPolling(batch: BatchSummary, now: number): boolean {
  if (batch.status === 'running') return true;
  if (batch.debrief?.status === 'generating') return true;
  if (batch.debrief === null && batch.counts.review > 0 && batch.finishedAt) {
    return now - Date.parse(batch.finishedAt) < DEBRIEF_GRACE_MS;
  }
  return false;
}

export function batchRefetchInterval(batch: BatchSummary | undefined, error: unknown, now: number, pollingSince: number): number | false {
  if (pollStopsOn(error) || !batch || !batchNeedsPolling(batch, now)) return false;
  return pollDelay(now - pollingSince);
}

/** C2 §1.5 for a job card or dialog: poll while its status is the working one. */
export function jobRefetchInterval(status: string | undefined, working: string, error: unknown, pollingForMs: number): number | false {
  if (pollStopsOn(error) || status !== working) return false;
  return pollDelay(pollingForMs);
}
