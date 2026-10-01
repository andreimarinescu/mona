import type { PageContext } from '../chat/types';

export interface PageFacts {
  archive?: { query: string | null; results: number };
}

export interface RouteLocation {
  pathname: string;
  search?: string;
  hash?: string;
  scope?: string;
  facts?: PageFacts | null;
}

/** A search term as it may appear in the one-line summary: no quotes or line breaks, short. */
export function summaryTerm(query: string): string {
  return query.replace(/['"\u2018\u2019\u201C\u201D\s]+/g, ' ').trim().slice(0, 60);
}

const ID = /^[A-Za-z0-9_-]{1,64}$/;
const PAGE = /(?:^|[?&])page=(\d{1,4})(?:&|$)/;

function id(segment: string | undefined): string | null {
  return segment && ID.test(segment) ? segment : null;
}

function withId(label: string, noun: string, value: string | undefined): string {
  const v = id(value);
  return v ? `${label}, ${noun} ${v}` : label;
}

function describe(pathname: string, search: string, hash: string, facts: PageFacts | null): { summary: string; scoped: boolean } {
  const seg = pathname.split('/').filter(Boolean);
  const [head, a, b] = seg;
  switch (head) {
    case undefined:
      return { summary: 'Home', scoped: true };
    case 'chat':
      return { summary: 'Chat page', scoped: false };
    case 'intake':
      return { summary: 'Intake', scoped: true };
    case 'review':
      return { summary: a ? `Review queue, document ${id(a) ?? 'unknown'}` : 'Review queue', scoped: true };
    case 'archive': {
      if (a === 'folders') return { summary: `Archive, folder view, depth ${seg.length - 2}`, scoped: true };
      const found = a === undefined ? facts?.archive : undefined;
      if (!found) return { summary: 'Archive', scoped: true };
      const term = found.query ? summaryTerm(found.query) : '';
      const count = `${found.results} ${found.results === 1 ? 'result' : 'results'}`;
      return { summary: term ? `Archive, search '${term}', ${count}` : `Archive, ${count}`, scoped: true };
    }
    case 'documents': {
      const page = PAGE.exec(search)?.[1];
      return { summary: `Document ${id(a) ?? 'unknown'}${page ? `, page ${page}` : ''}`, scoped: true };
    }
    case 'rules':
      return { summary: withId('Rules', 'rule', a), scoped: true };
    case 'entities':
      return { summary: a === 'categories' ? withId('Entities and taxonomy', 'category', b) : 'Entities and taxonomy', scoped: true };
    case 'activity':
      return { summary: 'Activity log', scoped: true };
    case 'settings': {
      const section = /^#?([a-z-]{1,30})$/.exec(hash)?.[1];
      return { summary: section ? `Settings, ${section} section` : 'Settings', scoped: false };
    }
    case 'unlock':
      return { summary: 'Unlock screen', scoped: false };
    case 'dev':
      return { summary: 'Developer page', scoped: false };
    default:
      return { summary: 'Unknown page', scoped: false };
  }
}

/** A document route keeps only its page: evidence links carry a quote from the page in `q`. */
function routeOf(pathname: string, search: string): string {
  if (!pathname.startsWith('/documents/')) return pathname + search;
  const page = PAGE.exec(search)?.[1];
  return page ? `${pathname}?page=${page}` : pathname;
}

/** The C3 `pageContext` for a route: English, ids and counts only, never document text. */
export function pageContext({ pathname, search = '', hash = '', scope = 'all', facts = null }: RouteLocation): PageContext {
  const { summary, scoped } = describe(pathname, search, hash, facts);
  const scopedSummary = scoped && id(scope) && scope !== 'all' ? `${summary}, filtered to entity ${scope}` : summary;
  return { route: routeOf(pathname, search).slice(0, 200), summary: scopedSummary.slice(0, 300) };
}
