import { summaryTerm, type PageFacts } from './pageContext';

export interface PageDisplay {
  key: string;
  values: Record<string, string | number>;
}

export interface DisplayLocation {
  pathname: string;
  search?: string;
  facts?: PageFacts | null;
}

/** The interface-language counterpart of the English C3 summary: an i18n key and its values, for the "Mona can see" line. */
export function pageDisplay({ pathname, search = '', facts = null }: DisplayLocation): PageDisplay {
  const [head, a, b] = pathname.split('/').filter(Boolean);
  const none = (key: string): PageDisplay => ({ key: `shell.seen.${key}`, values: {} });
  switch (head) {
    case undefined:
      return none('home');
    case 'chat':
      return none('chat');
    case 'intake':
      return none('intake');
    case 'review':
      return none(a ? 'reviewDocument' : 'review');
    case 'archive': {
      if (a === 'folders') return { key: 'shell.seen.archiveFolder', values: { count: Math.max(pathname.split('/').filter(Boolean).length - 2, 0) } };
      const found = a === undefined ? facts?.archive : undefined;
      if (!found) return none('archive');
      const term = found.query ? summaryTerm(found.query) : '';
      return term ? { key: 'shell.seen.archiveSearch', values: { count: found.results, q: term } } : { key: 'shell.seen.archiveResults', values: { count: found.results } };
    }
    case 'documents': {
      const page = /(?:^|[?&])page=(\d{1,4})(?:&|$)/.exec(search)?.[1];
      return page ? { key: 'shell.seen.documentPage', values: { page: Number(page) } } : none('document');
    }
    case 'rules':
      return none(a ? 'rule' : 'rules');
    case 'entities':
      return none(a === 'categories' && b ? 'category' : 'entities');
    case 'activity':
      return none('activity');
    case 'settings':
      return none('settings');
    case 'unlock':
      return none('unlock');
    case 'dev':
      return none('dev');
    default:
      return none('unknown');
  }
}
