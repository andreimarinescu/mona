import { Button, Input, format } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { calendarDate, toIsoDate } from '../../data/calendar';
import type { Deadline, DocumentDetail } from '../../data/dto';
import { errorKey, errorValues } from '../../data/errors';
import { toastFailure } from '../../data/journal';
import { cancelReminder, createReminder } from '../../data/reminders';
import { useRefreshAfterWrite } from '../../data/review';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { defaultReminderDate } from './reminderDate';

function DueLine({ deadline }: { deadline: Deadline }) {
  const { t } = useTranslation();
  const lang = useLang();
  const date = format.date(calendarDate(deadline.dueDate), lang);
  const n = format.number(Math.abs(deadline.daysLeft), lang);
  const when =
    deadline.daysLeft === 0
      ? t('viewer.reminder.dueToday')
      : deadline.daysLeft > 0
        ? t('viewer.reminder.dueIn', { count: deadline.daysLeft, n })
        : t('viewer.reminder.overdue', { count: -deadline.daysLeft, n });
  return (
    <p className="m-0 font-ui text-[15px] leading-[22px] text-text" data-testid="deadline-line">
      {t('viewer.reminder.due', { date, when })}
    </p>
  );
}

export function ReminderControl({ doc }: { doc: DocumentDetail }) {
  const { t } = useTranslation();
  const lang = useLang();
  const refresh = useRefreshAfterWrite();
  const deadline = doc.deadlines.find((d) => d.status === 'open');
  const today = toIsoDate(new Date());
  const [choosing, setChoosing] = useState(false);
  const [date, setDate] = useState(() => defaultReminderDate(deadline, today));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [local, setLocal] = useState<{ id: string; remindOn: string } | null>(null);
  const reminder = deadline ? deadline.reminder : local;

  async function set() {
    setBusy(true);
    setError(null);
    try {
      const result = await createReminder(deadline ? { deadlineId: deadline.id, remindOn: date } : { documentId: doc.id, remindOn: date });
      setLocal({ id: result.reminderId, remindOn: result.remindOn });
      setChoosing(false);
      toasts.push({ key: 'reminder', message: 'toast.reminderSet', values: { date: format.date(calendarDate(result.remindOn), lang) }, tone: 'neutral' });
      await refresh();
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  async function cancel() {
    if (!reminder) return;
    setBusy(true);
    try {
      await cancelReminder(reminder.id);
      setLocal(null);
      await refresh();
    } catch (err) {
      toastFailure(err);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section aria-labelledby="reminder-heading" className="flex flex-col gap-3" data-testid="reminder">
      <h3 id="reminder-heading" className="m-0 text-text [font:var(--type-heading)]">
        {t('viewer.reminder.title')}
      </h3>
      {deadline ? <DueLine deadline={deadline} /> : <p className="m-0 text-text-muted">{t('viewer.reminder.noDeadline')}</p>}
      {reminder ? (
        <div className="flex flex-wrap items-center gap-3">
          <span className="inline-flex items-center gap-2 font-ui text-[15px] leading-[22px] text-text" role="status">
            {t('viewer.reminder.set', { date: format.date(calendarDate(reminder.remindOn), lang) })}
          </span>
          <Button variant="quiet" size="sm" disabled={busy} onClick={() => void cancel()}>
            {t('viewer.reminder.cancel')}
          </Button>
        </div>
      ) : choosing ? (
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            void set();
          }}
        >
          <Input type="date" label={t('viewer.reminder.on')} value={date} min={today} required onChange={(e) => setDate(e.target.value)} error={error ? t(errorKey(error), errorValues(error)) : undefined} />
          <div className="flex flex-wrap gap-3">
            <Button type="submit" variant="primary" size="sm" loading={busy} disabled={!date || date < today}>
              {t('viewer.reminder.save')}
            </Button>
            <Button type="button" variant="quiet" size="sm" onClick={() => setChoosing(false)}>
              {t('common.cancel')}
            </Button>
          </div>
        </form>
      ) : (
        <div>
          <Button variant="secondary" size="sm" icon="bell" onClick={() => setChoosing(true)}>
            {t('viewer.reminder.remindMe')}
          </Button>
        </div>
      )}
    </section>
  );
}
