import { format, type Lang } from '@mona/ui';
import type { TFunction } from 'i18next';
import type { Rule } from '../../data/dto';

/** Corrections since the rule last changed: above this the row says "check" in words. */
export const CHECK_CORRECTIONS_ABOVE = 2;

export const needsCheck = (rule: Pick<Rule, 'correctionsSince'>) => rule.correctionsSince > CHECK_CORRECTIONS_ABOVE;

const sameDay = (a: Date, b: Date) => a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();

/** Time for today, then Yesterday, a weekday inside the week, else the day and month; Never when it hasn't fired. */
export function lastFiredLabel(iso: string | undefined, now: number, lang: Lang, t: TFunction): string {
  if (!iso) return t('rules.row.never');
  const at = new Date(iso);
  const today = new Date(now);
  if (sameDay(at, today)) return format.time(at, lang);
  const yesterday = new Date(now - 86_400_000);
  if (sameDay(at, yesterday)) return t('rules.row.yesterday');
  const days = (new Date(today.getFullYear(), today.getMonth(), today.getDate()).getTime() - new Date(at.getFullYear(), at.getMonth(), at.getDate()).getTime()) / 86_400_000;
  if (days < 7) return new Intl.DateTimeFormat(lang === 'fr' ? 'fr-FR' : lang === 'ro' ? 'ro-RO' : 'en-GB', { weekday: 'long' }).format(at);
  return format.date(at, lang, 'dayMonth');
}

export function destinationText(rule: Pick<Rule, 'destination'>): string {
  return rule.destination.join(' / ');
}

export function todayStart(now = Date.now()): string {
  const d = new Date(now);
  return new Date(d.getFullYear(), d.getMonth(), d.getDate()).toISOString();
}

export function learnedWhen(createdAt: string, now: number, lang: Lang, t: TFunction): string {
  const at = new Date(createdAt);
  const today = new Date(now);
  if (sameDay(at, today)) return t('rules.learned.today');
  if (sameDay(at, new Date(now - 86_400_000))) return t('rules.learned.yesterday');
  return format.date(at, lang, 'dayMonth');
}
