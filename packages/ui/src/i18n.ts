import type { Category, DocStatus, Lang, ReasonKind } from './types';

export const STATUS: Record<Lang, Record<DocStatus, string>> = {
  en: { filed: 'Filed by Mona', review: 'Needs review', processing: 'Processing', unreadable: 'Unreadable' },
  fr: { filed: 'Classé par Mona', review: 'À vérifier', processing: 'En cours', unreadable: 'Illisible' },
  ro: { filed: 'Arhivat de Mona', review: 'De verificat', processing: 'În lucru', unreadable: 'Ilizibil' },
};

export const CONFIDENCE: Record<Lang, { label: string; high: string; mid: string; low: string }> = {
  en: { label: 'Confidence', high: 'high', mid: 'medium', low: 'low' },
  fr: { label: 'Confiance', high: 'élevée', mid: 'moyenne', low: 'faible' },
  ro: { label: 'Încredere', high: 'ridicată', mid: 'medie', low: 'scăzută' },
};

export const CATEGORY: Record<Lang, Record<Category, string>> = {
  en: { bank: 'Bank', invoice: 'Invoice', tax: 'Tax', insurance: 'Insurance', payroll: 'Payroll', training: 'Training', travel: 'Travel', personal: 'Personal' },
  fr: { bank: 'Banque', invoice: 'Facture', tax: 'Impôts', insurance: 'Assurance', payroll: 'Paie', training: 'Formation', travel: 'Déplacements', personal: 'Personnel' },
  ro: { bank: 'Bancă', invoice: 'Factură', tax: 'Taxe', insurance: 'Asigurare', payroll: 'Salarii', training: 'Formare', travel: 'Deplasări', personal: 'Personal' },
};

export const REASON: Record<Lang, Record<ReasonKind, string>> = {
  en: { low: 'Low confidence', entity: 'Unknown entity', conflict: 'Conflicting rule', unreadable: 'Unreadable' },
  fr: { low: 'Confiance faible', entity: 'Entité inconnue', conflict: 'Règle en conflit', unreadable: 'Illisible' },
  ro: { low: 'Încredere scăzută', entity: 'Entitate necunoscută', conflict: 'Regulă în conflict', unreadable: 'Ilizibil' },
};

export const LANGS: Array<{ id: Lang; short: string; name: string }> = [
  { id: 'en', short: 'EN', name: 'English' },
  { id: 'fr', short: 'FR', name: 'Français' },
  { id: 'ro', short: 'RO', name: 'Română' },
];

export const CLOSE: Record<Lang, string> = { en: 'Close', fr: 'Fermer', ro: 'Închideți' };

export const THEME_LABELS: Record<Lang, { group: string; light: string; dark: string; system: string }> = {
  en: { group: 'Theme', light: 'Light', dark: 'Dark', system: 'Match system' },
  fr: { group: 'Thème', light: 'Clair', dark: 'Sombre', system: 'Selon le système' },
  ro: { group: 'Temă', light: 'Luminoasă', dark: 'Întunecată', system: 'Ca sistemul' },
};

export type UiKey =
  | 'noMatch' | 'clear' | 'remove' | 'loading' | 'prev' | 'next' | 'page' | 'range' | 'crumbs' | 'fullPath'
  | 'drop' | 'choose' | 'selected' | 'optional' | 'search' | 'more';

export const UI: Record<Lang, Record<UiKey, string>> = {
  en: { noMatch: 'No matches', clear: 'Clear', remove: 'Remove', loading: 'Loading', prev: 'Previous page', next: 'Next page', page: 'Page {p} of {n}', range: '{a}–{b} of {n}', crumbs: 'Breadcrumb', fullPath: 'Show full path', drop: 'Drop files here, or', choose: 'choose files', selected: '{n} selected', optional: 'optional', search: 'Search', more: 'more' },
  fr: { noMatch: 'Aucun résultat', clear: 'Effacer', remove: 'Retirer', loading: 'Chargement', prev: 'Page précédente', next: 'Page suivante', page: 'Page {p} sur {n}', range: '{a}–{b} sur {n}', crumbs: 'Fil d’Ariane', fullPath: 'Afficher le chemin complet', drop: 'Déposez vos fichiers ici, ou', choose: 'choisissez-les', selected: '{n} sélectionnés', optional: 'facultatif', search: 'Rechercher', more: 'de plus' },
  ro: { noMatch: 'Niciun rezultat', clear: 'Ștergeți', remove: 'Eliminați', loading: 'Se încarcă', prev: 'Pagina anterioară', next: 'Pagina următoare', page: 'Pagina {p} din {n}', range: '{a}–{b} din {n}', crumbs: 'Navigare', fullPath: 'Afișați calea completă', drop: 'Trageți fișierele aici sau', choose: 'alegeți-le', selected: '{n} selectate', optional: 'opțional', search: 'Căutați', more: 'în plus' },
};

export const i18n = { STATUS, CONFIDENCE, CATEGORY, REASON, LANGS, UI };

export function ui(lang: Lang | undefined, key: UiKey, vars?: Record<string, string | number>): string {
  let s = ((lang && UI[lang]) || UI.en)[key];
  if (vars) for (const k of Object.keys(vars)) s = s.replace(`{${k}}`, String(vars[k]));
  return s;
}
