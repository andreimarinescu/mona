import { Button, format } from '@mona/ui';
import { useId } from 'react';
import { useTranslation } from 'react-i18next';
import type { JournalEntry } from '../data/dto';
import { redoTarget } from '../data/journal';
import { useLang } from '../shell/useLang';
import { undoView } from './entryView';

export interface EntryUndoProps {
  entry: JournalEntry;
  undoneAt?: string;
  busy?: boolean;
  onUndo(entry: JournalEntry): void;
  onRedo(entry: JournalEntry): void;
}

export function EntryUndo({ entry, undoneAt, busy, onUndo, onRedo }: EntryUndoProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const hint = useId();
  const view = undoView(entry);
  if (view === 'live') {
    return (
      <Button variant="quiet" size="sm" icon="undo" disabled={busy} onClick={() => onUndo(entry)}>
        {t('common.undo')}
      </Button>
    );
  }
  if (view === 'superseded') {
    return (
      <span className="inline-flex items-center gap-2">
        <span className="font-ui text-[13px] leading-[18px] text-text-muted" id={hint}>
          {t('activity.undoState.superseded')}
        </span>
        <Button variant="quiet" size="sm" icon="undo" disabled aria-describedby={hint}>
          {t('common.undo')}
        </Button>
      </span>
    );
  }
  if (view === 'undone') {
    const redo = redoTarget(entry);
    return (
      <span className="inline-flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-surface-sunken px-3 py-1 font-ui text-[13px] leading-[18px] text-text">
          {undoneAt ? t('activity.undoneAt', { time: format.time(undoneAt, lang) }) : t('activity.undoState.undone')}
        </span>
        {redo ? (
          <Button variant="quiet" size="sm" icon="undo" disabled={busy} onClick={() => onRedo(entry)}>
            {t('common.redo')}
          </Button>
        ) : null}
      </span>
    );
  }
  return null;
}
