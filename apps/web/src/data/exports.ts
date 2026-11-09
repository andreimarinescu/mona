import { useQuery } from '@tanstack/react-query';
import { useRef } from 'react';
import type { ExportPack, ExportPreview, TableFileFormat, TableView } from './dto';
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

export function useExportPack(id: string | undefined, snapshot?: ExportPack) {
  const since = useRef<{ id: string | undefined; at: number }>({ id, at: 0 });
  return useQuery({
    queryKey: ['export', id],
    enabled: !!id,
    initialData: snapshot,
    queryFn: ({ signal }) => {
      if (since.current.id !== id || since.current.at === 0) since.current = { id, at: Date.now() };
      return get<ExportPack>(`/api/exports/${id}`, undefined, signal);
    },
    refetchInterval: (query) => jobRefetchInterval(query.state.data?.status, 'building', query.state.error, Date.now() - (since.current.at || Date.now())),
  });
}

export const tableKey = (id: string) => ['table', id] as const;

/** A36: the card's snapshot first; `GET /api/exports/{id}/table` on refresh, never polled. */
export function useExportTable(snapshot: TableView) {
  return useQuery({
    queryKey: tableKey(snapshot.id),
    initialData: snapshot,
    staleTime: Infinity,
    retry: retryTransient,
    queryFn: ({ signal }) => get<TableView>(`/api/exports/${snapshot.id}/table`, undefined, signal),
  });
}

export const makeTableFile = (id: string, format: TableFileFormat, conversationId?: string) =>
  post<ExportPack>(`/api/exports/${id}/file`, { format, ...(conversationId ? { conversationId } : {}) });
