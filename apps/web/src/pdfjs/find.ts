export const SAMPLE_PHRASE = '1 284,00 €';

export interface PdfViewerApp {
  initializedPromise: Promise<void>;
  eventBus: { dispatch(name: string, data: Record<string, unknown>): void };
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

export async function dispatchFind(app: PdfViewerApp, query: string): Promise<void> {
  await app.initializedPromise;
  app.eventBus.dispatch('find', findEvent(query));
}
