import { useQuery } from '@tanstack/react-query';
import type { CategoryDto, EntityList, SettingsThresholds } from './dto';
import { get } from './http';

export function useEntityList() {
  return useQuery({ queryKey: ['entities-list'], queryFn: ({ signal }) => get<EntityList>('/api/entities', undefined, signal), staleTime: 60_000 });
}

export function useCategories() {
  return useQuery({
    queryKey: ['categories'],
    queryFn: ({ signal }) => get<{ items: CategoryDto[] }>('/api/categories', undefined, signal).then((r) => r.items),
    staleTime: 60_000,
  });
}

export const DEFAULT_THRESHOLDS: SettingsThresholds = { confidenceHigh: 85, confidenceLow: 60, badgeHours: 24 };

export function useThresholds(): SettingsThresholds {
  const q = useQuery({
    queryKey: ['settings-view'],
    queryFn: ({ signal }) => get<SettingsThresholds>('/api/settings', undefined, signal),
    staleTime: 60_000,
  });
  return q.data ? { confidenceHigh: q.data.confidenceHigh, confidenceLow: q.data.confidenceLow, badgeHours: q.data.badgeHours } : DEFAULT_THRESHOLDS;
}
