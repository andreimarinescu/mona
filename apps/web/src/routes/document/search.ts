import { format, type Lang } from '@mona/ui';
import { calendarDate } from '../../data/calendar';
import type { ExtractedField, FieldKey } from '../../data/dto';

export interface DocumentSearch {
  page?: number;
  q?: string;
  field?: FieldKey;
}

const FIELD_KEYS: FieldKey[] = ['entity', 'counterparty', 'issuer', 'reference', 'doc_type', 'doc_date', 'period_start', 'period_end', 'amount', 'due_date', 'addressee'];
const MAX_Q = 200;

/** C2 §4.4: the viewer deep link's `page`, `q` and `field`. Anything malformed is dropped. */
export function parseDocumentSearch(raw: Record<string, unknown>): DocumentSearch {
  const out: DocumentSearch = {};
  const page = typeof raw.page === 'number' ? raw.page : typeof raw.page === 'string' && /^\d{1,4}$/.test(raw.page) ? Number(raw.page) : NaN;
  if (Number.isInteger(page) && page >= 1) out.page = page;
  const q = typeof raw.q === 'string' ? raw.q : typeof raw.q === 'number' ? String(raw.q) : '';
  if (q.trim()) out.q = q.trim().slice(0, MAX_Q);
  if (FIELD_KEYS.includes(raw.field as FieldKey)) out.field = raw.field as FieldKey;
  return out;
}

/** The page to open: the link's (default 1), kept inside the document. */
export function clampPage(page: number | undefined, pageCount: number | null): number {
  const wanted = page ?? 1;
  return Math.max(1, pageCount && pageCount > 0 ? Math.min(wanted, pageCount) : wanted);
}

/** What "Show on page" sends to pdf.js find: the field's findQuery (C5 §7), else its value. */
export function showOnPage(field: ExtractedField): { query: string; page: number } {
  return { query: field.evidence.findQuery || field.value, page: field.evidence.page };
}

const DATE_FIELDS: FieldKey[] = ['doc_date', 'period_start', 'period_end', 'due_date'];

export function formatFieldValue(field: ExtractedField, lang: Lang): string {
  if (field.money) return format.money(field.money.value, field.money.currency, lang);
  if (DATE_FIELDS.includes(field.key) && /^\d{4}-\d{2}-\d{2}$/.test(field.value)) return format.date(calendarDate(field.value), lang);
  return field.value;
}
