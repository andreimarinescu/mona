import { afterEach, describe, expect, it, vi } from 'vitest';
import { unlock } from '../data/auth';
import { asFeed } from '../data/conversations';
import { setAuthLostHandler, setCsrfToken } from '../data/http';
import { chatErrorCode } from './errorCode';
import { monaTransport } from './transport';
import type { MonaUIMessage } from './types';

describe('chatErrorCode', () => {
  it.each([
    ['mona_offline', 'mona_offline'],
    ['stream_interrupted', 'stream_interrupted'],
    ['{"error":{"code":"turn_in_progress","message":"x"}}', 'turn_in_progress'],
    ['{"error":{"code":"locked","message":"x"}}', 'locked'],
    ['{"error":{"code":"made_up","message":"x"}}', 'internal'],
    ['Failed to fetch', 'internal'],
  ])('%s → %s', (message, code) => {
    expect(chatErrorCode(new Error(message))).toBe(code);
  });
});

describe('asFeed (C2 §13)', () => {
  const c = (id: string, title: string) => ({ id, title, lastMessageAt: '2026-10-01T08:00:00Z', turnCount: 1 });
  it('passes a Feed through and reads a bare array as one page, searched by folded title', () => {
    const feed = { items: [c('cnv_a', 'A')], nextCursor: 'x' };
    expect(asFeed(feed, 'zzz')).toBe(feed);
    expect(asFeed([c('cnv_a', 'Échéancier'), c('cnv_b', 'Other')], 'echeancier')).toEqual({ items: [c('cnv_a', 'Échéancier')], nextCursor: null });
  });
});

describe('monaTransport body (C3 §2)', () => {
  async function body(t: ReturnType<typeof monaTransport>, text: string) {
    const messages = [{ id: 'u', role: 'user', parts: [{ type: 'text', text }] }] as MonaUIMessage[];
    const prepare = (t.transport as unknown as { prepareSendMessagesRequest: (o: unknown) => { body: Record<string, unknown> } }).prepareSendMessagesRequest;
    return prepare({ messages, id: 'x', requestMetadata: undefined, body: undefined, credentials: undefined, headers: undefined, api: '/api/chat', trigger: 'submit-message', messageId: undefined }).body;
  }

  it('the page context override is for one turn; the pinned reply language is for every later turn', async () => {
    const t = monaTransport({ pageContext: () => ({ route: '/archive', summary: 'Archive' }), locale: () => 'fr' });
    t.overrideNext({ route: '/intake', summary: 'Interview int_x, question qst_y open' });
    expect(await body(t, 'a')).toEqual({ conversationId: undefined, message: 'a', pageContext: { route: '/intake', summary: 'Interview int_x, question qst_y open' }, locale: 'fr' });
    t.setReplyLanguage('en');
    t.setConversationId('cnv_1');
    expect(await body(t, 'b')).toEqual({ conversationId: 'cnv_1', message: 'b', pageContext: { route: '/archive', summary: 'Archive' }, locale: 'fr', replyLanguage: 'en' });
  });
});

describe('monaTransport headers (C2 §2.4)', () => {
  afterEach(() => {
    setCsrfToken(null);
    vi.unstubAllGlobals();
  });

  it('sends the session CSRF token from the auth state, and the new one after an unlock', async () => {
    let token = 'tok-before';
    const sent: (string | null)[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url === '/api/auth/state') return Response.json({ csrfToken: token });
        if (url === '/api/auth/unlock') {
          token = 'tok-after';
          return Response.json({ authenticated: true, locked: false, locale: 'en', csrfToken: token, autoLockMinutes: 15, profileName: 'x' });
        }
        sent.push(new Headers(init?.headers).get('x-csrf-token'));
        return new Response('data: [DONE]\n\n', { headers: { 'content-type': 'text/event-stream' } });
      }),
    );
    setCsrfToken(null);
    const t = monaTransport({ pageContext: () => ({ route: '/chat', summary: 'Chat page' }), locale: () => 'en' });
    const messages = [{ id: 'u', role: 'user', parts: [{ type: 'text', text: 'hi' }] }] as MonaUIMessage[];
    const send = () => t.transport.sendMessages({ chatId: 'x', messages, abortSignal: undefined, trigger: 'submit-message', messageId: undefined });
    await send();
    await unlock('pw');
    await send();
    expect(sent).toEqual(['tok-before', 'tok-after']);
  });
});

describe('monaTransport after an auto-lock (C2 §16.3)', () => {
  afterEach(() => {
    setAuthLostHandler(null);
    setCsrfToken(null);
    vi.unstubAllGlobals();
  });

  it.each([
    [423, 'locked', 1],
    [401, 'unauthenticated', 1],
    [401, 'invalid_password', 0],
    [409, 'turn_in_progress', 0],
  ])('%i %s calls the auth-lost handler %i time(s)', async (status, code, times) => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ error: { code, message: 'x' } }, { status })),
    );
    setCsrfToken('tok');
    const lost = vi.fn();
    setAuthLostHandler(lost);
    const t = monaTransport({ pageContext: () => ({ route: '/chat', summary: 'Chat page' }), locale: () => 'en' });
    const messages = [{ id: 'u', role: 'user', parts: [{ type: 'text', text: 'hi' }] }] as MonaUIMessage[];
    await expect(t.transport.sendMessages({ chatId: 'x', messages, abortSignal: undefined, trigger: 'submit-message', messageId: undefined })).rejects.toThrow();
    expect(lost).toHaveBeenCalledTimes(times);
  });
});
