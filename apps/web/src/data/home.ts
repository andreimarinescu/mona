import { useQuery } from '@tanstack/react-query';
import type { HomeView } from './dto';
import { get } from './http';
import { pollStopsOn } from './polling';

export const HOME_POLL_MS = 30_000;

export function useHome(entityId: string | undefined) {
  return useQuery({
    queryKey: ['home', entityId ?? 'all'],
    queryFn: ({ signal }) => get<HomeView>('/api/home', { entityId }, signal),
    refetchInterval: (query) => (pollStopsOn(query.state.error) ? false : HOME_POLL_MS),
  });
}
