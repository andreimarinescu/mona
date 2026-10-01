import { useQuery } from '@tanstack/react-query';
import { useRef } from 'react';
import type { ExportPack, ExportPreview } from './dto';
import { get, post, retryTransient } from './http';
import { jobRefetchInterval } from './polling';

export function useExportPreview(entityId: string | undefined, fiscalYear: number | undefined) {
  return useQuery({
    queryKey: ['export-preview', entityId, fiscalYear],
    enabled: !!entityId && fiscalYear !== undefined,
    retry: retryTransient,
    queryFn: ({ signal }) => get<ExportPreview>('/api/exports/preview', { entityId, fiscalYear }, signal),
  });
}

export const startExport = (entityId: string, fiscalYear: number) => post<ExportPack>('/api/exports', { entityId, fiscalYear });

export function useExportPack(id: string | undefined) {
  const since = useRef<{ id: string | undefined; at: number }>({ id, at: 0 });
  return useQuery({
    queryKey: ['export', id],
    enabled: !!id,
    queryFn: ({ signal }) => {
      if (since.current.id !== id || since.current.at === 0) since.current = { id, at: Date.now() };
      return get<ExportPack>(`/api/exports/${id}`, undefined, signal);
    },
    refetchInterval: (query) => jobRefetchInterval(query.state.data?.status, 'building', query.state.error, Date.now() - (since.current.at || Date.now())),
  });
}
