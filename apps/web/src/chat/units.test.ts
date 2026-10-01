import { describe, expect, it } from 'vitest';
import { asFeed } from '../data/conversations';
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
