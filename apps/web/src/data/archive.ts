import { keepPreviousData, useQuery } from '@tanstack/react-query';
import type { ArchiveStatus, DocumentPage, DocumentSort, FolderListing } from './dto';
import { get, retryTransient, type Query } from './http';

export const ARCHIVE_PAGE_SIZE = 25;
export const ALL_STATUSES: ArchiveStatus[] = ['filed', 'review', 'unreadable'];
const SORTS: DocumentSort[] = ['relevance', 'date_desc', 'date_asc', 'arrived_desc', 'amount_desc'];
const MAX_QUERY_LENGTH = 200;

export interface ArchiveFilters {
  q?: string;
  entityId?: string;
  year?: number;
  categoryId?: string;
  counterpartyId?: string;
  amountMin?: number;
  amountMax?: number;
  statuses?: ArchiveStatus[];
  sort?: DocumentSort;
  page?: number;
}

function text(value: unknown, max = 200): string | undefined {
  const s = typeof value === 'number' ? String(value) : typeof value === 'string' ? value.trim() : '';
  return s ? s.slice(0, max) : undefined;
}

function num(value: unknown): number | undefined {
  const n = typeof value === 'number' ? value : typeof value === 'string' && value.trim() !== '' ? Number(value) : NaN;
  return Number.isFinite(n) ? n : undefined;
}

function id(value: unknown): string | undefined {
  const s = text(value, 64);
  return s && /^[A-Za-z0-9_-]{1,64}$/.test(s) ? s : undefined;
}

/** The route's search params, as the router parsed them, to typed filters. Unknown or malformed values are dropped. */
export function parseArchiveSearch(raw: Record<string, unknown>): ArchiveFilters {
  const out: ArchiveFilters = {};
  const q = text(raw.q, MAX_QUERY_LENGTH);
  if (q) out.q = q;
  const entityId = id(raw.entityId);
  if (entityId) out.entityId = entityId;
  const year = num(raw.year);
  if (year !== undefined && Number.isInteger(year) && year >= 1900 && year <= 2200) out.year = year;
  const categoryId = id(raw.categoryId);
  if (categoryId) out.categoryId = categoryId;
  const counterpartyId = id(raw.counterpartyId);
  if (counterpartyId) out.counterpartyId = counterpartyId;
  const min = num(raw.amountMin);
  if (min !== undefined && min >= 0) out.amountMin = min;
  const max = num(raw.amountMax);
  if (max !== undefined && max >= 0) out.amountMax = max;
  const statuses = (Array.isArray(raw.statuses) ? raw.statuses : raw.statuses === undefined ? [] : [raw.statuses]).filter((s): s is ArchiveStatus => ALL_STATUSES.includes(s as ArchiveStatus));
  if (statuses.length > 0 && statuses.length < ALL_STATUSES.length) out.statuses = ALL_STATUSES.filter((s) => statuses.includes(s));
  if (SORTS.includes(raw.sort as DocumentSort)) out.sort = raw.sort as DocumentSort;
  const page = num(raw.page);
  if (page !== undefined && Number.isInteger(page) && page > 1) out.page = page;
  return out;
}

/** Filters as they go back into the route's search: defaults and empty values left out. */
export function archiveSearchParams(filters: ArchiveFilters): ArchiveFilters {
  return parseArchiveSearch({ ...filters });
}

export function activeFilterCount(filters: ArchiveFilters): number {
  return [filters.entityId, filters.year, filters.categoryId, filters.counterpartyId, filters.amountMin, filters.amountMax, filters.statuses].filter((v) => v !== undefined).length;
}

/** C2 §4.1: the facet selection and the shell's entity scope as `GET /api/documents` query parameters. */
export function filtersToQuery(filters: ArchiveFilters, scopeEntityId?: string): Query {
  const q = filters.q?.trim().slice(0, MAX_QUERY_LENGTH);
  const statuses = filters.statuses && filters.statuses.length > 0 && filters.statuses.length < ALL_STATUSES.length ? filters.statuses : undefined;
  const sort = filters.sort && !(filters.sort === 'relevance' && !q) ? filters.sort : undefined;
  const page = Math.max(1, filters.page ?? 1);
  return {
    q: q || undefined,
    entityId: scopeEntityId ?? filters.entityId,
    categoryId: filters.categoryId,
    counterpartyId: filters.counterpartyId,
    year: filters.year,
    amountMin: filters.amountMin,
    amountMax: filters.amountMax,
    status: statuses,
    sort,
    offset: (page - 1) * ARCHIVE_PAGE_SIZE,
    limit: ARCHIVE_PAGE_SIZE,
  };
}

export function useArchiveSearch(query: Query) {
  return useQuery({
    queryKey: ['archive', query],
    queryFn: ({ signal }) => get<DocumentPage>('/api/documents', query, signal),
    retry: retryTransient,
    placeholderData: keepPreviousData,
  });
}

export function useFolderListing(path: string[], entityId?: string, enabled = true) {
  return useQuery({
    queryKey: ['folders', path.join('/'), entityId ?? null],
    enabled,
    retry: retryTransient,
    queryFn: ({ signal }) => get<FolderListing>('/api/folders', { path: path.join('/'), entityId }, signal),
  });
}

export function folderHref(path: string[]): string {
  return path.length === 0 ? '/archive/folders' : `/archive/folders/${path.map(encodeURIComponent).join('/')}`;
}

export function splatToPath(splat: string | undefined): string[] {
  return (splat ?? '').split('/').filter(Boolean).map((s) => {
    try {
      return decodeURIComponent(s);
    } catch {
      return s;
    }
  });
}
