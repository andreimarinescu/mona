import type { Lang, MonaFormat } from './types';

const NBSP = '\u00a0';

function loc(lang?: Lang): string {
  return lang === 'fr' ? 'fr-FR' : lang === 'ro' ? 'ro-RO' : 'en-GB';
}

function fixSpaces(s: string): string {
  return s.replace(/\u202f/g, NBSP);
}

function toDate(d: Date | string | number): Date {
  return d instanceof Date ? d : new Date(d);
}

export const format: MonaFormat = {
  number(n, lang, opts) {
    return fixSpaces(new Intl.NumberFormat(loc(lang), opts).format(n));
  },
  money(amount, currency, lang) {
    currency = currency || 'EUR';
    const num = format.number(amount, lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (currency === 'RON') return num + NBSP + 'lei';
    if (currency === 'EUR' && lang !== 'en') return num + NBSP + '€';
    return fixSpaces(new Intl.NumberFormat(loc(lang), { style: 'currency', currency }).format(amount));
  },
  percent(v, lang, digits) {
    const n = format.number(v * 100, lang, { maximumFractionDigits: digits || 0 });
    return lang === 'fr' ? n + NBSP + '%' : n + '%';
  },
  date(d, lang, style) {
    const o: Intl.DateTimeFormatOptions =
      style === 'short' ? { day: '2-digit', month: '2-digit', year: 'numeric' }
      : style === 'medium' ? { day: 'numeric', month: 'short', year: 'numeric' }
      : style === 'dayMonth' ? { day: 'numeric', month: 'long' }
      : { day: 'numeric', month: 'long', year: 'numeric' };
    return fixSpaces(new Intl.DateTimeFormat(loc(lang), o).format(toDate(d)));
  },
  time(d, lang) {
    return new Intl.DateTimeFormat(loc(lang), { hour: '2-digit', minute: '2-digit', hour12: false }).format(toDate(d));
  },
  relative(d, lang, now) {
    const date = toDate(d);
    const s = (date.getTime() - (now ?? new Date()).getTime()) / 1000;
    const a = Math.abs(s);
    const rtf = new Intl.RelativeTimeFormat(loc(lang), { numeric: 'auto' });
    if (a < 45) return rtf.format(0, 'second');
    if (a < 2700) return rtf.format(Math.round(s / 60), 'minute');
    if (a < 72000) return rtf.format(Math.round(s / 3600), 'hour');
    if (a < 518400) return rtf.format(Math.round(s / 86400), 'day');
    return format.date(date, lang, 'medium');
  },
  fileSize(bytes, lang) {
    const u = lang === 'fr' ? ['o', 'Ko', 'Mo', 'Go'] : ['B', 'KB', 'MB', 'GB'];
    let i = 0;
    while (bytes >= 1024 && i < u.length - 1) {
      bytes /= 1024;
      i++;
    }
    return format.number(bytes, lang, { maximumFractionDigits: i ? 1 : 0 }) + NBSP + u[i];
  },
};
