import { format, type Lang } from '@mona/ui';
import type { TFunction } from 'i18next';
import type { BriefFacts, Deadline } from '../../data/dto';

export type TimeOfDay = 'morning' | 'afternoon' | 'evening';

export type BriefLink = { kind: 'review' } | { kind: 'activity' } | { kind: 'document'; documentId: string } | { kind: 'questions' };

export interface BriefSentence {
  id: 'greeting' | 'filed' | 'review' | 'due' | 'questions';
  text: string;
  link?: BriefLink;
}

export interface BriefContext {
  t: TFunction;
  lang: Lang;
  hour: number;
  name: string;
  /** The profile name is the practice name: greet without a form of address (C8 §5.6). */
  anonymous: boolean;
}

export function timeOfDay(hour: number): TimeOfDay {
  return hour < 12 ? 'morning' : hour < 18 ? 'afternoon' : 'evening';
}

/** The `{{when}}` phrase of a due sentence, from `Deadline.daysLeft`. */
export function whenPhrase(daysLeft: number, t: TFunction): string {
  if (daysLeft <= 0) return t('time.dueToday');
  if (daysLeft === 1) return t('time.dueTomorrow');
  return t('time.dueIn', { count: daysLeft });
}

/** C8 §5.6: overdue first, then the soonest. */
export function mostUrgent(dueSoon: Deadline[]): Deadline | undefined {
  return dueSoon.filter((d) => d.status === 'open').sort((a, b) => a.daysLeft - b.daysLeft)[0];
}

export function dueSentence(d: Deadline, ctx: Pick<BriefContext, 't' | 'lang'>): string {
  if (d.daysLeft < 0) return ctx.t('home.brief.overdue', { label: d.label });
  const when = whenPhrase(d.daysLeft, ctx.t);
  return d.amount
    ? ctx.t('home.brief.dueAmount', { label: d.label, amount: format.money(d.amount.value, d.amount.currency, ctx.lang), when })
    : ctx.t('home.brief.due', { label: d.label, when });
}

/** C8 §5.6: greeting, filed, review, the most urgent due item, pending questions; one sentence each, skipping those that don't apply. */
export function briefSentences(facts: BriefFacts, ctx: BriefContext): BriefSentence[] {
  const { t } = ctx;
  const out: BriefSentence[] = [];
  const tod = timeOfDay(ctx.hour);
  out.push({ id: 'greeting', text: ctx.anonymous ? t(`home.brief.greeting.${tod}`, { context: 'anon' }) : t(`home.brief.greeting.${tod}`, { name: ctx.name }) });
  out.push({
    id: 'filed',
    text: facts.filed.count === 0 ? t('home.brief.filedNone') : t(ctx.hour < 12 ? 'home.brief.filedOvernight' : 'home.brief.filedToday', { count: facts.filed.count }),
    link: { kind: 'activity' },
  });
  if (facts.needsReview.count > 0) out.push({ id: 'review', text: t('home.brief.review', { count: facts.needsReview.count }), link: { kind: 'review' } });
  const urgent = mostUrgent(facts.dueSoon);
  if (urgent) out.push({ id: 'due', text: dueSentence(urgent, ctx), link: urgent.documentId ? { kind: 'document', documentId: urgent.documentId } : undefined });
  if (facts.pendingInterview && facts.pendingInterview.openQuestions > 0) {
    out.push({ id: 'questions', text: t('home.brief.questions', { count: facts.pendingInterview.openQuestions }), link: { kind: 'questions' } });
  }
  return out;
}
