import type { TemplatePreview } from '../data/dto';
import { parseTemplate, type TemplateError, type TemplatePart } from '../data/template';

export interface SampleValues {
  lang: 'en' | 'fr' | 'ro';
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
  bad_format: 'The date format uses YYYY, YY, MMMM, MM, DD and - _ . only.',
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

const MONTHS: Record<SampleValues['lang'], string[]> = {
  en: ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'],
  fr: ['Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin', 'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'],
  ro: ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie', 'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie'],
};

function dateText(date: string, format: string, lang: SampleValues['lang']): string {
  const [y = '', m = '', d = ''] = date.split('-');
  const units: Record<string, string> = { YYYY: y, YY: y.slice(2), MMMM: MONTHS[lang][Number(m) - 1] ?? '', MM: m, DD: d };
  return format.replace(/YYYY|YY|MMMM|MM|DD/g, (u) => units[u]!);
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
      return dateText(v.docDate, part.format ?? 'YYYY-MM-DD', v.lang);
  }
}

const fold = (s: string) => s.normalize('NFKD').replace(/\p{M}/gu, '');

const slug = (s: string) =>
  fold(s)
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
    .map((p) => (p.kind === 'literal' ? fold(p.text).replace(/[^A-Za-z0-9._-]/g, '-') : slug(value(p, sample))))
    .join('')
    .replace(/[_-]*_[_-]*/g, '_')
    .replace(/-{2,}/g, '-')
    .replace(/^[_.-]+|[_.-]+$/g, '');
  return { path: folders, fileName: `${stem}.pdf`, error: null };
}
