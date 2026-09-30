import type { BatchCounts, BatchSummary } from '../../data/dto';

export interface IntakeSummary {
  filed: number;
  needYou: number;
  unreadable: number;
  alreadyHad: number;
}

export function intakeSummary(counts: BatchCounts): IntakeSummary {
  return {
    filed: counts.filed,
    needYou: counts.review + counts.failed,
    unreadable: counts.unreadable + counts.rejected,
    alreadyHad: counts.duplicate,
  };
}

export const STEPS = ['queued', 'reading', 'ocr', 'classifying', 'result'] as const;
export type Step = (typeof STEPS)[number];

/** 1-based position of the step a document is on; `filing` and the end states sit on Result. */
export function stepOf(stage: string): number {
  switch (stage) {
    case 'queued':
      return 1;
    case 'reading':
      return 2;
    case 'ocr':
      return 3;
    case 'classifying':
      return 4;
    default:
      return 5;
  }
}

export function timeLeftMs(startedAt: string, now: number, done: number, total: number): number | null {
  if (done <= 0 || done >= total) return null;
  const elapsed = now - Date.parse(startedAt);
  return Math.max(0, (elapsed / done) * (total - done));
}

export function showsQuestionsBanner(batch: BatchSummary): boolean {
  return batch.debrief?.status === 'ready' && batch.debrief.openQuestions > 0;
}
