import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRef } from 'react';
import type { BatchDetail, IntakeResult, Page, BatchSummary } from './dto';
import { get, request } from './http';
import { batchRefetchInterval } from './polling';

export const MAX_FILES = 50;
export const MAX_FILE_BYTES = 25 * 1024 * 1024;
export const MAX_REQUEST_BYTES = 250 * 1024 * 1024;

export interface UploadPlan {
  send: File[];
  overLimit: File[];
}

/** Keeps what C2 §5.1 would accept whole: at most 50 files, each up to 25 MB, 250 MB together. */
export function planUpload(files: File[]): UploadPlan {
  const send: File[] = [];
  const overLimit: File[] = [];
  let total = 0;
  for (const file of files) {
    if (file.size > MAX_FILE_BYTES || send.length >= MAX_FILES || total + file.size > MAX_REQUEST_BYTES) overLimit.push(file);
    else {
      send.push(file);
      total += file.size;
    }
  }
  return { send, overLimit };
}

export function uploadIntake(files: File[], opts: { visitor: boolean; title?: string }): Promise<IntakeResult> {
  const form = new FormData();
  for (const file of files) form.append('file', file, file.name);
  form.append('visitor', opts.visitor ? 'true' : 'false');
  if (opts.title) form.append('title', opts.title);
  return request<IntakeResult>('POST', '/api/intake', { form });
}

export const batchKey = (id: string | undefined) => ['batch', id] as const;

export function useBatch(id: string | undefined) {
  const since = useRef<{ id: string | undefined; at: number }>({ id, at: 0 });
  return useQuery({
    queryKey: batchKey(id),
    enabled: !!id,
    queryFn: ({ signal }) => {
      if (since.current.id !== id || since.current.at === 0) since.current = { id, at: Date.now() };
      return get<BatchDetail>(`/api/batches/${id}`, undefined, signal);
    },
    refetchInterval: (query) => batchRefetchInterval(query.state.data?.batch, query.state.error, Date.now(), since.current.at || Date.now()),
  });
}

export const RECENT_BATCH_MS = 12 * 3_600_000;

/** The newest batch, when it is still running or finished recently enough to be today's work. */
export function useRecentBatchId() {
  return useQuery({
    queryKey: ['batches', 'latest'],
    queryFn: async ({ signal }) => {
      const latest = (await get<Page<BatchSummary>>('/api/batches', { limit: 1 }, signal)).items[0];
      if (!latest) return null;
      const recent = latest.status === 'running' || (latest.finishedAt !== null && Date.now() - Date.parse(latest.finishedAt) < RECENT_BATCH_MS);
      return recent ? latest.id : null;
    },
  });
}

export function useInvalidateIntake() {
  const qc = useQueryClient();
  return () => Promise.all([qc.invalidateQueries({ queryKey: ['batch'] }), qc.invalidateQueries({ queryKey: ['batches'] })]);
}
