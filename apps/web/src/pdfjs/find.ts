export const SAMPLE_PHRASE = '1 284,00 €';
export const SAMPLE_PDF = '/dev/sample.pdf';

export interface PdfViewerApp {
  initializedPromise: Promise<void>;
  eventBus: { dispatch(name: string, data: Record<string, unknown>): void };
  page?: number;
}

export function viewerUrl(file: string = SAMPLE_PDF): string {
  return `/pdfjs/web/viewer.html?file=${encodeURIComponent(file)}`;
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
  await app.initializedPromise;
  if (page !== undefined) app.page = page;
  app.eventBus.dispatch('find', findEvent(query));
}
