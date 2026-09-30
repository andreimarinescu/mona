import { useQuery } from '@tanstack/react-query';
import { useProviders } from './context';

export function useEntities() {
  const p = useProviders();
  return useQuery({ queryKey: ['entities'], queryFn: () => p.entities(), staleTime: Infinity });
}

export function useSettings() {
  const p = useProviders();
  return useQuery({ queryKey: ['settings'], queryFn: () => p.settings(), staleTime: Infinity });
}

export function useShellCounts() {
  const p = useProviders();
  return useQuery({ queryKey: ['shell-counts'], queryFn: () => p.shellCounts() });
}

export function useHealth() {
  const p = useProviders();
  return useQuery({ queryKey: ['health'], queryFn: () => p.health(), refetchInterval: 30_000, retry: false });
}
