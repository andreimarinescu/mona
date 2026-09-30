import { describe, expect, it } from 'vitest';
import type { DocumentSummary, Reason } from '../../data/dto';
import { mergeQueue, neighbourAfter, omit, reasonCounts } from './queue';

const d = (id: string, arrivedAt: string, reasons: Reason[] = ['low']) => ({ id, arrivedAt, reasons }) as DocumentSummary;

describe('queue helpers', () => {
  const a = d('a', '2026-09-28T10:00:00Z');
  const b = d('b', '2026-09-29T10:00:00Z');
  const c = d('c', '2026-09-30T10:00:00Z');

  it('keeps a corrected document in its place among the server items', () => {
    expect(mergeQueue([a, c], { b }).map((x) => x.id)).toEqual(['a', 'b', 'c']);
  });

  it('does not list a corrected document twice', () => {
    expect(mergeQueue([a, b], { b }).map((x) => x.id)).toEqual(['a', 'b']);
  });

  it('goes to the next document after one leaves, else the previous, else nothing', () => {
    expect(neighbourAfter([a, b, c], 'b')).toBe('c');
    expect(neighbourAfter([a, b, c], 'c')).toBe('b');
    expect(neighbourAfter([a], 'a')).toBeUndefined();
  });

  it('counts each reason a document carries', () => {
    expect(reasonCounts([d('x', '', ['low', 'conflict']), d('y', '', ['entity']), d('z', '', ['low'])])).toEqual({ low: 2, entity: 1, conflict: 1, unreadable: 0 });
  });

  it('omits a key without touching the original', () => {
    const original = { a: 1, b: 2 };
    expect(omit(original, 'a')).toEqual({ b: 2 });
    expect(original).toEqual({ a: 1, b: 2 });
  });
});
