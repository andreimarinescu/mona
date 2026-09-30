import type { TFunction } from 'i18next';
import type { DocRefs, JournalEntry, PathState } from '../data/dto';

export type UndoView = 'live' | 'superseded' | 'undone' | 'none';

export function undoView(entry: Pick<JournalEntry, 'undoState'>): UndoView {
  switch (entry.undoState) {
    case 'undoable':
      return 'live';
    case 'superseded':
      return 'superseded';
    case 'undone':
      return 'undone';
    default:
      return 'none';
  }
}

export function isPathState(value: unknown): value is PathState {
  return typeof value === 'object' && value !== null && 'location' in value && 'path' in value;
}

const BADGE_ACTIONS = new Set(['file', 'move', 'rename']);

/** C7 §6 read from an entry: Mona's live filing inside the badge window. */
export function badgeLive(entry: JournalEntry, badgeHours: number, now: number): boolean {
  return (
    entry.actor === 'mona' &&
    BADGE_ACTIONS.has(entry.action) &&
    entry.undoState === 'undoable' &&
    isPathState(entry.after) &&
    entry.after.status === 'filed' &&
    now - Date.parse(entry.at) < badgeHours * 3_600_000
  );
}

export function sendsToReview(entry: JournalEntry): boolean {
  return isPathState(entry.after) && entry.after.status === 'review';
}

export function placeLabel(state: PathState | Record<string, unknown> | null, t: TFunction): string | null {
  if (!isPathState(state)) return null;
  if (state.location === 'archive') return state.path.join(' / ');
  if (state.location === 'trash') return t('activity.place.trash');
  return state.status === 'review' || state.status === 'unreadable' ? t('activity.place.review') : t('activity.place.inbox');
}

export function docTitle(documents: DocRefs, id: string | undefined, t: TFunction): string {
  const ref = id ? documents[id] : undefined;
  if (!ref) return t('activity.unknownDocument');
  return ref.deleted ? t('activity.deletedDocument', { title: ref.title }) : ref.title;
}

export function entryTitle(entry: JournalEntry, documents: DocRefs, rules: Record<string, { name: string }>, t: TFunction): string {
  return t(`activity.action.${entry.action}`, {
    context: entry.actor,
    doc: docTitle(documents, entry.documentIds[0], t),
    rule: (entry.ruleId ? rules[entry.ruleId]?.name : undefined) ?? t('activity.unknownRule'),
  });
}
