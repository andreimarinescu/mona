import { format } from '@mona/ui';
import { calendarDate } from '../../data/calendar';
import { useLang } from '../../shell/useLang';

export const URGENT_DAYS = 3;

/** Weekday and day number; urgent (3 days or fewer, or overdue) on accent-soft, otherwise sunken. */
export function DateTile({ date, daysLeft }: { date: string; daysLeft: number }) {
  const lang = useLang();
  const d = calendarDate(date);
  const weekday = new Intl.DateTimeFormat(lang === 'fr' ? 'fr-FR' : lang === 'ro' ? 'ro-RO' : 'en-GB', { weekday: 'short' }).format(d);
  const urgent = daysLeft <= URGENT_DAYS;
  return (
    <span
      aria-hidden
      data-urgent={urgent ? '' : undefined}
      className={`inline-flex size-12 shrink-0 flex-col items-center justify-center rounded-md font-ui leading-none ${urgent ? 'bg-accent-soft text-accent-strong' : 'bg-surface-sunken text-text'}`}
    >
      <span className="text-[11px] font-semibold tracking-[0.08em] uppercase">{weekday.replace('.', '')}</span>
      <span className="text-[20px] font-semibold tabular-nums">{format.number(d.getDate(), lang, { useGrouping: false })}</span>
    </span>
  );
}
