import { describe, expect, it } from 'vitest';
import { dayRelation, groupByDay } from './days';

describe('day grouping', () => {
  it('buckets items by local day, keeping the incoming order', () => {
    const items = [
      { at: new Date(2026, 9, 1, 14, 0).toISOString(), n: 1 },
      { at: new Date(2026, 9, 1, 9, 0).toISOString(), n: 2 },
      { at: new Date(2026, 8, 30, 18, 0).toISOString(), n: 3 },
    ];
    const days = groupByDay(items, (i) => i.at);
    expect(days.map((d) => d.items.map((i) => i.n))).toEqual([[1, 2], [3]]);
  });

  it('names today and yesterday', () => {
    const now = new Date(2026, 9, 1, 12, 0);
    expect(dayRelation(new Date(2026, 9, 1, 0, 5), now)).toBe('today');
    expect(dayRelation(new Date(2026, 8, 30, 23, 55), now)).toBe('yesterday');
    expect(dayRelation(new Date(2026, 8, 29), now)).toBe('other');
  });
});
