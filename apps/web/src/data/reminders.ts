import type { ReminderResult } from './dto';
import { post, request } from './http';

export interface ReminderRequest {
  deadlineId?: string;
  documentId?: string;
  remindOn: string;
  note?: string;
}

export const createReminder = (body: ReminderRequest) => post<ReminderResult>('/api/reminders', body);
export const cancelReminder = (id: string) => request<void>('DELETE', `/api/reminders/${id}`);
