import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { ApplyResult, CorrectionRequest, DocumentDetail, DocumentSummary, FileOpResult, LikeThisResult, Page, Reason } from './dto';
import { get, post, retryTransient } from './http';
import { invalidateAfterWrite } from './journal';
import { pollDelay, pollStopsOn } from './polling';

export const REVIEW_LIMIT = 200;

export interface ReviewFilter {
  reason?: Reason;
  entityId?: string;
}

export function useReviewList(filter: ReviewFilter = {}) {
  return useQuery({
    queryKey: ['review', filter],
    queryFn: ({ signal }) => get<Page<DocumentSummary>>('/api/review', { ...filter, limit: REVIEW_LIMIT }, signal),
  });
}

export function useDocument(id: string | undefined) {
  return useQuery({
    queryKey: ['document', id],
    enabled: !!id,
    retry: retryTransient,
    queryFn: ({ signal }) => get<DocumentDetail>(`/api/documents/${id}`, undefined, signal),
    refetchInterval: (query) => (!pollStopsOn(query.state.error) && query.state.data?.status === 'processing' ? pollDelay(0) : false),
  });
}

export const confirmDocument = (id: string) => post<FileOpResult>(`/api/documents/${id}/confirm`);
export const correctDocument = (id: string, body: CorrectionRequest) => post<FileOpResult>(`/api/documents/${id}/correct`, body);
export const likeThis = (id: string) => post<LikeThisResult>(`/api/documents/${id}/like-this`);
export const applyRule = (ruleId: string, conversationId?: string) => post<ApplyResult>(`/api/rules/${ruleId}/apply`, conversationId ? { conversationId } : {});

export function useRefreshAfterWrite() {
  const qc = useQueryClient();
  return () => invalidateAfterWrite(qc);
}
