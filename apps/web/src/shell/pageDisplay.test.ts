import { describe, expect, it } from 'vitest';
import { pageContext } from './pageContext';
import { pageDisplay } from './pageDisplay';

describe('the archive page facts in the C3 summary', () => {
  it('names the search and the result count, in English', () => {
    expect(pageContext({ pathname: '/archive', facts: { archive: { query: 'URSSAF', results: 14 } } }).summary).toBe("Archive, search 'URSSAF', 14 results");
    expect(pageContext({ pathname: '/archive', facts: { archive: { query: null, results: 1 } } }).summary).toBe('Archive, 1 result');
    expect(pageContext({ pathname: '/archive', facts: null }).summary).toBe('Archive');
  });

  it('strips quotes and line breaks from the term and caps it', () => {
    const summary = pageContext({ pathname: '/archive', facts: { archive: { query: `it's\n"x" ${'y'.repeat(100)}`, results: 0 } } }).summary;
    expect(summary).toMatch(/^Archive, search 'it s x y{53}', 0 results$/);
    expect(summary.length).toBeLessThanOrEqual(300);
  });

  it('ignores the facts on other routes and on the folder view', () => {
    const facts = { archive: { query: 'x', results: 3 } };
    expect(pageContext({ pathname: '/review', facts }).summary).toBe('Review queue');
    expect(pageContext({ pathname: '/archive/folders/a/b', facts }).summary).toBe('Archive, folder view, depth 2');
  });
});

describe('the localised display string', () => {
  it('gives an i18n key and its values per route', () => {
    expect(pageDisplay({ pathname: '/' })).toEqual({ key: 'shell.seen.home', values: {} });
    expect(pageDisplay({ pathname: '/archive', facts: { archive: { query: 'URSSAF', results: 14 } } })).toEqual({ key: 'shell.seen.archiveSearch', values: { count: 14, q: 'URSSAF' } });
    expect(pageDisplay({ pathname: '/archive', facts: { archive: { query: null, results: 2 } } })).toEqual({ key: 'shell.seen.archiveResults', values: { count: 2 } });
    expect(pageDisplay({ pathname: '/archive/folders/a/b/c' })).toEqual({ key: 'shell.seen.archiveFolder', values: { count: 3 } });
    expect(pageDisplay({ pathname: '/documents/doc_a', search: '?page=2' })).toEqual({ key: 'shell.seen.documentPage', values: { page: 2 } });
    expect(pageDisplay({ pathname: '/reports' }).key).toBe('shell.seen.unknown');
  });

  it('never carries an id', () => {
    const shown = JSON.stringify(pageDisplay({ pathname: '/documents/doc_01j9zq3k8e6y4v2m7c5r1t0b9a', search: '?page=2' }));
    expect(shown).not.toContain('doc_');
  });
});
