export const TOKEN_NAMES = ['entity', 'year', 'fy', 'category', 'sub', 'counterparty', 'issuer', 'reference', 'date'] as const;
export type TokenName = (typeof TOKEN_NAMES)[number];

/** The token chips offered next to a field: `{date:…}` carries its default format. */
export const TOKEN_CHIPS = ['{entity}', '{year}', '{fy}', '{category}', '{sub}', '{counterparty}', '{issuer}', '{reference}', '{date:YYYY-MM-DD}'] as const;

export type TemplateKind = 'path' | 'file';

export type TemplatePart = { kind: 'literal'; text: string } | { kind: 'token'; text: string; name: TokenName; format: string | null };

export interface TemplateError {
  offset: number;
  reason: 'unknown_token' | 'format_on_token' | 'bad_format' | 'stray_brace' | 'empty' | 'empty_segment' | 'bad_segment' | 'slash' | 'date_first';
}

const DATE_FORMAT = /^(?:YYYY|YY|MM|DD|[-_.])+$/;

/** C5 §8.1: splits a template into literals and tokens, or names the first error and its character offset. */
export function parseTemplate(text: string, kind: TemplateKind): { parts: TemplatePart[]; error: null } | { parts: TemplatePart[]; error: TemplateError } {
  const parts: TemplatePart[] = [];
  let literal = '';
  let i = 0;
  const flush = () => {
    if (literal) parts.push({ kind: 'literal', text: literal });
    literal = '';
  };
  while (i < text.length) {
    const ch = text[i]!;
    if (ch === '}') return { parts, error: { offset: i, reason: 'stray_brace' } };
    if (ch !== '{') {
      literal += ch;
      i += 1;
      continue;
    }
    const end = text.indexOf('}', i + 1);
    const inner = end < 0 ? null : text.slice(i + 1, end);
    if (inner === null || inner.includes('{')) return { parts, error: { offset: i, reason: 'stray_brace' } };
    const colon = inner.indexOf(':');
    const name = colon < 0 ? inner : inner.slice(0, colon);
    const format = colon < 0 ? null : inner.slice(colon + 1);
    if (!(TOKEN_NAMES as readonly string[]).includes(name)) return { parts, error: { offset: i + 1, reason: 'unknown_token' } };
    if (format !== null && name !== 'date') return { parts, error: { offset: i + 1 + name.length, reason: 'format_on_token' } };
    if (format !== null && !DATE_FORMAT.test(format)) return { parts, error: { offset: i + 2 + name.length, reason: 'bad_format' } };
    flush();
    parts.push({ kind: 'token', text: text.slice(i, end + 1), name: name as TokenName, format });
    i = end + 1;
  }
  flush();
  const error = structure(parts, text, kind);
  return error ? { parts, error } : { parts, error: null };
}

function structure(parts: TemplatePart[], text: string, kind: TemplateKind): TemplateError | null {
  if (text === '') return { offset: 0, reason: 'empty' };
  if (kind === 'file') {
    const slash = text.indexOf('/');
    if (slash >= 0) return { offset: slash, reason: 'slash' };
    const first = parts[0];
    if (!first || first.kind !== 'token' || first.name !== 'date') return { offset: 0, reason: 'date_first' };
    return null;
  }
  if (text.startsWith('/')) return { offset: 0, reason: 'empty_segment' };
  if (text.endsWith('/')) return { offset: text.length - 1, reason: 'empty_segment' };
  const double = text.indexOf('//');
  if (double >= 0) return { offset: double + 1, reason: 'empty_segment' };
  let offset = 0;
  for (const segment of text.split('/')) {
    if (segment === '.' || segment === '..') return { offset, reason: 'bad_segment' };
    offset += segment.length + 1;
  }
  return null;
}
