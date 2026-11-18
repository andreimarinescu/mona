import { describe, expect, it } from 'vitest';
import { parseTemplate } from '../data/template';
import { MESSAGES, renderTemplates, type SampleValues } from './template';

const sample = (lang: SampleValues['lang'], docDate = '2026-02-05'): SampleValues => ({
  lang,
  entity: 'Studio Numérique',
  fyEnd: '09-30',
  category: 'Banque',
  sub: 'Relevé de compte',
  counterparty: 'Hello bank',
  issuer: null,
  reference: 'R-1',
  docDate,
  periodEnd: '2026-01-31',
});

describe('the mock template renderer (C5 §8, A61)', () => {
  it('renders {date:MMMM} as the month name in the filing language', () => {
    expect(renderTemplates('{entity}', '{date:YYYY-MM}-HB-Studio-{date:MMMM}', sample('fr')).fileName).toBe('2026-02-HB-Studio-Fevrier.pdf');
    expect(renderTemplates('{entity}', '{date:MMMM}', sample('ro')).fileName).toBe('Februarie.pdf');
    expect(renderTemplates('{entity}', '{date:MMMM}', sample('en')).fileName).toBe('February.pdf');
  });

  it('matches MMMM before MM', () => {
    expect(renderTemplates('{entity}', '{date:MMMM}_{date:MM}', sample('fr', '2026-10-03')).fileName).toBe('Octobre_10.pdf');
    expect(parseTemplate('{date:MMMM-YYYY}', 'file').error).toBeNull();
  });

  it('drops accents from literals and values in file names, keeps them in folders', () => {
    const out = renderTemplates('{entity}/{date:MMMM} Relevés', '{date:YYYY}_Relevé Médical_{sub}', sample('fr'));
    expect(out.fileName).toBe('2026_Releve-Medical_Releve-de-compte.pdf');
    expect(out.path).toEqual(['Studio Numérique', 'Février Relevés']);
  });

  it('names MMMM in the bad format message', () => {
    expect(MESSAGES.bad_format).toContain('MMMM');
  });
});
