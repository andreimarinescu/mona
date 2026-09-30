import type { DocRefs, JournalEntry } from '../../data/dto';
import type { useEntryActions } from '../../journal/useEntryActions';

export interface ActivityContext {
  documents: DocRefs;
  rules: Record<string, { name: string }>;
  profileName: string;
  badgeHours: number;
  now: number;
  entriesById: Map<number, JournalEntry>;
  actions: ReturnType<typeof useEntryActions>;
}
