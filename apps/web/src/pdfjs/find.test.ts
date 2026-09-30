import { describe, expect, it, vi } from 'vitest';
import { dispatchFind, findHash } from './find';

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
