import { useInfiniteQuery, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useCallback, useMemo } from 'react';
import { toasts } from '../toast/store';
import type { ActivityPage, DocRefs, GroupView, JournalEntry, UndoResult, UndoTarget } from './dto';
import { errorKey, errorValues } from './errors';
import { get, post } from './http';

export interface ActivityFilters {
  actor?: 'mona' | 'user';
  entityId?: string;
  kind?: string;
  q?: string;
}

export const ACTIVITY_PAGE_SIZE = 30;

export function useActivity(filters: ActivityFilters) {
  const query = useInfiniteQuery({
    queryKey: ['activity', filters],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => get<ActivityPage>('/api/activity', { ...filters, cursor: pageParam, limit: ACTIVITY_PAGE_SIZE }, signal),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  const merged = useMemo(() => {
    const pages = query.data?.pages ?? [];
    const documents: DocRefs = {};
    const rules: Record<string, { name: string }> = {};
    for (const p of pages) {
      Object.assign(documents, p.documents);
      Object.assign(rules, p.rules);
    }
    return { items: pages.flatMap((p) => p.items), documents, rules };
  }, [query.data]);
  return { ...query, ...merged };
}

export function useGroupEntries(groupId: string, enabled: boolean) {
  return useQuery({
    queryKey: ['group', groupId],
    enabled,
    queryFn: ({ signal }) => get<GroupView>(`/api/journal/groups/${groupId}`, undefined, signal),
  });
}

export function undoTargetPath(target: UndoTarget): string {
  return 'journalId' in target ? `/api/journal/${target.journalId}/undo` : `/api/journal/groups/${target.groupId}/undo`;
}

export const postUndo = (target: UndoTarget, conversationId?: string) => post<UndoResult>(undoTargetPath(target), conversationId ? { conversationId } : {});

const VOLATILE = ['review', 'document', 'activity', 'group', 'batch', 'batches', 'shell-counts', 'rule-preview', 'interview', 'archive', 'folders'];

export function invalidateAfterWrite(qc: QueryClient) {
  return Promise.all(VOLATILE.map((key) => qc.invalidateQueries({ queryKey: [key] })));
}

export function toastFailure(err: unknown) {
  toasts.push({ key: 'failed', message: errorKey(err), values: errorValues(err), tone: 'danger' });
}

export type UndoKind = 'undo' | 'redo';

/** Runs a C2 §9.2 undo or redo, reports it in a toast and refreshes what it changed. */
export function useUndoRunner() {
  const qc = useQueryClient();
  return useCallback(
    async (target: UndoTarget, kind: UndoKind = 'undo', conversationId?: string): Promise<UndoResult | null> => {
      try {
        const result = await postUndo(target, conversationId);
        toasts.push({ key: kind, message: kind === 'undo' ? 'toast.undone' : 'toast.redone', count: Math.max(result.undone.length, 1), tone: 'neutral' });
        if (result.skipped.length > 0) {
          toasts.push({ key: 'skipped', message: 'toast.undoSkipped', count: result.skipped.length, tone: 'warning' });
        }
        return result;
      } catch (err) {
        toastFailure(err);
        return null;
      } finally {
        void invalidateAfterWrite(qc);
      }
    },
    [qc],
  );
}

export function redoTarget(entry: JournalEntry): UndoTarget | null {
  return entry.undoState === 'undone' && entry.undoneBy !== undefined ? { journalId: entry.undoneBy } : null;
}
