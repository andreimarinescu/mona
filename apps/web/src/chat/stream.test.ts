// @vitest-environment node
import { readFileSync } from 'node:fs';
import { parseJsonEventStream, readUIMessageStream, uiMessageChunkSchema, type UIMessageChunk } from 'ai';
import { describe, expect, it } from 'vitest';
import { lastUserText } from './transport';
import type { MonaUIMessage } from './types';

const golden: UIMessageChunk[] = JSON.parse(
  readFileSync(
    new URL('../../../../docs/spikes/s5/fixtures/completions-stream-overlay.ui-chunks.json', import.meta.url),
    'utf8',
  ),
);

const doc = (title: string) => ({ type: 'data-doc', id: 'doc_urssaf_q3', data: { id: 'doc_urssaf_q3', title } });
const deadline = {
  type: 'data-deadline',
  id: 'ddl_1',
  data: {
    id: 'ddl_1',
    documentId: 'doc_urssaf_q3',
    label: 'URSSAF 3e trimestre',
    entityId: 'ent_1',
    entityName: 'Cabinet Marchand',
    dueDate: '2026-10-14',
    amount: { value: 1284, currency: 'EUR' },
    status: 'open',
    daysLeft: 14,
    reminder: null,
  },
};

function adapterStream(): string {
  const chunks: unknown[] = [
    { type: 'start', messageId: 'msg_1', messageMetadata: { conversationId: 'cnv_1', replyLanguage: 'fr' } },
    { type: 'start-step' },
  ];
  for (const c of golden) {
    chunks.push(c);
    if (c.type === 'tool-output-available') chunks.push(doc('first'), doc('URSSAF appel de cotisation T3'), deadline);
  }
  chunks.push({ type: 'finish-step' }, { type: 'finish', finishReason: 'stop', messageMetadata: { reasoningMs: 1200 } });
  return chunks.map((c) => `data: ${JSON.stringify(c)}\n\n`).join('') + 'data: [DONE]\n\n';
}

async function readMessage(sse: string): Promise<MonaUIMessage> {
  const bytes = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(sse));
      controller.close();
    },
  });
  const chunks = parseJsonEventStream({ stream: bytes, schema: uiMessageChunkSchema }).pipeThrough(
    new TransformStream({
      transform(result, controller) {
        if (!result.success) throw result.error;
        controller.enqueue(result.value);
      },
    }),
  );
  let last: MonaUIMessage | undefined;
  for await (const message of readUIMessageStream<MonaUIMessage>({ stream: chunks, terminateOnError: true })) {
    last = message;
  }
  return last!;
}

describe('adapter stream (S1 fixture through the Python translator)', () => {
  it('validates against ai@7 chunk schema and builds reasoning, tool, card and text parts', async () => {
    const message = await readMessage(adapterStream());
    expect(message.id).toBe('msg_1');
    expect(message.metadata).toEqual({ conversationId: 'cnv_1', replyLanguage: 'fr', reasoningMs: 1200 });
    expect(message.parts.map((p) => p.type)).toEqual([
      'step-start',
      'reasoning',
      'dynamic-tool',
      'data-doc',
      'data-deadline',
      'reasoning',
      'text',
    ]);
    const tool = message.parts[2];
    expect(tool).toMatchObject({ type: 'dynamic-tool', toolName: 'get_document', state: 'output-available' });
    expect(message.parts[3]).toMatchObject({ id: 'doc_urssaf_q3', data: { title: 'URSSAF appel de cotisation T3' } });
    expect(message.parts[4]).toMatchObject({ id: 'ddl_1', data: { daysLeft: 14, amount: { value: 1284 } } });
    expect(message.parts[6]).toMatchObject({ type: 'text', text: expect.stringMatching(/^\s*Vous regardez/) });
  });
});

describe('a live capture of the adapter (list_deadlines turn)', () => {
  it('validates chunk by chunk and yields reasoning, the tool, three deadline cards and text', async () => {
    const sse = readFileSync(new URL('./fixtures/adapter-live-deadlines.sse', import.meta.url), 'utf8');
    const message = await readMessage(sse);
    expect(message.metadata).toMatchObject({ replyLanguage: 'en', reasoningMs: expect.any(Number) });
    expect(message.parts.map((p) => p.type)).toEqual([
      'step-start',
      'reasoning',
      'dynamic-tool',
      'data-deadline',
      'data-deadline',
      'data-deadline',
      'reasoning',
      'text',
    ]);
    expect(message.parts[2]).toMatchObject({ toolName: 'list_deadlines', state: 'output-available' });
    const card = message.parts.find((p) => p.type === 'data-deadline');
    expect(card).toMatchObject({ data: { label: expect.any(String), daysLeft: expect.any(Number), status: 'open' } });
  });
});

describe('lastUserText', () => {
  it('joins the text parts of the newest user message', () => {
    const messages = [
      { id: 'u1', role: 'user', parts: [{ type: 'text', text: 'old' }] },
      { id: 'a1', role: 'assistant', parts: [{ type: 'text', text: 'reply' }] },
      { id: 'u2', role: 'user', parts: [{ type: 'text', text: 'Find the ' }, { type: 'text', text: 'URSSAF letter' }] },
    ] as MonaUIMessage[];
    expect(lastUserText(messages)).toBe('Find the URSSAF letter');
  });
});
