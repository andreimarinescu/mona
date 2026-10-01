export const SAMPLE_PHRASE = '1 284,00 €';
export const SAMPLE_PDF = '/dev/sample.pdf';

export interface PdfViewerApp {
  initializedPromise: Promise<void>;
  eventBus: {
    dispatch(name: string, data: Record<string, unknown>): void;
    on?(name: string, listener: () => void, options?: { once?: boolean }): void;
  };
  pdfViewer?: { pagesCount: number };
  page?: number;
}

export function viewerUrl(file: string = SAMPLE_PDF, page?: number): string {
  return `/pdfjs/web/viewer.html?file=${encodeURIComponent(file)}${page && page > 1 ? `#page=${page}` : ''}`;
}

/** Resolves once the viewer has a document: a find sent earlier is dropped when the document is set. */
export async function whenDocumentLoaded(app: PdfViewerApp): Promise<void> {
  await app.initializedPromise;
  if (!app.pdfViewer || app.pdfViewer.pagesCount > 0 || !app.eventBus.on) return;
  await new Promise<void>((resolve) => app.eventBus.on?.('documentloaded', () => resolve(), { once: true }));
}

export function findHash(query: string, page = 1): string {
  return `#page=${page}&search=${encodeURIComponent(query)}&phrase=true`;
}

export function findEvent(query: string) {
  return {
    source: null,
    type: '',
    query,
    caseSensitive: false,
    entireWord: false,
    highlightAll: false,
    findPrevious: false,
    matchDiacritics: false,
  };
}

/** C5 §7: open the evidence page, then send the findQuery to pdf.js find. */
export async function dispatchFind(app: PdfViewerApp, query: string, page?: number): Promise<void> {
  await whenDocumentLoaded(app);
  if (page !== undefined) app.page = page;
  app.eventBus.dispatch('find', findEvent(query));
}

export const VIEWER_PREFERENCES_KEY = 'pdfjs.preferences';

/** The viewer reads its preferences from this origin's storage: v1 needs no GPU decoding, and without an adapter Chromium logs a warning. */
export function configureViewerPreferences(storage: Pick<Storage, 'getItem' | 'setItem'> | undefined = globalThis.localStorage): void {
  if (!storage) return;
  let current: Record<string, unknown> = {};
  try {
    const parsed: unknown = JSON.parse(storage.getItem(VIEWER_PREFERENCES_KEY) ?? '{}');
    if (parsed && typeof parsed === 'object') current = parsed as Record<string, unknown>;
  } catch {
    current = {};
  }
  if (current.enableWebGPU === false) return;
  storage.setItem(VIEWER_PREFERENCES_KEY, JSON.stringify({ ...current, enableWebGPU: false }));
}

const UNLABELLED_CONTROLS = ['pageNumber', 'scaleSelect'];

/** The stock toolbar names its page and zoom controls with `title` alone, which assistive technology may skip: copy it to `aria-label`. Returns a stop function. */
export function labelViewerControls(doc: Document): () => void {
  const apply = () => {
    for (const id of UNLABELLED_CONTROLS) {
      const el = doc.getElementById(id);
      const title = el?.getAttribute('title');
      if (el && title && el.getAttribute('aria-label') !== title) el.setAttribute('aria-label', title);
    }
  };
  apply();
  const observer = new MutationObserver(apply);
  observer.observe(doc.documentElement, { subtree: true, attributes: true, attributeFilter: ['title'] });
  return () => observer.disconnect();
}
