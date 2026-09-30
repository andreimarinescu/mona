import type { Entity, Settings, ShellCounts } from './types';

const base = { subUnits: [], people: [], accounts: [], filingLanguage: 'fr' as const };

export const entitiesFixture: Entity[] = [
  { ...base, id: 'ent_01j9zq3k8e6y4v2m7c5r1t0b9a', key: 'cabinet-marchand', displayName: 'Cabinet Marchand', folderName: 'Cabinet Marchand', legalForm: 'SELARL', siren: '000000001', visibility: 'practice', fiscalYearEnd: '12-31' },
  { ...base, id: 'ent_01j9zq3k8f7z5w3n8d6s2v1c0b', key: 'sci-les-tilleuls', displayName: 'SCI Les Tilleuls', folderName: 'SCI Les Tilleuls', legalForm: 'SCI', siren: '000000002', visibility: 'practice', fiscalYearEnd: '12-31' },
  { ...base, id: 'ent_01j9zq3k8g8a6x4p9e7t3w2d1c', key: 'atelier-numerique', displayName: 'Atelier Numérique', folderName: 'Atelier Numérique', legalForm: 'SAS', siren: '000000003', visibility: 'practice', fiscalYearEnd: '06-30' },
  { ...base, id: 'ent_01j9zq3k8h9b7y5q0f8v4x3e2d', key: 'personnel', displayName: 'Personnel', folderName: 'Personnel', legalForm: null, siren: null, visibility: 'personal', fiscalYearEnd: '12-31' },
];

export const settingsFixture: Settings = {
  locale: 'en',
  profileName: 'Léa Marchand',
  practiceName: 'Cabinet Marchand',
};

export const countsFixture: ShellCounts = { reviewCount: 6, queueCount: 0 };
