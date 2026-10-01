import type { CategoryDto, Entity, FieldKey, PersonDetail } from '../data/dto';
import { makeId } from './ids';

export const VISITORS_ID = 'ent_01j9zq3k8j0c8z6r1g9w5y4f3e';

export const PEOPLE: PersonDetail[] = [
  { id: makeId('prs', 1), key: 'lea', displayName: 'Léa Marchand', shortName: 'Léa', aliases: [] },
  { id: makeId('prs', 2), key: 'camille', displayName: 'Camille Roux', shortName: 'Camille', aliases: [] },
  { id: makeId('prs', 3), key: 'thomas', displayName: 'Thomas Marchand', shortName: 'Thomas', aliases: [] },
];

const [LEA, CAMILLE, THOMAS] = PEOPLE as [PersonDetail, PersonDetail, PersonDetail];

export const ENTITIES: Entity[] = [
  {
    id: 'ent_01j9zq3k8e6y4v2m7c5r1t0b9a',
    key: 'cabinet-marchand',
    displayName: 'Cabinet Marchand',
    folderName: 'Cabinet Marchand',
    legalForm: 'SELARL',
    siren: '000000001',
    visibility: 'practice',
    fiscalYearEnd: '12-31',
    filingLanguage: 'fr',
    subUnits: [{ id: makeId('sub', 1), key: 'laval', label: 'Laval (main)', personId: null }],
    people: [
      { personId: LEA.id, role: 'manager' },
      { personId: CAMILLE.id, role: 'assistant' },
    ],
    accounts: [{ id: makeId('acc', 1), key: 'cabinet-main', label: 'Crédit Mutuel', ibanLast4: '4471', subUnitId: null }],
  },
  {
    id: 'ent_01j9zq3k8f7z5w3n8d6s2v1c0b',
    key: 'sci-les-tilleuls',
    displayName: 'SCI Les Tilleuls',
    folderName: 'SCI Les Tilleuls',
    legalForm: 'SCI',
    siren: '000000002',
    visibility: 'practice',
    fiscalYearEnd: '12-31',
    filingLanguage: 'fr',
    subUnits: [],
    people: [{ personId: LEA.id, role: 'manager' }],
    accounts: [{ id: makeId('acc', 2), key: 'sci-main', label: 'Crédit Mutuel', ibanLast4: '2208', subUnitId: null }],
  },
  {
    id: 'ent_01j9zq3k8g8a6x4p9e7t3w2d1c',
    key: 'atelier-numerique',
    displayName: 'Atelier Numérique',
    folderName: 'Atelier Numérique',
    legalForm: 'SAS',
    siren: '000000003',
    visibility: 'practice',
    fiscalYearEnd: '06-30',
    filingLanguage: 'fr',
    subUnits: [],
    people: [{ personId: LEA.id, role: 'president' }],
    accounts: [{ id: makeId('acc', 3), key: 'atelier-main', label: 'Crédit Mutuel', ibanLast4: '0381', subUnitId: null }],
  },
  {
    id: 'ent_01j9zq3k8h9b7y5q0f8v4x3e2d',
    key: 'famille',
    displayName: 'Famille Marchand',
    folderName: 'Famille Marchand',
    legalForm: null,
    siren: null,
    visibility: 'personal',
    fiscalYearEnd: '12-31',
    filingLanguage: 'fr',
    subUnits: [
      { id: makeId('sub', 2), key: 'lea', label: 'Léa', personId: LEA.id },
      { id: makeId('sub', 3), key: 'thomas', label: 'Thomas', personId: THOMAS.id },
    ],
    people: [
      { personId: LEA.id, role: null },
      { personId: THOMAS.id, role: null },
    ],
    accounts: [
      { id: makeId('acc', 4), key: 'perso-bank', label: 'Banque Lumière', ibanLast4: '3350', subUnitId: null },
      { id: makeId('acc', 5), key: 'perso-credit', label: 'Crédit Mutuel', ibanLast4: '7712', subUnitId: null },
    ],
  },
  {
    id: VISITORS_ID,
    key: 'visitors',
    displayName: 'Visitors',
    folderName: 'Visitors',
    legalForm: null,
    siren: null,
    visibility: 'practice',
    fiscalYearEnd: '12-31',
    filingLanguage: 'fr',
    subUnits: [],
    people: [],
    accounts: [],
  },
];

export const CABINET = ENTITIES[0]!;
export const ATELIER = ENTITIES[2]!;
export const PERSONAL = ENTITIES[3]!;
/** A fictional insurer for the mock debrief. */
export const PRIVATE_INSURER = 'Prévia Retraite';

const TEMPLATE = {
  invoices: { pathTemplate: '{entity}/{year} {entity}/{category}/{sub}', fileTemplate: '{date:YYYY-MM-DD}_{counterparty}_{reference}' },
  bank: { pathTemplate: '{entity}/{category}/{fy}', fileTemplate: '{date:YYYY-MM-DD}_{counterparty}_{sub}' },
  tax: { pathTemplate: '{entity}/{category}/{year}', fileTemplate: '{date:YYYY-MM-DD}_{issuer}_{sub}' },
  insurance: { pathTemplate: '{entity}/{category}/{counterparty}/{year}', fileTemplate: '{date:YYYY-MM-DD}_{counterparty}_{sub}_{reference}' },
};

export const CATEGORIES: CategoryDto[] = [
  {
    id: 'invoices',
    icon: 'invoice',
    labels: { en: 'Received invoices', fr: 'Factures reçues', ro: 'Facturi primite' },
    subcategories: [
      { key: 'telecom', labels: { en: 'Telecom', fr: 'Télécom', ro: 'Telecom' } },
      { key: 'supplies', labels: { en: 'Supplies', fr: 'Fournitures', ro: 'Consumabile' } },
    ],
    template: TEMPLATE.invoices,
    entityTemplates: [],
  },
  { id: 'bank', icon: 'bank', labels: { en: 'Bank', fr: 'Banque', ro: 'Bancă' }, subcategories: [{ key: 'statements', labels: { en: 'Statements', fr: 'Relevés', ro: 'Extrase' } }], template: TEMPLATE.bank, entityTemplates: [] },
  {
    id: 'tax',
    icon: 'tax',
    labels: { en: 'Tax', fr: 'Impôts', ro: 'Taxe' },
    subcategories: [{ key: 'contributions', labels: { en: 'Contribution calls', fr: 'Appels de paiement', ro: 'Apeluri de plată' } }],
    template: TEMPLATE.tax,
    entityTemplates: [],
  },
  { id: 'insurance', icon: 'insurance', labels: { en: 'Insurance', fr: 'Assurances', ro: 'Asigurări' }, subcategories: [], template: TEMPLATE.insurance, entityTemplates: [] },
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

export interface SeedRule {
  n: number;
  name: string;
  condition: string;
  destination: string[];
  state: 'draft' | 'active' | 'disabled';
  source: 'interview' | 'correction' | 'seed';
  firedCount: number;
  lastFiredHoursAgo: number | null;
  correctionsSince: number;
  createdHoursAgo: number;
}

const Y = '{year} Cabinet Marchand';

export const RULES_SEED: SeedRule[] = [
  { n: 900, name: 'URSSAF calls', condition: 'When the counterparty is URSSAF.', destination: ['Cabinet Marchand', Y, 'Impôts', 'Appels de paiement'], state: 'active', source: 'seed', firedCount: 14, lastFiredHoursAgo: 216, correctionsSince: 0, createdHoursAgo: 2_400 },
  {
    n: 910,
    name: 'Horizon letters are for the practice, except the retirement contract',
    condition: 'When the counterparty is Mutuelle Horizon, and the text doesn’t mention “retirement”.',
    destination: ['Cabinet Marchand', 'Assurances', 'Mutuelle Horizon'],
    state: 'active',
    source: 'interview',
    firedCount: 4,
    lastFiredHoursAgo: 2,
    correctionsSince: 0,
    createdHoursAgo: 3,
  },
  {
    n: 911,
    name: 'The Nordtel line ending in 18 is the Atelier’s, not the practice’s',
    condition: 'When the counterparty is Nordtel, and the text mentions “18”.',
    destination: ['Atelier Numérique', Y, 'Factures reçues', 'Télécom'],
    state: 'active',
    source: 'correction',
    firedCount: 4,
    lastFiredHoursAgo: 1,
    correctionsSince: 0,
    createdHoursAgo: 4,
  },
  { n: 912, name: 'Martin Supplies invoices', condition: 'When the counterparty is Martin Supplies.', destination: ['Atelier Numérique', Y, 'Factures reçues', 'Fournitures'], state: 'active', source: 'seed', firedCount: 148, lastFiredHoursAgo: 4, correctionsSince: 1, createdHoursAgo: 2_400 },
  { n: 913, name: 'Laboratoire du Val', condition: 'When the counterparty is Laboratoire du Val.', destination: ['Cabinet Marchand', Y, 'Factures reçues', 'Fournitures'], state: 'active', source: 'correction', firedCount: 121, lastFiredHoursAgo: 52, correctionsSince: 0, createdHoursAgo: 190 },
  { n: 914, name: 'Banque Lumière, account ••4471', condition: 'When it shows the Crédit Mutuel account ••4471.', destination: ['Cabinet Marchand', 'Banque', '{fy}'], state: 'active', source: 'seed', firedCount: 96, lastFiredHoursAgo: 5, correctionsSince: 0, createdHoursAgo: 2_400 },
  { n: 915, name: 'Banque Lumière statements, personal', condition: 'When the counterparty is Banque Lumière, and it shows one of Famille Marchand’s accounts.', destination: ['Famille Marchand', 'Banque', '{fy}'], state: 'active', source: 'seed', firedCount: 22, lastFiredHoursAgo: 52, correctionsSince: 3, createdHoursAgo: 2_400 },
  { n: 916, name: 'Energie Verte, Les Tilleuls meter', condition: 'When the counterparty is Energie Verte, and the text mentions “Tilleuls”.', destination: ['SCI Les Tilleuls', Y, 'Énergie'], state: 'active', source: 'interview', firedCount: 12, lastFiredHoursAgo: 6, correctionsSince: 0, createdHoursAgo: 700 },
  { n: 917, name: 'Mutuelle Horizon premium', condition: 'When the counterparty is Mutuelle Horizon, and it is a premium notice.', destination: ['Cabinet Marchand', 'Assurances', 'Mutuelle Horizon'], state: 'active', source: 'interview', firedCount: 7, lastFiredHoursAgo: 23, correctionsSince: 0, createdHoursAgo: 500 },
  { n: 901, name: 'SIE Laval tax notices', condition: 'When the counterparty is SIE Laval.', destination: ['Cabinet Marchand', Y, 'Impôts'], state: 'disabled', source: 'seed', firedCount: 24, lastFiredHoursAgo: 480, correctionsSince: 0, createdHoursAgo: 2_400 },
  { n: 918, name: 'Banque Lumière: Atelier statements', condition: 'When the counterparty is Banque Lumière, and the amount is over 2000.00.', destination: ['Atelier Numérique', 'Banque', '{fy}'], state: 'draft', source: 'correction', firedCount: 0, lastFiredHoursAgo: null, correctionsSince: 0, createdHoursAgo: 30 },
];

/** Mock-only history: what the pipeline did before the in-memory documents exist. */
export const OVERNIGHT = { cabinet: 14, atelier: 9, entries: 23 };
export const INGESTION_HISTORY = [9, 14, 22, 7, 0, 0, 18, 24, 12, 9, 31, 15, 11];
