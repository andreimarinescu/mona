import { describe, expect, it } from 'vitest';
import type { Deadline } from '../../data/dto';
import { defaultReminderDate } from './reminderDate';

const deadline = (dueDate: string): Deadline => ({ id: 'ddl_a', documentId: 'doc_a', label: 'x', entityId: 'ent_a', entityName: 'A', dueDate, status: 'open', daysLeft: 0, reminder: null });

describe('default reminder date', () => {
  it('is three days before the deadline', () => {
    expect(defaultReminderDate(deadline('2026-10-15'), '2026-10-01')).toBe('2026-10-12');
  });

  it('is today when that day has passed', () => {
    expect(defaultReminderDate(deadline('2026-10-02'), '2026-10-01')).toBe('2026-10-01');
  });

  it('is tomorrow without a deadline', () => {
    expect(defaultReminderDate(undefined, '2026-10-31')).toBe('2026-11-01');
  });
});
