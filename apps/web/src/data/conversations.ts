import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import type { MonaUIMessage } from '../chat/types';
import type { ConversationSummary, Feed } from './dto';
import { get, retryTransient } from './http';

export const CONVERSATIONS_PAGE = 30;

const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

/** C2 §13 is a `Feed`; a bare array (the api before it pages and searches) is read as one page, filtered here. */
export function asFeed(body: Feed<ConversationSummary> | ConversationSummary[], q = ''): Feed<ConversationSummary> {
  if (!Array.isArray(body)) return body;
  const needle = fold(q.trim());
  return { items: needle ? body.filter((c) => fold(c.title).includes(needle)) : body, nextCursor: null };
}

export function useConversations(q: string) {
  const query = useInfiniteQuery({
    queryKey: ['conversations', q],
    initialPageParam: undefined as string | undefined,
    queryFn: async ({ pageParam, signal }) =>
      asFeed(await get<Feed<ConversationSummary> | ConversationSummary[]>('/api/conversations', { q: q.trim() || undefined, cursor: pageParam, limit: CONVERSATIONS_PAGE }, signal), q),
    getNextPageParam: (last) => last.nextCursor ?? undefined,
  });
  return { ...query, items: query.data?.pages.flatMap((p) => p.items) ?? [] };
}

export function useTranscript(conversationId: string | undefined) {
  return useQuery({
    queryKey: ['conversation-messages', conversationId],
    enabled: !!conversationId,
    staleTime: Infinity,
    gcTime: 0,
    retry: retryTransient,
    queryFn: ({ signal }) => get<MonaUIMessage[]>(`/api/conversations/${conversationId}/messages`, undefined, signal),
  });
}
