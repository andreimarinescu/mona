import { afterEach, describe, expect, it } from 'vitest';
import type { BriefFacts, Deadline } from '../../data/dto';
import i18n from '../../i18n';
import { briefSentences, dueSentence, mostUrgent, timeOfDay, whenPhrase } from './brief';

const NBSP = '\u00a0';

function deadline(over: Partial<Deadline> = {}): Deadline {
  return {
    id: 'ddl_a',
    documentId: 'doc_a',
    label: 'URSSAF',
    entityId: 'ent_a',
    entityName: 'Cabinet',
    dueDate: '2026-10-03',
    amount: { value: 1284, currency: 'EUR' },
    status: 'open',
    daysLeft: 2,
    reminder: null,
    ...over,
  };
}

function facts(over: Partial<BriefFacts> = {}): BriefFacts {
  return {
    generatedAt: '2026-10-01T07:02:00.000Z',
    since: '2026-10-01T00:00:00.000Z',
    filed: { count: 23, byEntity: [] },
    needsReview: { count: 2, byReason: { low: 2 } },
    dueSoon: [deadline()],
    remindersToday: [],
    learned: [],
    pendingInterview: null,
    ...over,
  };
}

const texts = (lng: 'en' | 'fr' | 'ro', f: BriefFacts, over: { hour?: number; anonymous?: boolean } = {}) =>
  briefSentences(f, { t: i18n.getFixedT(lng), lang: lng, hour: over.hour ?? 8, name: 'Dr Laurent', anonymous: over.anonymous ?? false }).map((s) => s.text);

describe('the brief from its facts (C8 §5.6)', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('writes greeting, filed, review and the due item in English, one sentence each', () => {
    expect(texts('en', facts())).toEqual(['Good morning, Dr Laurent.', 'I filed 23 documents overnight.', '2 need your eye.', 'URSSAF, €1,284.00, is due in 2 days.']);
  });

  it('writes it in French, with U+00A0 in the amount', () => {
    expect(texts('fr', facts())).toEqual(['Bonjour, Dr Laurent.', 'J’ai classé 23 documents cette nuit.', '2 documents attendent votre avis.', `URSSAF, 1${NBSP}284,00${NBSP}€, arrive à échéance dans 2 jours.`]);
  });

  it('writes it in Romanian, with "de" from 20', () => {
    expect(texts('ro', facts())).toEqual(['Bună dimineața, Dr Laurent.', 'Am arhivat 23 de documente peste noapte.', '2 documente așteaptă confirmarea dumneavoastră.', `Scadența pentru URSSAF, 1.284,00${NBSP}€, este peste 2 zile.`]);
    expect(texts('ro', facts({ filed: { count: 1, byEntity: [] } }))[1]).toBe('Am arhivat un document peste noapte.');
    expect(texts('ro', facts({ filed: { count: 20, byEntity: [] } }))[1]).toBe('Am arhivat 20 de documente peste noapte.');
  });

  it('picks the greeting and the filed sentence from the browser clock', () => {
    expect([timeOfDay(8), timeOfDay(12), timeOfDay(17), timeOfDay(18)]).toEqual(['morning', 'afternoon', 'afternoon', 'evening']);
    expect(texts('en', facts(), { hour: 14 }).slice(0, 2)).toEqual(['Good afternoon, Dr Laurent.', 'I filed 23 documents today.']);
    expect(texts('fr', facts(), { hour: 20 })[0]).toBe('Bonsoir, Dr Laurent.');
  });

  it('greets without a name when the profile name is the practice name', () => {
    expect(texts('en', facts(), { anonymous: true })[0]).toBe('Good morning.');
    expect(texts('ro', facts(), { anonymous: true, hour: 19 })[0]).toBe('Bună seara.');
  });

  it('skips what does not apply and says so when nothing came in', () => {
    const quiet = facts({ filed: { count: 0, byEntity: [] }, needsReview: { count: 0, byReason: {} }, dueSoon: [] });
    expect(texts('en', quiet)).toEqual(['Good morning, Dr Laurent.', 'Nothing new came in since yesterday.']);
    expect(texts('en', facts({ filed: { count: 1, byEntity: [] }, needsReview: { count: 1, byReason: {} }, dueSoon: [] }))).toEqual(['Good morning, Dr Laurent.', 'I filed one document overnight.', 'One needs your eye.']);
  });

  it('names the most urgent due item: overdue first, then the soonest', () => {
    const items = [deadline({ id: 'b', label: 'Later', daysLeft: 4 }), deadline({ id: 'c', label: 'Late', daysLeft: -3 }), deadline({ id: 'a', label: 'Soon', daysLeft: 1 })];
    expect(mostUrgent(items)?.label).toBe('Late');
    expect(texts('en', facts({ dueSoon: items }))[3]).toBe('Late is overdue.');
    expect(mostUrgent(items.slice(0, 1).concat(items.slice(2)))?.label).toBe('Soon');
  });

  it('words a due date as today, tomorrow or in N days, and drops the amount when there is none', () => {
    const t = i18n.getFixedT('en');
    expect([0, 1, 5].map((d) => whenPhrase(d, t))).toEqual(['today', 'tomorrow', 'in 5 days']);
    expect(dueSentence(deadline({ amount: undefined, daysLeft: 1 }), { t, lang: 'en' })).toBe('URSSAF is due tomorrow.');
  });

  it('ends with the pending questions and links each sentence to its source', () => {
    const f = facts({ pendingInterview: { interviewId: 'int_a', openQuestions: 5 } });
    const sentences = briefSentences(f, { t: i18n.getFixedT('en'), lang: 'en', hour: 8, name: 'Dr Laurent', anonymous: false });
    expect(sentences.map((s) => s.id)).toEqual(['greeting', 'filed', 'review', 'due', 'questions']);
    expect(sentences.at(-1)?.text).toBe('I have 5 questions for you.');
    expect(sentences.map((s) => s.link?.kind)).toEqual([undefined, 'activity', 'review', 'document', 'questions']);
  });
});
