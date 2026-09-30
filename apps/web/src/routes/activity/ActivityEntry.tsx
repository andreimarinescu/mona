import { Avatar, MonaAvatar, StatusPill, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { JournalEntry } from '../../data/dto';
import { EntryUndo } from '../../journal/EntryUndo';
import { badgeLive, entryTitle, placeLabel, sendsToReview } from '../../journal/entryView';
import { useLang } from '../../shell/useLang';
import type { ActivityContext } from './context';

export function ActivityEntry({ entry, ctx, nested = false }: { entry: JournalEntry; ctx: ActivityContext; nested?: boolean }) {
  const { t } = useTranslation();
  const lang = useLang();
  const undone = entry.undoState === 'undone';
  const place = placeLabel(entry.after, t);
  const undoneAt = entry.undoneBy !== undefined ? ctx.entriesById.get(entry.undoneBy)?.at : undefined;
  const detail = [place, t('activity.journalNumber', { id: format.number(entry.id, lang, { useGrouping: false }) })].filter(Boolean).join(' · ');
  return (
    <li
      className={`flex flex-wrap items-start gap-x-4 gap-y-2 py-3 ${nested ? 'border-t border-border pl-0' : ''}`}
      data-journal-id={entry.id}
      data-undo-state={entry.undoState}
    >
      <time dateTime={entry.at} className="w-[52px] shrink-0 pt-0.5 font-ui text-[14px] leading-5 text-text-muted">
        {format.time(entry.at, lang)}
      </time>
      <span className="shrink-0">{entry.actor === 'mona' ? <MonaAvatar size={nested ? 24 : 32} /> : <Avatar name={ctx.profileName || t('activity.you')} size={nested ? 24 : 32} />}</span>
      <div className="flex min-w-[200px] flex-1 flex-col gap-0.5">
        <span className={`font-ui text-[15px] leading-[22px] text-text ${undone ? 'line-through' : ''}`}>{entryTitle(entry, ctx.documents, ctx.rules, t)}</span>
        <span className="font-ui text-[13px] leading-[18px] text-text-muted">{detail}</span>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        {badgeLive(entry, ctx.badgeHours, ctx.now) ? <StatusPill status="filed" size="sm" lang={lang} /> : null}
        {sendsToReview(entry) && !undone ? <StatusPill status="review" size="sm" lang={lang} /> : null}
        <EntryUndo entry={entry} undoneAt={undoneAt} busy={ctx.actions.busy} onUndo={ctx.actions.undo} onRedo={ctx.actions.redo} />
      </div>
    </li>
  );
}
