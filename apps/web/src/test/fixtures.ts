import type { JournalEntry } from '../data/dto';

export function entry(over: Partial<JournalEntry> = {}): JournalEntry {
  return {
    id: 4231,
    at: '2026-10-01T08:20:00.000Z',
    actor: 'mona',
    via: 'pipeline',
    action: 'file',
    documentIds: ['doc_a'],
    subjectId: null,
    before: { location: 'inbox', path: [], fileName: 'scan.pdf', status: 'processing' },
    after: { location: 'archive', path: ['Cabinet Marchand', '2026 Cabinet Marchand'], fileName: 'scan.pdf', status: 'filed' },
    groupId: null,
    ruleId: null,
    confidence: 92,
    band: 'high',
    undoable: true,
    undoState: 'undoable',
    undoOf: null,
    ...over,
  };
}
