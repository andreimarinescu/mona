import { describe, expect, it } from 'vitest';
import { KINDS } from '../routes/activity/kinds';
import i18n from './index';

const ACTIONS = ['file', 'move', 'rename', 'unfile', 'delete', 'undo', 'redo', 'doc.update', 'rule.create', 'rule.change', 'deadline.add', 'reminder.add', 'mark.unreadable'];
const GROUP_KINDS = ['intake_batch', 'rule_apply', 'correction', 'undo', 'redo', 'refile'];
const FIELDS = ['entity', 'counterparty', 'issuer', 'reference', 'doc_type', 'doc_date', 'period_start', 'period_end', 'amount', 'due_date', 'addressee'];

function keys(): string[] {
  return [
    ...KINDS.map((k) => `activity.kind.${k}`),
    ...ACTIONS.flatMap((a) => ['mona', 'user'].map((who) => `activity.action.${a}_${who}`)),
    ...GROUP_KINDS.flatMap((g) => ['mona', 'user'].map((who) => `activity.group.${g}_${who}`)),
    ...['undoable', 'undone', 'superseded', 'not_undoable'].map((s) => `activity.undoState.${s}`),
    ...FIELDS.map((f) => `review.field.${f}`),
    ...['queued', 'reading', 'ocr', 'classifying', 'result'].map((s) => `intake.steps.${s}`),
    ...['unsupported_type', 'too_large', 'empty', 'unreadable_file'].map((r) => `intake.reject.${r}`),
    ...['interview', 'correction', 'seed'].map((s) => `rules.source.${s}`),
  ];
}

describe('the keys built from closed enums exist in every language', () => {
  it.each(['en', 'fr', 'ro'])('%s', (lng) => {
    const t = i18n.getFixedT(lng);
    const missing = keys().filter((k) => !i18n.exists(k, { lng }) || t(k) === k);
    expect(missing).toEqual([]);
  });

  it('plural keys that the code passes by name exist', () => {
    for (const lng of ['en', 'fr', 'ro']) {
      for (const k of ['toast.undone', 'toast.redone', 'toast.undoSkipped', 'review.toast.ruleApplied', 'intake.overLimit', 'rules.preview.applied', 'chat.thinking.done', 'interview.affects', 'interview.toast.appliedAll', 'deadline.dueIn', 'deadline.overdue']) {
        expect(i18n.exists(k, { lng, count: 2 }), `${lng} ${k}`).toBe(true);
        expect(i18n.getFixedT(lng)(k, { count: 2, n: 2 })).not.toContain('{{');
      }
    }
  });

  it('formats Romanian plurals with "de" from 20 and French with "de" from a million', () => {
    expect(i18n.getFixedT('ro')('toast.undone', { count: 3, n: 3 })).toBe('Am anulat 3 modificări');
    expect(i18n.getFixedT('ro')('toast.undone', { count: 20, n: 20 })).toBe('Am anulat 20 de modificări');
    expect(i18n.getFixedT('fr')('toast.undone', { count: 1_000_000, n: '1 000 000' })).toBe('1 000 000 de modifications annulées');
  });
});
