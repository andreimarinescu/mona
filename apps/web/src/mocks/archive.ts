import type { ArchiveStatus, CategoryDto, DocumentFacets, DocumentPage, DocumentSort, DocumentSummary, FolderListing, FolderNode } from '../data/dto';

export function norm(s: string): string {
  return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase();
}

export interface SearchParams {
  q?: string;
  entityId?: string;
  categoryId?: string;
  counterpartyId?: string;
  year?: number;
  amountMin?: number;
  amountMax?: number;
  status: ArchiveStatus[];
  sort?: DocumentSort;
  offset: number;
  limit: number;
}

const STATUSES: ArchiveStatus[] = ['filed', 'review', 'unreadable'];

export function parseSearchParams(q: URLSearchParams): SearchParams {
  const num = (k: string) => (q.get(k) === null || q.get(k) === '' ? undefined : Number(q.get(k)));
  const status = q.getAll('status').filter((s): s is ArchiveStatus => STATUSES.includes(s as ArchiveStatus));
  return {
    q: q.get('q') ?? undefined,
    entityId: q.get('entityId') ?? undefined,
    categoryId: q.get('categoryId') ?? undefined,
    counterpartyId: q.get('counterpartyId') ?? undefined,
    year: num('year'),
    amountMin: num('amountMin'),
    amountMax: num('amountMax'),
    status: status.length > 0 ? status : STATUSES,
    sort: (q.get('sort') as DocumentSort | null) ?? undefined,
    offset: num('offset') ?? 0,
    limit: num('limit') ?? 50,
  };
}

type Facet = 'entity' | 'year' | 'category' | 'counterparty' | 'status' | 'amount';

const year = (d: DocumentSummary) => (d.date ? Number(d.date.slice(0, 4)) : null);

function matches(d: DocumentSummary, p: SearchParams, skip?: Facet): boolean {
  if (d.status === 'processing') return false;
  if (p.q) {
    const hay = norm(`${d.title} ${d.fileName} ${d.counterparty ?? ''} ${d.reference ?? ''}`);
    if (!norm(p.q).split(/\s+/).filter(Boolean).every((w) => hay.includes(w))) return false;
  }
  if (skip !== 'entity' && p.entityId && d.entityId !== p.entityId) return false;
  if (skip !== 'category' && p.categoryId && d.categoryId !== p.categoryId) return false;
  if (skip !== 'counterparty' && p.counterpartyId && d.counterpartyId !== p.counterpartyId) return false;
  if (skip !== 'year' && p.year !== undefined && year(d) !== p.year) return false;
  if (skip !== 'status' && !p.status.includes(d.status as ArchiveStatus)) return false;
  if (skip !== 'amount') {
    const v = d.amount?.value;
    if (p.amountMin !== undefined && (v === undefined || v < p.amountMin)) return false;
    if (p.amountMax !== undefined && (v === undefined || v > p.amountMax)) return false;
  }
  return true;
}

function tally<K extends string | number>(docs: DocumentSummary[], key: (d: DocumentSummary) => K | null): Map<K, number> {
  const out = new Map<K, number>();
  for (const d of docs) {
    const k = key(d);
    if (k !== null) out.set(k, (out.get(k) ?? 0) + 1);
  }
  return out;
}

export function searchDocuments(all: DocumentSummary[], p: SearchParams, categories: CategoryDto[], entityNames: Map<string, string>): DocumentPage {
  const hits = all.filter((d) => matches(d, p));
  const sort: DocumentSort = p.sort ?? (p.q ? 'relevance' : 'date_desc');
  const byDate = (d: DocumentSummary) => d.date ?? '';
  hits.sort((a, b) => {
    if (sort === 'date_asc') return byDate(a) < byDate(b) ? -1 : 1;
    if (sort === 'arrived_desc') return a.arrivedAt < b.arrivedAt ? 1 : -1;
    if (sort === 'amount_desc') return (b.amount?.value ?? -Infinity) - (a.amount?.value ?? -Infinity);
    return byDate(a) < byDate(b) ? 1 : byDate(a) > byDate(b) ? -1 : a.id < b.id ? -1 : 1;
  });
  const among = (skip: Facet) => all.filter((d) => matches(d, p, skip));
  const cpNames = new Map(all.filter((d) => d.counterpartyId && d.counterparty).map((d) => [d.counterpartyId!, d.counterparty!]));
  const amounts = among('amount').flatMap((d) => (d.amount ? [d.amount.value] : []));
  const facets: DocumentFacets = {
    entities: [...tally(among('entity'), (d) => d.entityId)].map(([id, count]) => ({ id, name: entityNames.get(id) ?? id, count })).sort((a, b) => b.count - a.count),
    years: [...tally(among('year'), year)].map(([y, count]) => ({ year: y, count })).sort((a, b) => b.year - a.year),
    categories: [...tally(among('category'), (d) => d.categoryId)].map(([id, count]) => ({ id, label: categories.find((c) => c.id === id)?.labels.en ?? id, count })).sort((a, b) => b.count - a.count),
    counterparties: [...tally(among('counterparty'), (d) => d.counterpartyId)].map(([id, count]) => ({ id, name: cpNames.get(id) ?? id, count })).sort((a, b) => b.count - a.count).slice(0, 20),
    statuses: [...tally(among('status'), (d) => d.status)].map(([status, count]) => ({ status, count })),
    amount: { min: amounts.length ? Math.min(...amounts) : null, max: amounts.length ? Math.max(...amounts) : null },
  };
  return { items: hits.slice(p.offset, p.offset + p.limit), total: hits.length, offset: p.offset, limit: p.limit, facets };
}

export function listFolder(all: DocumentSummary[], path: string[], entityId?: string): FolderListing {
  const inArchive = all.filter((d) => d.location === 'archive' && (!entityId || d.entityId === entityId));
  const under = inArchive.filter((d) => path.every((seg, i) => d.path[i] === seg));
  const children = new Map<string, FolderNode>();
  for (const d of under) {
    const name = d.path[path.length];
    if (name === undefined) continue;
    const node = children.get(name) ?? { name, path: [...path, name], documentCount: 0, hasChildren: false };
    node.documentCount += 1;
    if (d.path.length > path.length + 1) node.hasChildren = true;
    children.set(name, node);
  }
  return {
    path,
    folders: [...children.values()].sort((a, b) => a.name.localeCompare(b.name, 'fr')),
    documents: under.filter((d) => d.path.length === path.length).sort((a, b) => (a.fileName < b.fileName ? -1 : 1)),
  };
}
