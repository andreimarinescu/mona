import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { LearnedItem, Page, RuleListItem, RulePatch, RulePreview } from './dto';
import { get, patch, retryTransient } from './http';
import { invalidateAfterWrite, toastFailure } from './journal';

export const RULES_LIMIT = 200;

export interface RuleFilter {
  q?: string;
  state?: 'draft' | 'active' | 'disabled';
  source?: 'interview' | 'correction' | 'seed';
  entityId?: string;
}

export function useRules(filter: RuleFilter = {}) {
  return useQuery({
    queryKey: ['rules', filter],
    queryFn: ({ signal }) => get<Page<RuleListItem>>('/api/rules', { ...filter, limit: RULES_LIMIT }, signal),
  });
}

export function useRule(id: string | undefined) {
  return useQuery({
    queryKey: ['rule', id],
    enabled: !!id,
    retry: retryTransient,
    queryFn: ({ signal }) => get<RuleListItem>(`/api/rules/${id}`, undefined, signal),
  });
}

export function useRulePreview(id: string | undefined) {
  return useQuery({
    queryKey: ['rule-preview', id],
    enabled: !!id,
    retry: retryTransient,
    queryFn: ({ signal }) => get<RulePreview>(`/api/rules/${id}/preview`, { limit: 50 }, signal),
  });
}

export function useLearned(since: string) {
  return useQuery({
    queryKey: ['learned', since],
    queryFn: ({ signal }) => get<LearnedItem[]>('/api/rules/learned', { since }, signal),
  });
}

export const patchRule = (id: string, body: RulePatch) => patch<RuleListItem>(`/api/rules/${id}`, body);

/** A PATCH to a rule, refreshed everywhere a rule shows; failures toast. */
export function usePatchRule() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: RulePatch }) => patchRule(id, body),
    onError: toastFailure,
    onSettled: () => invalidateAfterWrite(qc),
  });
}
