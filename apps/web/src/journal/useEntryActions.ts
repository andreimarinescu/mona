import { useCallback, useState } from 'react';
import type { JournalEntry, UndoTarget } from '../data/dto';
import { redoTarget, useUndoRunner } from '../data/journal';

/** Undo and redo for one screen: one request at a time, and a flag for the buttons. */
export function useEntryActions() {
  const run = useUndoRunner();
  const [busy, setBusy] = useState(false);
  const exec = useCallback(
    async (target: UndoTarget | null, kind: 'undo' | 'redo') => {
      if (!target) return;
      setBusy(true);
      try {
        await run(target, kind);
      } finally {
        setBusy(false);
      }
    },
    [run],
  );
  return {
    busy,
    undo: (entry: JournalEntry) => exec({ journalId: entry.id }, 'undo'),
    redo: (entry: JournalEntry) => exec(redoTarget(entry), 'redo'),
    undoGroup: (groupId: string) => exec({ groupId }, 'undo'),
    redoGroup: (groupId: string) => exec({ groupId }, 'redo'),
  };
}
