import { describe, expect, it } from 'vitest';
import { addDays, calendarDate, toIsoDate } from './calendar';

describe('calendar dates', () => {
  it('parses a YYYY-MM-DD day as a local calendar date', () => {
    const d = calendarDate('2026-10-02');
    expect([d.getFullYear(), d.getMonth(), d.getDate()]).toEqual([2026, 9, 2]);
  });

  it('adds days across month ends', () => {
    expect(addDays('2026-10-30', 3)).toBe('2026-11-02');
    expect(addDays('2026-03-01', -1)).toBe('2026-02-28');
    expect(toIsoDate(new Date(2026, 0, 5))).toBe('2026-01-05');
  });
});
