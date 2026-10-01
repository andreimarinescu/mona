import { addDays } from '../../data/calendar';
import type { Deadline } from '../../data/dto';

/** Three days before the deadline, but never in the past; tomorrow when there is no deadline. */
export function defaultReminderDate(deadline: Deadline | undefined, today: string): string {
  if (!deadline) return addDays(today, 1);
  const early = addDays(deadline.dueDate, -3);
  return early > today ? early : today;
}
