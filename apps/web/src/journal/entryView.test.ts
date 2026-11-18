import { describe, expect, it } from 'vitest';
import i18n from '../i18n';
import { entry } from '../test/fixtures';
import { entryTitle } from './entryView';

describe('the title of a deadline status entry (A60)', () => {
  it('names the status in each language', () => {
    const done = entry({ action: 'deadline.status', actor: 'user', after: { status: 'done' } });
    expect(entryTitle(done, {}, {}, i18n.getFixedT('en'))).toBe('You marked a deadline done');
    expect(entryTitle({ ...done, after: { status: 'open' } }, {}, {}, i18n.getFixedT('fr'))).toBe('Vous avez rouvert une échéance');
    expect(entryTitle({ ...done, after: { status: 'dismissed' } }, {}, {}, i18n.getFixedT('ro'))).toBe('Ați ignorat o scadență');
  });
});

describe('the title of an export entry', () => {
  const t = i18n.getFixedT('en');

  it('names an accountant pack apart from a table file', () => {
    const pack = entry({ action: 'export', actor: 'user', documentIds: [], after: { kind: 'pack', fiscal_year: 2025, documents: 7 } });
    const table = entry({ action: 'export', actor: 'mona', documentIds: [], after: { format: 'xlsx', rows: 3 } });
    expect(entryTitle(pack, {}, {}, t)).toBe('You prepared an accountant pack');
    expect(entryTitle({ ...pack, actor: 'mona' }, {}, {}, i18n.getFixedT('fr'))).toBe('Mona a préparé un dossier pour le comptable');
    expect(entryTitle(table, {}, {}, t)).toBe('Mona made a table file');
  });

  it('names a table shown in the chat apart from a table file (A36)', () => {
    const shown = entry({ action: 'export', actor: 'mona', documentIds: [], after: { format: 'table', rows: 3 } });
    expect(entryTitle(shown, {}, {}, t)).toBe('Mona showed a table in the chat');
  });
});
