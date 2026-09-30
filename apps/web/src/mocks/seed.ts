import type { CategoryDto, Entity } from '../data/dto';
import { entitiesFixture } from '../data/fixtures';

export const VISITORS_ID = 'ent_01j9zq3k8j0c8z6r1g9w5y4f3e';

export const ENTITIES: Entity[] = [
  ...entitiesFixture.map((e) => ({
    id: e.id,
    key: e.key,
    displayName: e.displayName,
    folderName: e.folderName,
    visibility: e.visibility,
    filingLanguage: e.filingLanguage,
    subUnits: e.subUnits,
  })),
  { id: VISITORS_ID, key: 'visitors', displayName: 'Visitors', folderName: 'Visitors', visibility: 'practice', filingLanguage: 'fr', subUnits: [] },
];

export const CABINET = ENTITIES[0]!;
export const ATELIER = ENTITIES[2]!;

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
  { id: 'tax', icon: 'tax', labels: { en: 'Tax', fr: 'Impôts', ro: 'Taxe' }, subcategories: [] },
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
