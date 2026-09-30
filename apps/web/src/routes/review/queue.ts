import type { DocumentSummary, Reason } from '../../data/dto';

export const REASONS: Reason[] = ['low', 'entity', 'conflict', 'unreadable'];

export function omit<T>(record: Record<string, T>, key: string): Record<string, T> {
  return Object.fromEntries(Object.entries(record).filter(([k]) => k !== key));
}

/** Server items plus the documents corrected this session, which stay listed until their scope prompt is answered. */
export function mergeQueue(server: DocumentSummary[], kept: Record<string, DocumentSummary>): DocumentSummary[] {
  const present = new Set(server.map((d) => d.id));
  const extra = Object.values(kept).filter((d) => !present.has(d.id));
  if (extra.length === 0) return server;
  return [...server, ...extra].sort((a, b) => Date.parse(a.arrivedAt) - Date.parse(b.arrivedAt));
}

export function reasonCounts(items: DocumentSummary[]): Record<Reason, number> {
  const counts: Record<Reason, number> = { low: 0, entity: 0, conflict: 0, unreadable: 0 };
  for (const doc of items) for (const reason of doc.reasons) counts[reason] += 1;
  return counts;
}

/** Where to go once `id` leaves the queue: the next document, else the previous one. */
export function neighbourAfter(items: DocumentSummary[], id: string): string | undefined {
  const i = items.findIndex((d) => d.id === id);
  if (i === -1) return items[0]?.id;
  return items[i + 1]?.id ?? items[i - 1]?.id;
}
