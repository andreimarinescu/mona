import type { CategoryDto, Entity, FieldKey } from '../data/dto';
import { entitiesFixture } from '../data/fixtures';

export const VISITORS_ID = 'ent_01j9zq3k8j0c8z6r1g9w5y4f3e';

export const ENTITIES: Entity[] = [
  ...entitiesFixture.map((e) => ({
    id: e.id,
    key: e.key,
    displayName: e.displayName,
    folderName: e.folderName,
    visibility: e.visibility,
    fiscalYearEnd: e.fiscalYearEnd,
    filingLanguage: e.filingLanguage,
    subUnits: e.subUnits,
  })),
  { id: VISITORS_ID, key: 'visitors', displayName: 'Visitors', folderName: 'Visitors', visibility: 'practice', fiscalYearEnd: '12-31', filingLanguage: 'fr', subUnits: [] },
];

export const CABINET = ENTITIES[0]!;
export const ATELIER = ENTITIES[2]!;
export const PERSONAL = ENTITIES[3]!;
/** A fictional insurer for the mock debrief. */
export const PRIVATE_INSURER = 'Prévia Retraite';

export const CATEGORIES: CategoryDto[] = [
  {
    id: 'invoices',
    icon: 'invoice',
    labels: { en: 'Received invoices', fr: 'Factures reçues', ro: 'Facturi primite' },
    subcategories: [
      { key: 'telecom', labels: { en: 'Telecom', fr: 'Télécom', ro: 'Telecom' } },
      { key: 'supplies', labels: { en: 'Supplies', fr: 'Fournitures', ro: 'Consumabile' } },
    ],
  },
  { id: 'bank', icon: 'bank', labels: { en: 'Bank', fr: 'Banque', ro: 'Bancă' }, subcategories: [{ key: 'statements', labels: { en: 'Statements', fr: 'Relevés', ro: 'Extrase' } }] },
  {
    id: 'tax',
    icon: 'tax',
    labels: { en: 'Tax', fr: 'Impôts', ro: 'Taxe' },
    subcategories: [{ key: 'contributions', labels: { en: 'Contribution calls', fr: 'Appels de paiement', ro: 'Apeluri de plată' } }],
  },
  { id: 'insurance', icon: 'insurance', labels: { en: 'Insurance', fr: 'Assurances', ro: 'Asigurări' }, subcategories: [] },
];

export interface SeedDoc {
  title: string;
  fileName: string;
  counterparty: string | null;
  docType: string;
  status: 'filed' | 'review' | 'unreadable';
  reasons: ('low' | 'entity' | 'conflict' | 'unreadable')[];
  confidence: number | null;
  entityId: string | null;
  categoryId: string | null;
  subcategoryKey: string | null;
  hoursAgo: number;
  source: 'drop' | 'telegram';
  sentence: string;
  evidence: { field: string; quote: string }[];
}

export const REVIEW_SEED: SeedDoc[] = [
  {
    title: 'Nordtel invoice, September 2026',
    fileName: 'Nordtel_Pro_0926.pdf',
    counterparty: 'Nordtel',
    docType: 'invoice',
    status: 'review',
    reasons: ['low'],
    confidence: 64,
    entityId: ATELIER.id,
    categoryId: 'invoices',
    subcategoryKey: 'telecom',
    hoursAgo: 31,
    source: 'drop',
    sentence: "I think this is the Atelier's line: the number ends in 18, like the last three Atelier invoices. But it's addressed to the practice.",
    evidence: [
      { field: 'reference', quote: 'Ligne : 02 43 •• •• 18 · Offre Pro Fibre' },
      { field: 'addressee', quote: 'Dr Léa Marchand, 12 rue du Pont-de-Mayenne, 53000 Laval' },
      { field: 'amount', quote: 'Total TTC 54,99 €' },
    ],
  },
  {
    title: 'Horizon letter of 24 September',
    fileName: 'Horizon_courrier_0926.pdf',
    counterparty: 'Mutuelle Horizon',
    docType: 'letter',
    status: 'review',
    reasons: ['conflict'],
    confidence: 78,
    entityId: CABINET.id,
    categoryId: 'insurance',
    subcategoryKey: null,
    hoursAgo: 30,
    source: 'drop',
    sentence: "Two of your rules disagree about this document from Mutuelle Horizon, so I've kept it for you.",
    evidence: [{ field: 'counterparty', quote: 'Mutuelle Horizon, association d’assurés' }],
  },
  {
    title: 'IMG_2231.jpg',
    fileName: 'IMG_2231.jpg',
    counterparty: null,
    docType: 'photo',
    status: 'unreadable',
    reasons: ['unreadable'],
    confidence: null,
    entityId: null,
    categoryId: null,
    subcategoryKey: null,
    hoursAgo: 29,
    source: 'telegram',
    sentence: "I can't read this document. Could you scan it again, or take a clearer photo?",
    evidence: [],
  },
  {
    title: 'Delivery note, Laboratoire du Val',
    fileName: 'Laboratoire_du_Val_BL_8841.pdf',
    counterparty: 'Laboratoire du Val',
    docType: 'delivery note',
    status: 'review',
    reasons: ['entity'],
    confidence: 55,
    entityId: null,
    categoryId: 'invoices',
    subcategoryKey: 'supplies',
    hoursAgo: 28,
    source: 'drop',
    sentence: "This document from Laboratoire du Val (delivery note) doesn't say clearly which entity it belongs to.",
    evidence: [{ field: 'counterparty', quote: 'Laboratoire du Val, prothèses dentaires' }],
  },
  {
    title: 'Martin Supplies credit note AV-2291',
    fileName: 'MartinSupplies_AV-2291.pdf',
    counterparty: 'Martin Supplies',
    docType: 'credit note',
    status: 'review',
    reasons: ['low'],
    confidence: 71,
    entityId: CABINET.id,
    categoryId: 'invoices',
    subcategoryKey: 'supplies',
    hoursAgo: 27,
    source: 'drop',
    sentence: "I think this document from Martin Supplies (credit note) belongs to Cabinet Marchand, but I'm not sure enough to file it.",
    evidence: [{ field: 'reference', quote: 'Avoir AV-2291' }],
  },
  {
    title: 'Banque Lumière statement, September',
    fileName: 'BanqueLumiere_releve_09.pdf',
    counterparty: 'Banque Lumière',
    docType: 'statement',
    status: 'review',
    reasons: ['entity'],
    confidence: 52,
    entityId: null,
    categoryId: 'bank',
    subcategoryKey: 'statements',
    hoursAgo: 26,
    source: 'drop',
    sentence: "This document from Banque Lumière (statement) doesn't say clearly which entity it belongs to.",
    evidence: [{ field: 'counterparty', quote: 'Banque Lumière · relevé de compte' }],
  },
];

export const NORDTEL_FILED_TITLES = ['Nordtel invoice, June 2026', 'Nordtel invoice, July 2026', 'Nordtel invoice, August 2026'];

export const PERSONNEL = ENTITIES[3]!;

export const FISCAL_YEAR_END: Record<string, string> = { [ATELIER.id]: '06-30' };

export interface ArchiveSeedDoc {
  title: string;
  fileName: string;
  counterparty: string;
  docType: string;
  reference?: string;
  entityId: string;
  categoryId: string;
  subcategoryKey: string | null;
  date: string;
  amount?: number;
  dueDate?: string;
  rule?: string;
  filedBy?: 'mona' | 'user';
  showcase?: boolean;
}

const URSSAF = { counterparty: 'URSSAF', docType: 'contribution call', entityId: CABINET.id, categoryId: 'tax', subcategoryKey: 'contributions', rule: 'URSSAF calls' } as const;

export const ARCHIVE_SEED: ArchiveSeedDoc[] = [
  { ...URSSAF, title: 'Call for contributions, Q1 2025', fileName: '2025-03-20_URSSAF_Appel_T1.pdf', date: '2025-03-20', amount: 1197 },
  { ...URSSAF, title: 'Call for contributions, Q2 2025', fileName: '2025-06-19_URSSAF_Appel_T2.pdf', date: '2025-06-19', amount: 1197 },
  { ...URSSAF, title: 'Call for contributions, Q3 2025', fileName: '2025-09-20_URSSAF_Appel_T3.pdf', date: '2025-09-20', amount: 1197 },
  { ...URSSAF, title: 'Regularisation of 2024', fileName: '2025-11-30_URSSAF_Regularisation-2024.pdf', date: '2025-11-30', amount: -212.4, filedBy: 'user' },
  { ...URSSAF, title: 'Call for contributions, Q4 2025', fileName: '2025-12-19_URSSAF_Appel_T4.pdf', date: '2025-12-19', amount: 1197 },
  { ...URSSAF, title: 'Annual statement 2025', fileName: '2026-02-10_URSSAF_Attestation-2025.pdf', date: '2026-02-10', amount: 4788 },
  { ...URSSAF, title: 'Call for contributions, Q1 2026', fileName: '2026-03-21_URSSAF_Appel_T1.pdf', date: '2026-03-21', amount: 1197 },
  { ...URSSAF, title: 'Call for contributions, Q2 2026', fileName: '2026-06-20_URSSAF_Appel_T2.pdf', date: '2026-06-20', amount: 1284 },
  { ...URSSAF, title: 'Call for contributions, Q3 2026', fileName: '2026-09-22_URSSAF_Appel_T3.pdf', date: '2026-09-22', amount: 1284, dueDate: '2026-10-15', reference: '2026-T3-EXEMPLE', showcase: true },
  { title: 'CFE advance, May 2025', fileName: '2025-05-15_SIE-Laval_CFE_Acompte.pdf', counterparty: 'SIE Laval', docType: 'tax notice', entityId: CABINET.id, categoryId: 'tax', subcategoryKey: null, date: '2025-05-15', amount: 306, rule: 'SIE Laval' },
  { title: 'CFE balance, December 2025', fileName: '2025-12-15_SIE-Laval_CFE_Solde.pdf', counterparty: 'SIE Laval', docType: 'tax notice', entityId: CABINET.id, categoryId: 'tax', subcategoryKey: null, date: '2025-12-15', amount: 306, rule: 'SIE Laval' },
  { title: 'Mutuelle Horizon, annual premium', fileName: '2026-01-12_MutuelleHorizon_Cotisation.pdf', counterparty: 'Mutuelle Horizon', docType: 'premium notice', entityId: CABINET.id, categoryId: 'insurance', subcategoryKey: null, date: '2026-01-12', amount: 842 },
  { title: 'Banque Lumière statement, July', fileName: '2026-07-31_BanqueLumiere_Releve.pdf', counterparty: 'Banque Lumière', docType: 'statement', entityId: CABINET.id, categoryId: 'bank', subcategoryKey: 'statements', date: '2026-07-31' },
  { title: 'Banque Lumière statement, August', fileName: '2026-08-31_BanqueLumiere_Releve.pdf', counterparty: 'Banque Lumière', docType: 'statement', entityId: CABINET.id, categoryId: 'bank', subcategoryKey: 'statements', date: '2026-08-31' },
  { title: 'Martin Supplies invoice 4410', fileName: '2026-05-06_MartinSupplies_Facture-4410.pdf', counterparty: 'Martin Supplies', docType: 'invoice', entityId: ATELIER.id, categoryId: 'invoices', subcategoryKey: 'supplies', date: '2026-05-06', amount: 213.6, reference: '4410' },
  { title: 'Home insurance, 2026 premium', fileName: '2026-02-03_Horizon_Habitation.pdf', counterparty: 'Mutuelle Horizon', docType: 'premium notice', entityId: PERSONNEL.id, categoryId: 'insurance', subcategoryKey: null, date: '2026-02-03', amount: 312.5 },
  { title: 'Banque Lumière statement, personal, August', fileName: '2026-08-31_BanqueLumiere_Releve-perso.pdf', counterparty: 'Banque Lumière', docType: 'statement', entityId: PERSONNEL.id, categoryId: 'bank', subcategoryKey: 'statements', date: '2026-08-31' },
];

export const NORDTEL_DATES = ['2026-06-12', '2026-07-12', '2026-08-12'];
export const NORDTEL_AMOUNT = 54.99;

export interface SeedField {
  key: FieldKey;
  value: string;
  money?: { value: number; currency: 'EUR' };
  page: number;
  quote: string;
  verified: boolean;
  findQuery: string | null;
  confidence: number;
}

/** Evidence for the document the dev sample PDF stands in for. Where `quote` and `findQuery` differ, the quote is what a model printed and findQuery is what pdf.js can match. */
export const SHOWCASE_FIELDS: SeedField[] = [
  { key: 'issuer', value: 'Union de recouvrement fictive', page: 1, quote: 'Union de recouvrement fictive — URSSAF (exemple)', verified: true, findQuery: 'Union de recouvrement fictive', confidence: 97 },
  { key: 'reference', value: '2026-T3-EXEMPLE', page: 1, quote: 'référence 2026-T3-EXEMPLE', verified: true, findQuery: '2026-T3-EXEMPLE', confidence: 95 },
  { key: 'period_end', value: '2026-09-30', page: 1, quote: 'au 30 septembre 2026', verified: true, findQuery: '30 septembre 2026', confidence: 94 },
  { key: 'amount', value: '1284.00', money: { value: 1284, currency: 'EUR' }, page: 1, quote: 'Montant à payer 1 284,00 €', verified: true, findQuery: '1 284,00', confidence: 98 },
  { key: 'due_date', value: '2026-10-15', page: 1, quote: 'Date limite de paiement : 15 octobre 2026', verified: true, findQuery: 'Date limite de paiement : 15 octobre 2026', confidence: 96 },
  { key: 'addressee', value: 'Cabinet dentaire Exemple', page: 1, quote: 'Cabinet dentaire Exemple SELARL', verified: false, findQuery: null, confidence: 58 },
];
