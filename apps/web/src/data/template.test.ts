import { describe, expect, it } from 'vitest';
import { TOKEN_CHIPS, parseTemplate } from './template';

describe('parseTemplate (C5 §8.1)', () => {
  it('splits literals and tokens, and reads the date format', () => {
    const { parts, error } = parseTemplate('{entity}/{fy} {entity}/Documents annuels', 'path');
    expect(error).toBeNull();
    expect(parts.map((p) => (p.kind === 'token' ? p.name : p.text))).toEqual(['entity', '/', 'fy', ' ', 'entity', '/Documents annuels']);
    const file = parseTemplate('{date:YYYY-MM-DD}_{issuer}_Appel_{reference}', 'file');
    expect(file.error).toBeNull();
    expect(file.parts[0]).toMatchObject({ kind: 'token', name: 'date', format: 'YYYY-MM-DD' });
  });

  it('accepts every token chip it offers', () => {
    for (const chip of TOKEN_CHIPS) expect([parseTemplate(`{date:YYYY}_${chip}`, 'file').error, parseTemplate(`${chip}/x`, 'path').error]).toEqual([null, null]);
  });

  it.each([
    ['{bogus}/x', 'path', 1, 'unknown_token'],
    ['{entity:YYYY}/x', 'path', 7, 'format_on_token'],
    ['{date:YYYYQ}_x', 'file', 6, 'bad_format'],
    ['{entity/x', 'path', 0, 'stray_brace'],
    ['a}b', 'path', 1, 'stray_brace'],
    ['', 'path', 0, 'empty'],
    ['{entity}//x', 'path', 9, 'empty_segment'],
    ['{entity}/..', 'path', 9, 'bad_segment'],
    ['{date:YYYY}/{counterparty}', 'file', 11, 'slash'],
    ['{counterparty}_{date:YYYY}', 'file', 0, 'date_first'],
  ] as const)('rejects %s with its offset', (text, kind, offset, reason) => {
    expect(parseTemplate(text, kind).error).toEqual({ offset, reason });
  });
});
