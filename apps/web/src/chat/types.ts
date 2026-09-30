import type { UIMessage } from 'ai';
import type { DocStatus, Lang } from '../ds';

export interface Money {
  value: number;
  currency: string;
}

/** The subset of C1 `DocumentSummary` the spike card shows. */
export interface DocCardData {
  id: string;
  title: string;
  fileName: string;
  path: string[];
  entityName: string | null;
  categoryId: string | null;
  date: string | null;
  amount?: Money;
  dueDate: string | null;
  status: DocStatus;
  confidence: number | null;
}

export interface InterviewQuestion {
  id: string;
  question: string;
  lang: Lang;
  affectsCount: number;
  options: { id: string; label: string; suggested?: boolean }[];
}

export interface InterviewCardData {
  id: string;
  status: string;
  questions: InterviewQuestion[];
}

export interface MonaMetadata {
  conversationId?: string;
  turnId?: string;
  replyLanguage?: Lang;
  reasoningMs?: number;
}

export type MonaUIMessage = UIMessage<MonaMetadata, { doc: DocCardData; interview: InterviewCardData }>;

export interface PageContext {
  route: string;
  summary: string;
}
