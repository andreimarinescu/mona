import type { Lang } from '@mona/ui';
import type { AuthState, SettingsPatch, SettingsView, SystemStatus } from '../data/dto';
import { MockError } from './errors';

export interface AccountOptions {
  now: () => number;
  locked?: boolean;
  autoLockMinutes?: number;
  locale?: Lang;
}

export const MOCK_PASSWORD = 'correct horse';
const MAX_FAILURES = 5;
const THROTTLE_MS = 60_000;
const LOCK_ALLOWED = ['/api/auth/state', '/api/auth/unlock', '/api/auth/lock', '/api/auth/logout', '/api/health'];

const invalid = (field: string, message: string) => new MockError(422, 'invalid_value', message, field);

export function createAccount(options: AccountOptions) {
  const { now } = options;
  const settings: SettingsView = {
    profileName: 'Léa Marchand',
    locale: options.locale ?? 'en',
    autoLockMinutes: options.autoLockMinutes ?? 15,
    practiceName: 'Cabinet Marchand',
    filingLanguage: 'fr',
    confidenceHigh: 85,
    confidenceLow: 60,
    badgeHours: 24,
    debriefQueueThreshold: 5,
    debriefEarlyMin: 5,
  };
  let password = MOCK_PASSWORD;
  let manualLock = options.locked ?? false;
  let lastActive = now();
  let mona: 'online' | 'offline' = 'online';
  let failures = 0;
  let throttledUntil = 0;

  const idle = () => now() - lastActive >= settings.autoLockMinutes * 60_000;
  const locked = () => manualLock || idle();

  function view(): AuthState {
    const isLocked = locked();
    return { authenticated: true, locked: isLocked, locale: settings.locale, csrfToken: 'mock-csrf', autoLockMinutes: settings.autoLockMinutes, profileName: isLocked ? null : settings.profileName };
  }

  function unlock(given: string): AuthState {
    if (now() < throttledUntil) throw new MockError(429, 'too_many_attempts', 'Too many attempts.', null, null, { 'Retry-After': '60' });
    if (given !== password) {
      failures += 1;
      if (failures >= MAX_FAILURES) {
        throttledUntil = now() + THROTTLE_MS;
        failures = 0;
      }
      throw new MockError(401, 'invalid_password', 'Wrong password.');
    }
    failures = 0;
    manualLock = false;
    lastActive = now();
    return view();
  }

  function heartbeat() {
    if (locked()) throw new MockError(423, 'locked', 'Locked.');
    lastActive = now();
  }

  /** The lock gate of C2 §2.3 for any /api request: a 423 body while locked, else activity for writes. */
  function gate(method: string, pathname: string): MockError | null {
    if (LOCK_ALLOWED.includes(pathname)) return null;
    if (locked()) return new MockError(423, 'locked', 'Mona is locked.');
    if (method !== 'GET') lastActive = now();
    return null;
  }

  function patch(body: SettingsPatch): SettingsView {
    const next = { ...settings, ...body };
    const text = (field: 'profileName' | 'practiceName') => {
      if (typeof next[field] !== 'string' || next[field].trim().length < 1 || next[field].length > 120) throw invalid(field, 'One to 120 characters.');
    };
    const whole = (field: 'autoLockMinutes' | 'confidenceHigh' | 'confidenceLow' | 'badgeHours' | 'debriefQueueThreshold' | 'debriefEarlyMin', min: number, max: number) => {
      const n = next[field];
      if (!Number.isInteger(n) || n < min || n > max) throw invalid(field, `${min} to ${max}.`);
    };
    if ('profileName' in body) text('profileName');
    if ('practiceName' in body) text('practiceName');
    if ('autoLockMinutes' in body) whole('autoLockMinutes', 1, 1440);
    if ('badgeHours' in body) whole('badgeHours', 1, 168);
    if ('debriefQueueThreshold' in body) whole('debriefQueueThreshold', 1, 50);
    if ('debriefEarlyMin' in body) whole('debriefEarlyMin', 1, 50);
    if ('confidenceLow' in body || 'confidenceHigh' in body) {
      whole('confidenceHigh', 1, 100);
      whole('confidenceLow', 1, 100);
      if (!(0 < next.confidenceLow && next.confidenceLow < next.confidenceHigh)) throw invalid('confidenceLow', 'Low must be under high.');
    }
    if ('locale' in body && !['en', 'fr', 'ro'].includes(next.locale)) throw invalid('locale', 'en, fr or ro.');
    if ('filingLanguage' in body && !['en', 'fr', 'ro'].includes(next.filingLanguage)) throw invalid('filingLanguage', 'en, fr or ro.');
    Object.assign(settings, next);
    return { ...settings };
  }

  function changePassword(current: string, next: string) {
    if (current !== password) throw new MockError(401, 'invalid_password', 'Wrong password.');
    if (typeof next !== 'string' || next.length < 8) throw invalid('newPassword', 'At least 8 characters.');
    password = next;
  }

  const systemStatus = (): SystemStatus => ({
    version: '0.1.0',
    build: 'a1b2c3d',
    env: 'prod',
    mona: { status: mona, hermesVersion: mona === 'online' ? '0.21.5' : null },
    llm: { endpoint: 'local', model: 'qwen3.6-35b-a3b', quantization: 'Q4_K_XL', contextPerSlot: 32768, slots: 2, vramBytes: null },
    queues: { llm: { todo: 0, doing: 0 }, cpu: { todo: 0, doing: 0 } },
    database: 'ok',
    disk: { dataFreeBytes: 214 * 1024 ** 3, dataTotalBytes: 931 * 1024 ** 3 },
    privacy: { cloudAi: false, telegram: true },
  });

  return {
    view,
    unlock,
    heartbeat,
    gate,
    patch,
    changePassword,
    systemStatus,
    settings: () => ({ ...settings }),
    lock: () => {
      manualLock = true;
    },
    idleOut: () => {
      lastActive = now() - settings.autoLockMinutes * 60_000;
    },
    isLocked: locked,
    mona: () => mona,
    setMona: (status: 'online' | 'offline') => {
      mona = status;
    },
  };
}

export type Account = ReturnType<typeof createAccount>;
