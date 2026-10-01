import type { TemplatePreview } from '../data/dto';
import { parseTemplate, type TemplateError, type TemplatePart } from '../data/template';

export interface SampleValues {
  entity: string;
  fyEnd: string;
  category: string;
  sub: string;
  counterparty: string;
  issuer: string | null;
  reference: string;
  docDate: string;
  periodEnd: string;
}

export const MESSAGES: Record<TemplateError['reason'], string> = {
  unknown_token: 'Unknown token.',
  format_on_token: 'Only {date} takes a format.',
  bad_format: 'The date format uses YYYY, YY, MM, DD and - _ . only.',
  stray_brace: 'A brace has no partner.',
  empty: 'The template is empty.',
  empty_segment: 'A folder name is empty.',
  bad_segment: 'A folder can’t be . or ..',
  slash: 'A file name has no /.',
  date_first: 'The file name starts with a {date} token.',
};

function fiscalYear(date: string, fyEnd: string): number {
  const year = Number(date.slice(0, 4));
  return date.slice(5) <= fyEnd ? year : year + 1;
}

function dateText(date: string, format: string): string {
  const [y = '', m = '', d = ''] = date.split('-');
  return format.replace(/YYYY|YY|MM|DD/g, (u) => (u === 'YYYY' ? y : u === 'YY' ? y.slice(2) : u === 'MM' ? m : d));
}

function value(part: Extract<TemplatePart, { kind: 'token' }>, v: SampleValues): string {
  switch (part.name) {
    case 'entity':
      return v.entity;
    case 'year':
      return v.docDate.slice(0, 4);
    case 'fy':
      return String(fiscalYear(v.periodEnd, v.fyEnd));
    case 'category':
      return v.category;
    case 'sub':
      return v.sub;
    case 'counterparty':
      return v.counterparty;
    case 'issuer':
      return v.issuer ?? v.counterparty;
    case 'reference':
      return v.reference;
    case 'date':
      return dateText(v.docDate, part.format ?? 'YYYY-MM-DD');
  }
}

const slug = (s: string) =>
  s
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^A-Za-z0-9.]+/g, '-')
    .replace(/^[-.]+|[-.]+$/g, '');

function segment(raw: string): string {
  return raw
    .normalize('NFC')
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\p{Cc}/gu, '-')
    .replace(/\s+/g, ' ')
    .replace(/^[ .]+|[ .]+$/g, '');
}

/** The C5 §8 renderer in miniature, enough for the editor's live preview against fixed sample values. */
export function renderTemplates(pathTemplate: string, fileTemplate: string, sample: SampleValues): TemplatePreview {
  const path = parseTemplate(pathTemplate, 'path');
  if (path.error) return { path: [], fileName: null, error: { template: 'path', offset: path.error.offset, message: MESSAGES[path.error.reason] } };
  const file = parseTemplate(fileTemplate, 'file');
  if (file.error) return { path: [], fileName: null, error: { template: 'file', offset: file.error.offset, message: MESSAGES[file.error.reason] } };
  const folders = path.parts
    .map((p) => (p.kind === 'literal' ? p.text : value(p, sample)))
    .join('')
    .split('/')
    .map(segment)
    .filter(Boolean);
  const stem = file.parts
    .map((p) => (p.kind === 'literal' ? p.text.replace(/[^A-Za-z0-9._-]/g, '-') : slug(value(p, sample))))
    .join('')
    .replace(/[_-]*_[_-]*/g, '_')
    .replace(/-{2,}/g, '-')
    .replace(/^[_.-]+|[_.-]+$/g, '');
  return { path: folders, fileName: `${stem}.pdf`, error: null };
}
