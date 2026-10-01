import { useQuery } from '@tanstack/react-query';
import type { CategoryDto, CategoryList, CategoryPatch, EntityDetail, EntityList, PersonDetail, SettingsThresholds, TemplatePreview } from './dto';
import { get, patch, request, retryTransient } from './http';
import { useSettings } from './hooks';

export function useEntityList() {
  return useQuery({ queryKey: ['entities-list'], queryFn: ({ signal }) => get<EntityList>('/api/entities', undefined, signal), staleTime: 60_000 });
}

export function useEntityDetail(id: string | null | undefined) {
  return useQuery({
    queryKey: ['entity-detail', id],
    enabled: !!id,
    retry: retryTransient,
    queryFn: ({ signal }) => get<EntityDetail>(`/api/entities/${id}`, undefined, signal),
    staleTime: 60_000,
  });
}

export function usePeople() {
  return useQuery({
    queryKey: ['people'],
    queryFn: ({ signal }) => get<{ items: PersonDetail[] }>('/api/people', undefined, signal).then((r) => r.items),
    staleTime: 60_000,
  });
}

const categoriesQuery = {
  queryKey: ['categories'],
  queryFn: ({ signal }: { signal: AbortSignal }) => get<CategoryList>('/api/categories', undefined, signal),
  staleTime: 60_000,
};

export function useCategoryList() {
  return useQuery(categoriesQuery);
}

export function useCategories() {
  return useQuery({ ...categoriesQuery, select: (r: CategoryList) => r.items });
}

export const patchCategory = (id: string, body: CategoryPatch) => patch<CategoryDto>(`/api/categories/${id}`, body);

export const previewTemplate = (body: { pathTemplate: string; fileTemplate: string; entityId?: string }, signal?: AbortSignal) =>
  request<TemplatePreview>('POST', '/api/templates/preview', { json: body, signal });

export const DEFAULT_THRESHOLDS: SettingsThresholds = { confidenceHigh: 85, confidenceLow: 60, badgeHours: 24 };

export function useThresholds(): SettingsThresholds {
  const s = useSettings().data;
  return s?.confidenceHigh !== undefined && s.confidenceLow !== undefined && s.badgeHours !== undefined
    ? { confidenceHigh: s.confidenceHigh, confidenceLow: s.confidenceLow, badgeHours: s.badgeHours }
    : DEFAULT_THRESHOLDS;
}
