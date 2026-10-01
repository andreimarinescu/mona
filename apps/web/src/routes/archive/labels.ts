import { format, type Lang } from '@mona/ui';
import { calendarDate } from '../../data/calendar';
import type { DocumentSummary } from '../../data/dto';

export function dateLabel(date: string | null, lang: Lang): string {
  return date ? format.date(calendarDate(date), lang, 'medium') : '—';
}

export function amountLabel(doc: Pick<DocumentSummary, 'amount'>, lang: Lang): string {
  return doc.amount ? format.money(doc.amount.value, doc.amount.currency, lang) : '—';
}
