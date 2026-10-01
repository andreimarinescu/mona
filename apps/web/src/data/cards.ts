import { useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import type { AnswerResult, ApplyAllResult, Deadline, Draft, Interview, InterviewQuestion, RulePreview } from './dto';
import { ApiError, get, post, request, retryTransient, withQuery } from './http';
import { jobRefetchInterval } from './polling';

export const interviewKey = (id: string) => ['interview', id] as const;
export const rulePreviewKey = (ruleId: string) => ['rule-preview', ruleId] as const;
export const draftKey = (id: string) => ['draft', id] as const;

function usePollingSince() {
  const since = useRef({ at: 0 });
  return () => {
    if (since.current.at === 0) since.current.at = Date.now();
    return Date.now() - since.current.at;
  };
}

/** C2 §1.5: the card's snapshot first, then `GET /api/interviews/{id}` while it is generating. */
export function useInterview(snapshot: Interview) {
  const elapsed = usePollingSince();
  return useQuery({
    queryKey: interviewKey(snapshot.id),
    initialData: snapshot,
    staleTime: Infinity,
    retry: retryTransient,
    queryFn: ({ signal }) => get<Interview>(`/api/interviews/${snapshot.id}`, undefined, signal),
    refetchInterval: (query) => jobRefetchInterval(query.state.data?.status, 'generating', query.state.error, elapsed()),
  });
}

/** C2 §1.5: a rule preview is fetched on render and after Apply, never polled; the snapshot stands in until then. */
export function useRulePreview(ruleId: string, snapshot?: RulePreview) {
  return useQuery({
    queryKey: rulePreviewKey(ruleId),
    initialData: snapshot,
    initialDataUpdatedAt: 0,
    staleTime: 30_000,
    retry: retryTransient,
    queryFn: ({ signal }) => get<RulePreview>(`/api/rules/${ruleId}/preview`, { limit: 20 }, signal),
  });
}

export function useDraft(snapshot: Draft) {
  const elapsed = usePollingSince();
  return useQuery({
    queryKey: draftKey(snapshot.id),
    initialData: snapshot,
    staleTime: Infinity,
    retry: retryTransient,
    queryFn: ({ signal }) => get<Draft>(`/api/drafts/${snapshot.id}`, undefined, signal),
    refetchInterval: (query) => jobRefetchInterval(query.state.data?.status, 'generating', query.state.error, elapsed()),
  });
}

const withConversation = (conversationId: string | undefined) => (conversationId ? { conversationId } : {});

export const answerQuestion = (interviewId: string, questionId: string, body: { optionId: string } | { freeText: string }, conversationId?: string) =>
  post<AnswerResult>(`/api/interviews/${interviewId}/questions/${questionId}/answer`, { ...body, ...withConversation(conversationId) });

export const skipQuestion = (interviewId: string, questionId: string, conversationId?: string) =>
  post<InterviewQuestion>(`/api/interviews/${interviewId}/questions/${questionId}/skip`, withConversation(conversationId));

export const applyAll = (interviewId: string, questionId: string, conversationId?: string) =>
  post<ApplyAllResult>(`/api/interviews/${interviewId}/questions/${questionId}/apply`, withConversation(conversationId));

export const markDeadline = (id: string, status: Deadline['status']) => request<Deadline>('PATCH', `/api/deadlines/${id}`, { json: { status } });

/** Puts an answered or skipped question into the cached interview, the way the server now has it. */
export function storeQuestion(qc: QueryClient, interviewId: string, question: InterviewQuestion, status?: Interview['status']) {
  qc.setQueryData<Interview>(interviewKey(interviewId), (iv) => {
    if (!iv) return iv;
    const questions = iv.questions.map((q) => (q.id === question.id ? question : q));
    return { ...iv, questions, openQuestions: questions.filter((q) => q.status === 'open').length, status: status ?? iv.status };
  });
}

export function storePreviews(qc: QueryClient, previews: RulePreview[]) {
  for (const p of previews) qc.setQueryData(rulePreviewKey(p.rule.id), p);
}

/** Refreshes every card query after a turn, so earlier cards show what the turn changed. */
export function useRefreshCards() {
  const qc = useQueryClient();
  return () =>
    Promise.all(['interview', 'rule-preview', 'draft', 'export'].map((key) => qc.invalidateQueries({ queryKey: [key] })));
}

export async function downloadDraft(draft: Draft, conversationId?: string): Promise<{ blob: Blob; name: string }> {
  const url = withQuery(draft.docxUrl ?? `/api/drafts/${draft.id}/docx`, withConversation(conversationId));
  const res = await fetch(url, { credentials: 'same-origin' });
  if (!res.ok) {
    const body = (await res.json().catch(() => null)) as { error?: { code?: string; message?: string } } | null;
    throw new ApiError(res.status, body?.error?.code ?? 'internal', body?.error?.message ?? res.statusText);
  }
  const disposition = res.headers.get('content-disposition') ?? '';
  const name = /filename\*=UTF-8''([^;]+)/i.exec(disposition)?.[1] ?? /filename="?([^";]+)"?/i.exec(disposition)?.[1] ?? `${draft.title ?? 'draft'}.docx`;
  return { blob: await res.blob(), name: decodeURIComponent(name) };
}
