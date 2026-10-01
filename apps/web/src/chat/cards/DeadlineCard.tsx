import { Badge, Button, Icon, format, type Lang } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import { markDeadline } from '../../data/cards';
import { calendarDate, toIsoDate } from '../../data/calendar';
import type { Deadline } from '../../data/dto';
import { toastFailure } from '../../data/journal';
import { createReminder } from '../../data/reminders';
import { defaultReminderDate } from '../../routes/document/reminderDate';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { useChatCard } from '../context';
import { CardShell } from './CardShell';

const URGENT_DAYS = 3;

/** Weekday and day number; urgent (≤ 3 days) on accent-soft. The due badge carries the urgency in words. */
export function DateTile({ date, urgent, lang }: { date: string; urgent: boolean; lang: Lang }) {
  const d = calendarDate(date);
  const word = (o: Intl.DateTimeFormatOptions) => new Intl.DateTimeFormat(lang, o).format(d).replace('.', '').toUpperCase();
  return (
    <span
      className={`inline-flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-md ${urgent ? 'bg-accent-soft text-accent-strong' : 'bg-surface-sunken text-text'}`}
      data-testid="date-tile"
      data-urgent={urgent}
    >
      <span className="mona-sr">{format.date(d, lang)}</span>
      <span aria-hidden className="font-ui text-[10px] leading-4 font-semibold tracking-[0.06em] whitespace-nowrap">
        {word({ weekday: 'short' })} · {word({ month: 'short' })}
      </span>
      <span aria-hidden className="font-voice text-[24px] leading-7">
        {format.number(d.getDate(), lang)}
      </span>
    </span>
  );
}

function DueBadge({ deadline }: { deadline: Deadline }) {
  const { t } = useTranslation();
  const lang = useLang();
  const n = format.number(Math.abs(deadline.daysLeft), lang);
  if (deadline.daysLeft < 0) return <Badge tone="danger">{t('deadline.overdue', { count: -deadline.daysLeft, n })}</Badge>;
  if (deadline.daysLeft === 0) return <Badge tone="warning">{t('deadline.dueToday')}</Badge>;
  return <Badge tone={deadline.daysLeft <= URGENT_DAYS ? 'warning' : 'neutral'}>{t('deadline.dueIn', { count: deadline.daysLeft, n })}</Badge>;
}

export function DeadlineCard({ deadline: snapshot }: { deadline: Deadline }) {
  const { t } = useTranslation();
  const lang = useLang();
  const card = useChatCard();
  const [deadline, setDeadline] = useState(snapshot);
  const [busy, setBusy] = useState<'remind' | 'done' | null>(null);
  const remindOn = defaultReminderDate(deadline, toIsoDate(new Date()));
  const dayMonth = (iso: string) => format.date(calendarDate(iso), lang, 'dayMonth');

  async function remind() {
    setBusy('remind');
    try {
      const result = await createReminder({ deadlineId: deadline.id, remindOn, conversationId: card.conversationId() });
      setDeadline((d) => result.deadline ?? { ...d, reminder: { id: result.reminderId, remindOn: result.remindOn } });
      toasts.push({ key: 'reminder', message: 'toast.reminderSet', values: { date: dayMonth(result.remindOn) }, tone: 'neutral' });
    } catch (err) {
      toastFailure(err);
    } finally {
      setBusy(null);
    }
  }

  async function done() {
    setBusy('done');
    try {
      setDeadline(await markDeadline(deadline.id, 'done'));
    } catch (err) {
      toastFailure(err);
    } finally {
      setBusy(null);
    }
  }

  return (
    <CardShell kind="deadline" id={deadline.id} label={deadline.label}>
      <div className="flex items-start gap-4">
        <DateTile date={deadline.dueDate} urgent={deadline.status === 'open' && deadline.daysLeft <= URGENT_DAYS} lang={lang} />
        <div className="flex min-w-0 flex-1 flex-col gap-1">
          <h3 className="m-0 font-ui text-[16px] leading-6 font-semibold text-text">{deadline.label}</h3>
          <p className="m-0 font-ui text-[14px] leading-5 text-text-muted">
            {deadline.paidBy ? `${deadline.entityName} · ${t('deadline.paidBy', { account: deadline.paidBy })}` : deadline.entityName}
          </p>
        </div>
        {deadline.amount ? (
          <strong className="shrink-0 font-ui text-[18px] leading-[26px] text-text tabular-nums">{format.money(deadline.amount.value, deadline.amount.currency, lang)}</strong>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {deadline.status === 'done' ? (
          <Badge tone="success">{t('deadline.markedDone')}</Badge>
        ) : (
          <DueBadge deadline={deadline} />
        )}
        {deadline.documentId ? (
          <InternalLink href={`/documents/${deadline.documentId}`} className="mona-btn mona-btn--secondary mona-btn--sm no-underline">
            <Icon name="file" size={16} />
            {t('deadline.openLetter')}
          </InternalLink>
        ) : null}
        {deadline.reminder ? (
          <span className="inline-flex items-center gap-1 font-ui text-[14px] leading-5 text-text-muted" data-testid="reminder-set">
            <Icon name="bell" size={16} />
            {t('deadline.reminderSet', { date: dayMonth(deadline.reminder.remindOn) })}
          </span>
        ) : deadline.status === 'open' ? (
          <Button size="sm" variant="secondary" icon="bell" loading={busy === 'remind'} disabled={busy !== null} onClick={() => void remind()}>
            {t('deadline.remindOn', { date: dayMonth(remindOn) })}
          </Button>
        ) : null}
        {deadline.status === 'open' ? (
          <Button size="sm" variant="ghost" icon="check" loading={busy === 'done'} disabled={busy !== null} onClick={() => void done()}>
            {t('deadline.done')}
          </Button>
        ) : null}
      </div>
    </CardShell>
  );
}
