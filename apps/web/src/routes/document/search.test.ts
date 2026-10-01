import { describe, expect, it } from 'vitest';
import type { ExtractedField } from '../../data/dto';
import { clampPage, formatFieldValue, parseDocumentSearch, showOnPage } from './search';

const field = (over: Partial<ExtractedField['evidence']> = {}, value = '1284.00'): ExtractedField => ({
  key: 'amount',
  value,
  money: { value: 1284, currency: 'EUR' },
  confidence: 98,
  evidence: { documentId: 'doc_a', documentTitle: 'Call', field: 'amount', page: 2, quote: 'Montant à payer 1 284,00 €', verified: true, findQuery: '1 284,00', ...over },
});

describe('the viewer deep link', () => {
  it('reads page, q and field', () => {
    expect(parseDocumentSearch({ page: 2, q: '1 284,00', field: 'amount' })).toEqual({ page: 2, q: '1 284,00', field: 'amount' });
  });

  it('accepts numeric strings and numbers where the router parsed a query as a number', () => {
    expect(parseDocumentSearch({ page: '3', q: 2026 })).toEqual({ page: 3, q: '2026' });
  });

  it('drops a bad page, an empty q and an unknown field', () => {
    expect(parseDocumentSearch({ page: 0, q: '  ', field: 'iban' })).toEqual({});
    expect(parseDocumentSearch({ page: -1 })).toEqual({});
    expect(parseDocumentSearch({ page: 1.5 })).toEqual({});
    expect(parseDocumentSearch({ page: 'x' })).toEqual({});
  });

  it('caps q at 200 characters', () => {
    expect(parseDocumentSearch({ q: 'x'.repeat(500) }).q).toHaveLength(200);
  });

  it('opens page 1 by default and clamps to the page count', () => {
    expect(clampPage(undefined, 3)).toBe(1);
    expect(clampPage(9, 3)).toBe(3);
    expect(clampPage(2, 3)).toBe(2);
    expect(clampPage(5, null)).toBe(5);
  });
});

describe('Show on page', () => {
  it('sends the findQuery, not the raw quote, with the evidence page', () => {
    const sent = showOnPage(field());
    expect(sent).toEqual({ query: '1 284,00', page: 2 });
    expect(sent.query).not.toBe('Montant à payer 1 284,00 €');
  });

  it('falls back to the value when there is no findQuery', () => {
    expect(showOnPage(field({ findQuery: null, verified: false }, 'Cabinet dentaire Exemple'))).toEqual({ query: 'Cabinet dentaire Exemple', page: 2 });
  });
});

describe('field values', () => {
  it('formats money and calendar dates in the interface language', () => {
    expect(formatFieldValue(field(), 'en')).toBe('€1,284.00');
    expect(formatFieldValue(field(), 'fr')).toBe('1 284,00 €');
    expect(formatFieldValue({ ...field(), key: 'due_date', money: undefined, value: '2026-10-02' }, 'en')).toBe('2 October 2026');
  });
});
