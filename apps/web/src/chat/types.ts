import type { UIMessage } from 'ai';
import type { Lang } from '@mona/ui';
import type { Deadline, DocumentSummary, Draft, ExportPack, Interview, IntakeItem, RulePreview } from '../data/dto';

/** A file dropped on the composer: uploaded to Intake (C3 §2), shown on the message, never sent to the model. */
export interface Attachment {
  name: string;
  type: string;
  sizeBytes: number;
  outcome: IntakeItem['outcome'] | null;
  documentId: string | null;
}

export interface MonaMetadata {
  conversationId?: string;
  turnId?: string;
  replyLanguage?: Lang;
  reasoningMs?: number;
  attachments?: Attachment[];
}

export type MonaDataParts = {
  doc: DocumentSummary;
  deadline: Deadline;
  interview: Interview;
  rulePreview: RulePreview;
  draft: Draft;
  export: ExportPack;
};

export type MonaUIMessage = UIMessage<MonaMetadata, MonaDataParts>;
export type MonaPart = MonaUIMessage['parts'][number];

export interface PageContext {
  route: string;
  summary: string;
}
