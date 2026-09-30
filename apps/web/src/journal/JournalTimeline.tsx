import { Avatar, MonaAvatar, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { DocRefs, JournalEntry } from '../data/dto';
import { useLang } from '../shell/useLang';
import { EntryUndo } from './EntryUndo';
import { entryTitle, placeLabel } from './entryView';
import { useEntryActions } from './useEntryActions';

export interface JournalTimelineProps {
  entries: JournalEntry[];
  documents?: DocRefs;
  profileName?: string;
}

export function JournalTimeline({ entries, documents = {}, profileName = '' }: JournalTimelineProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const actions = useEntryActions();
  const byId = new Map(entries.map((e) => [e.id, e]));
  if (entries.length === 0) return <p className="m-0 text-text-muted">{t('activity.timeline.empty')}</p>;
  return (
    <ol className="m-0 flex list-none flex-col gap-3 p-0" aria-label={t('activity.timeline.label')}>
      {entries.map((entry) => {
        const place = placeLabel(entry.after, t);
        const undoneAt = entry.undoneBy !== undefined ? byId.get(entry.undoneBy)?.at : undefined;
        return (
          <li key={entry.id} className="flex items-start gap-3" data-journal-id={entry.id}>
            {entry.actor === 'mona' ? <MonaAvatar size={28} /> : <Avatar name={profileName || t('activity.you')} size={28} />}
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className={`font-ui text-[15px] leading-[22px] text-text ${entry.undoState === 'undone' ? 'line-through' : ''}`}>
                {entryTitle(entry, documents, {}, t)}
              </span>
              <span className="font-ui text-[13px] leading-[18px] text-text-muted">
                {[
                  `${format.date(entry.at, lang, 'medium')} ${format.time(entry.at, lang)}`,
                  place,
                  t('activity.journalNumber', { id: format.number(entry.id, lang, { useGrouping: false }) }),
                ]
                  .filter(Boolean)
                  .join(' · ')}
              </span>
              <EntryUndo entry={entry} undoneAt={undoneAt} busy={actions.busy} onUndo={actions.undo} onRedo={actions.redo} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}
