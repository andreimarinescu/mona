import { describe, expect, it } from 'vitest';
import type { SettingsView } from './dto';
import { draftOf, settingsChanges, validateSettings } from './settings';

const view: SettingsView = {
  profileName: 'Léa Marchand',
  locale: 'en',
  autoLockMinutes: 15,
  practiceName: 'Cabinet Marchand',
  filingLanguage: 'fr',
  confidenceHigh: 85,
  confidenceLow: 60,
  badgeHours: 24,
  debriefQueueThreshold: 5,
  debriefEarlyMin: 5,
};

const draft = (over: Record<string, string> = {}) => ({ ...draftOf(view), ...over });

describe('validateSettings (C2 §15.1)', () => {
  it('accepts the saved values', () => {
    expect(validateSettings(draft())).toEqual({});
  });

  it.each([
    [{ confidenceLow: '85' }, { confidenceLow: 'order' }],
    [{ confidenceLow: '90' }, { confidenceLow: 'order' }],
    [{ confidenceLow: '0' }, { confidenceLow: 'range' }],
    [{ confidenceHigh: '101' }, { confidenceHigh: 'range' }],
    [{ autoLockMinutes: '0' }, { autoLockMinutes: 'range' }],
    [{ autoLockMinutes: '1441' }, { autoLockMinutes: 'range' }],
    [{ badgeHours: '169' }, { badgeHours: 'range' }],
    [{ debriefQueueThreshold: '51' }, { debriefQueueThreshold: 'range' }],
    [{ debriefEarlyMin: '0' }, { debriefEarlyMin: 'range' }],
    [{ badgeHours: '2.5' }, { badgeHours: 'whole' }],
    [{ badgeHours: '' }, { badgeHours: 'whole' }],
    [{ profileName: '  ' }, { profileName: 'name' }],
    [{ practiceName: 'x'.repeat(121) }, { practiceName: 'name' }],
  ])('rejects %j', (over, expected) => {
    expect(validateSettings(draft(over))).toEqual(expected);
  });

  it('accepts the limits themselves', () => {
    expect(validateSettings(draft({ autoLockMinutes: '1440', badgeHours: '1', confidenceHigh: '100', confidenceLow: '99', debriefQueueThreshold: '50', debriefEarlyMin: '1' }))).toEqual({});
  });
});

describe('settingsChanges', () => {
  it('sends only what differs, as numbers and trimmed text', () => {
    expect(settingsChanges(draft({ confidenceHigh: '90', profileName: ' Léa ' }), view)).toEqual({ confidenceHigh: 90, profileName: 'Léa' });
    expect(settingsChanges(draft(), view)).toEqual({});
  });
});
