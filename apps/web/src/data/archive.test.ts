import { describe, expect, it } from 'vitest';
import { ARCHIVE_PAGE_SIZE, archiveSearchParams, filtersToQuery, folderHref, parseArchiveSearch, splatToPath } from './archive';

describe('facets to the C2 §4.1 query', () => {
  it('maps every facet to its parameter', () => {
    expect(
      filtersToQuery({ q: ' URSSAF ', entityId: 'ent_a', year: 2026, categoryId: 'tax', counterpartyId: 'cpt_a', amountMin: 1000, amountMax: 5000, statuses: ['filed', 'review'], sort: 'amount_desc', page: 3 }),
    ).toEqual({
      q: 'URSSAF',
      entityId: 'ent_a',
      categoryId: 'tax',
      counterpartyId: 'cpt_a',
      year: 2026,
      amountMin: 1000,
      amountMax: 5000,
      status: ['filed', 'review'],
      sort: 'amount_desc',
      offset: 2 * ARCHIVE_PAGE_SIZE,
      limit: ARCHIVE_PAGE_SIZE,
    });
  });

  it('sends nothing for a bare search: default statuses, default sort, first page', () => {
    expect(filtersToQuery({})).toEqual({ offset: 0, limit: ARCHIVE_PAGE_SIZE });
    expect(filtersToQuery({ statuses: ['filed', 'review', 'unreadable'] })).toMatchObject({ status: undefined });
    expect(filtersToQuery({ statuses: [] })).toMatchObject({ status: undefined });
  });

  it('lets the shell scope win over the entity facet', () => {
    expect(filtersToQuery({ entityId: 'ent_a' }, 'ent_b')).toMatchObject({ entityId: 'ent_b' });
    expect(filtersToQuery({ entityId: 'ent_a' }, undefined)).toMatchObject({ entityId: 'ent_a' });
  });

  it('asks for relevance only when there is a search text', () => {
    expect(filtersToQuery({ sort: 'relevance' })).toMatchObject({ sort: undefined });
    expect(filtersToQuery({ sort: 'relevance', q: 'x' })).toMatchObject({ sort: 'relevance' });
  });

  it('truncates the search text to the 200 characters the API takes', () => {
    expect((filtersToQuery({ q: 'x'.repeat(300) }).q as string).length).toBe(200);
  });
});

describe('the archive route search', () => {
  it('parses what the router hands over, coercing numbers and dropping the malformed', () => {
    expect(parseArchiveSearch({ q: 'URSSAF', year: '2026', amountMin: 1000, statuses: 'filed', sort: 'date_asc', page: '2', junk: 1 })).toEqual({
      q: 'URSSAF',
      year: 2026,
      amountMin: 1000,
      statuses: ['filed'],
      sort: 'date_asc',
      page: 2,
    });
    expect(parseArchiveSearch({ year: 'soon', amountMin: -5, statuses: ['bogus'], sort: 'random', page: 0, entityId: 'a b' })).toEqual({});
  });

  it('keeps all three statuses and page 1 out of the URL', () => {
    expect(archiveSearchParams({ statuses: ['filed', 'review', 'unreadable'], page: 1, q: 'x' })).toEqual({ q: 'x' });
    expect(archiveSearchParams({ statuses: ['review', 'filed'] })).toEqual({ statuses: ['filed', 'review'] });
  });
});

describe('folder paths', () => {
  it('encodes each segment and reads the splat back', () => {
    expect(folderHref(['Cabinet Marchand', 'Impôts'])).toBe('/archive/folders/Cabinet%20Marchand/Imp%C3%B4ts');
    expect(folderHref([])).toBe('/archive/folders');
    expect(splatToPath('Cabinet%20Marchand/Imp%C3%B4ts/')).toEqual(['Cabinet Marchand', 'Impôts']);
    expect(splatToPath('Cabinet Marchand/Impôts')).toEqual(['Cabinet Marchand', 'Impôts']);
    expect(splatToPath(undefined)).toEqual([]);
    expect(splatToPath('%E0%A4%A')).toEqual(['%E0%A4%A']);
  });
});
