import { act, render } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { HEARTBEAT_MS, firstName, safeNext, unlockHref, useHeartbeat } from './auth';
import { ApiError, isAuthLoss, request, setAuthLostHandler } from './http';

describe('safeNext (C2 §16.3)', () => {
  it.each([
    ['/review', '/review'],
    ['/documents/doc_a?page=2', '/documents/doc_a?page=2'],
    ['/settings#status', '/settings#status'],
    ['//evil.example', '/'],
    ['/\\evil.example', '/'],
    ['https://evil.example', '/'],
    ['review', '/'],
    ['/unlock', '/'],
    [undefined, '/'],
  ])('%s → %s', (input, expected) => {
    expect(safeNext(input)).toBe(expected);
  });

  it('leaves next out of the unlock link when the person was on Home', () => {
    expect(unlockHref('/')).toEqual({ to: '/unlock', search: {} });
    expect(unlockHref('/chat/cnv_a')).toEqual({ to: '/unlock', search: { next: '/chat/cnv_a' } });
  });
});

describe('firstName', () => {
  it('takes the first name after a title, and is empty without a profile', () => {
    expect(['Léa Marchand', 'Dr Léa Marchand', 'docteur  Léa', 'Mme Ionescu Ana', '  Ana ', null, undefined, ''].map(firstName)).toEqual(['Léa', 'Léa', 'Léa', 'Ionescu', 'Ana', '', '', '']);
  });
});

describe('auth loss', () => {
  afterEach(() => {
    setAuthLostHandler(null);
    vi.unstubAllGlobals();
  });

  it('is a 423, or a 401 unauthenticated, and not a wrong password', () => {
    expect([isAuthLoss(423, 'locked'), isAuthLoss(401, 'unauthenticated'), isAuthLoss(401, 'invalid_password'), isAuthLoss(404, 'not_found')]).toEqual([true, true, false, false]);
  });

  it('calls the handler once per refused request and still throws the error', async () => {
    const lost = vi.fn();
    setAuthLostHandler(lost);
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ error: { code: 'locked', message: 'x' } }, { status: 423 })));
    await expect(request('GET', '/api/review')).rejects.toBeInstanceOf(ApiError);
    expect(lost).toHaveBeenCalledTimes(1);
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ error: { code: 'invalid_password', message: 'x' } }, { status: 401 })));
    await expect(request('POST', '/api/auth/unlock', { json: { password: 'x' } })).rejects.toMatchObject({ code: 'invalid_password' });
    expect(lost).toHaveBeenCalledTimes(1);
  });
});

describe('useHeartbeat (C2 §2.3)', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  function Probe({ send }: { send: () => Promise<unknown> }) {
    useHeartbeat(send);
    return null;
  }

  it('sends nothing while the person does nothing', () => {
    const send = vi.fn(async () => undefined);
    render(<Probe send={send} />);
    act(() => void vi.advanceTimersByTime(HEARTBEAT_MS * 5));
    expect(send).not.toHaveBeenCalled();
  });

  it('sends one heartbeat after activity, and at most one a minute', () => {
    const send = vi.fn(async () => undefined);
    render(<Probe send={send} />);
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'a' }));
      vi.advanceTimersByTime(HEARTBEAT_MS - 1);
    });
    expect(send).not.toHaveBeenCalled();
    act(() => void vi.advanceTimersByTime(1));
    expect(send).toHaveBeenCalledTimes(1);
    act(() => {
      for (let i = 0; i < 20; i++) document.dispatchEvent(new Event('pointerdown'));
      vi.advanceTimersByTime(HEARTBEAT_MS - 1);
    });
    expect(send).toHaveBeenCalledTimes(1);
    act(() => void vi.advanceTimersByTime(1));
    expect(send).toHaveBeenCalledTimes(2);
    act(() => void vi.advanceTimersByTime(HEARTBEAT_MS * 3));
    expect(send).toHaveBeenCalledTimes(2);
  });
});
