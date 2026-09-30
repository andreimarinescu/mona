import { describe, expect, it, vi } from 'vitest';
import { dispatchFind, findHash, viewerUrl } from './find';

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
