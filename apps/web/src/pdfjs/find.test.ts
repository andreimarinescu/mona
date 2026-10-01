import { describe, expect, it, vi } from 'vitest';
import { configureViewerPreferences, dispatchFind, findHash, labelViewerControls, viewerUrl } from './find';

describe('pdf.js find', () => {
  it('builds a phrase-search hash', () => {
    expect(findHash('1 284,00 €')).toBe('#page=1&search=1%20284%2C00%20%E2%82%AC&phrase=true');
  });

  it('dispatches a string query (phrase) once the viewer is initialised', async () => {
    const dispatch = vi.fn();
    await dispatchFind({ initializedPromise: Promise.resolve(), eventBus: { dispatch } }, '1 284,00');
    expect(dispatch).toHaveBeenCalledWith('find', expect.objectContaining({ query: '1 284,00', highlightAll: false }));
  });
});

describe('viewer url and evidence page', () => {
  it('points the viewer at the sample or at a given file', () => {
    expect(viewerUrl()).toBe('/pdfjs/web/viewer.html?file=%2Fdev%2Fsample.pdf');
    expect(viewerUrl('/dev/fixture/0.pdf')).toBe('/pdfjs/web/viewer.html?file=%2Fdev%2Ffixture%2F0.pdf');
  });

  it('opens the evidence page before the find', async () => {
    const order: string[] = [];
    const app = {
      initializedPromise: Promise.resolve(),
      eventBus: { dispatch: () => order.push('find') },
      set page(n: number) {
        order.push(`page ${n}`);
      },
    };
    await dispatchFind(app, 'x', 2);
    expect(order).toEqual(['page 2', 'find']);
  });
});

describe('viewer preferences', () => {
  const memory = (initial?: string) => {
    let value = initial ?? null;
    return { getItem: () => value, setItem: (_: string, v: string) => void (value = v), read: () => value };
  };

  it('turns WebGPU off and keeps the other preferences', () => {
    const storage = memory(JSON.stringify({ sidebarViewOnLoad: 0 }));
    configureViewerPreferences(storage);
    expect(JSON.parse(storage.read()!)).toEqual({ sidebarViewOnLoad: 0, enableWebGPU: false });
  });

  it('starts from nothing, and from storage that is not JSON', () => {
    const empty = memory();
    configureViewerPreferences(empty);
    expect(JSON.parse(empty.read()!)).toEqual({ enableWebGPU: false });
    const broken = memory('{nope');
    configureViewerPreferences(broken);
    expect(JSON.parse(broken.read()!)).toEqual({ enableWebGPU: false });
  });
});

describe('viewer url with a page', () => {
  it('opens a later page through the hash and page 1 without one', () => {
    expect(viewerUrl('/api/documents/doc_a/pdf', 3)).toBe('/pdfjs/web/viewer.html?file=%2Fapi%2Fdocuments%2Fdoc_a%2Fpdf#page=3');
    expect(viewerUrl('/api/documents/doc_a/pdf', 1)).toBe('/pdfjs/web/viewer.html?file=%2Fapi%2Fdocuments%2Fdoc_a%2Fpdf');
  });
});

describe('viewer control labels', () => {
  it('copies the title of the page and zoom controls to aria-label, now and when the viewer localises it', async () => {
    document.body.innerHTML = '<input id="pageNumber" title="Page"><select id="scaleSelect"></select><input id="other" title="x">';
    const stop = labelViewerControls(document);
    expect(document.getElementById('pageNumber')?.getAttribute('aria-label')).toBe('Page');
    expect(document.getElementById('scaleSelect')?.hasAttribute('aria-label')).toBe(false);
    document.getElementById('scaleSelect')!.setAttribute('title', 'Zoom');
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(document.getElementById('scaleSelect')?.getAttribute('aria-label')).toBe('Zoom');
    expect(document.getElementById('other')?.hasAttribute('aria-label')).toBe(false);
    stop();
  });
});
