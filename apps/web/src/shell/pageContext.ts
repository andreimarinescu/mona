import type { PageContext } from '../chat/types';

export interface RouteLocation {
  pathname: string;
  search?: string;
  hash?: string;
  scope?: string;
}

const ID = /^[A-Za-z0-9_-]{1,64}$/;

function id(segment: string | undefined): string | null {
  return segment && ID.test(segment) ? segment : null;
}

function withId(label: string, noun: string, value: string | undefined): string {
  const v = id(value);
  return v ? `${label}, ${noun} ${v}` : label;
}

function describe(pathname: string, search: string, hash: string): { summary: string; scoped: boolean } {
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
    case 'archive':
      return { summary: a === 'folders' ? `Archive, folder view, depth ${seg.length - 2}` : 'Archive', scoped: true };
    case 'documents': {
      const page = /(?:^|[?&])page=(\d{1,4})(?:&|$)/.exec(search)?.[1];
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

/** The C3 `pageContext` for a route: English, ids and counts only, never document text. */
export function pageContext({ pathname, search = '', hash = '', scope = 'all' }: RouteLocation): PageContext {
  const { summary, scoped } = describe(pathname, search, hash);
  const scopedSummary = scoped && id(scope) && scope !== 'all' ? `${summary}, filtered to entity ${scope}` : summary;
  return { route: (pathname + search).slice(0, 200), summary: scopedSummary.slice(0, 300) };
}
