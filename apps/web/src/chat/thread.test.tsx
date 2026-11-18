import { act, cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { chatBodies } from '../mocks';
import type { ChatOutbox } from '../state/context';
import { useMockApi } from '../test/mockApi';
import { renderInApp } from '../test/renderInApp';
import { ConversationThread } from './ConversationThread';
import { MonaMessage } from './Messages';
import { ReasoningClock, ReasoningClockContext } from './reasoningClock';
import type { MonaUIMessage, PageContext } from './types';

const reasoning = (text: string, state: 'streaming' | 'done') => ({ type: 'reasoning' as const, text, state });

function twoBlocks(first: 'streaming' | 'done', second: 'streaming' | 'done' | null, reasoningMs?: number): MonaUIMessage {
  return {
    id: 'msg_t',
    role: 'assistant',
    metadata: { reasoningMs },
    parts: [{ type: 'step-start' }, reasoning('Looking.', first), ...(second ? [{ type: 'dynamic-tool', toolName: 'get_document', toolCallId: 'c1', state: 'output-available', input: {}, output: { status: 'completed' } }, reasoning('Adding up.', second)] : [])],
  } as MonaUIMessage;
}

describe('ThinkingBlock: "Thought for N seconds" per block, not the turn total', () => {
  useMockApi();

  it('times each block from its own start to its own end while streaming', async () => {
    let now = 1_000;
    const clock = new ReasoningClock(() => now);
    const ui = (m: MonaUIMessage) => (
      <ReasoningClockContext.Provider value={clock}>
        <MonaMessage message={m} streaming newest />
      </ReasoningClockContext.Provider>
    );
    const { rerender } = await renderInApp(ui(twoBlocks('streaming', null)));
    expect(screen.getByTestId('thinking')).toHaveTextContent('Mona is thinking…');
    now = 4_000;
    rerender(ui(twoBlocks('done', 'streaming')));
    now = 11_000;
    rerender(ui(twoBlocks('done', 'done', 10_000)));
    await waitFor(() => expect(screen.getAllByTestId('thinking').map((b) => b.dataset.seconds)).toEqual(['3', '7']));
    expect(screen.getAllByTestId('thinking').map((b) => b.querySelector('summary span')!.textContent)).toEqual(['Thought for 3 seconds', 'Thought for 7 seconds']);
  });

  it('a live block counts its seconds, once a second', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    try {
      let now = 0;
      const clock = new ReasoningClock(() => now);
      await renderInApp(
        <ReasoningClockContext.Provider value={clock}>
          <MonaMessage message={twoBlocks('streaming', null)} streaming newest />
        </ReasoningClockContext.Provider>,
      );
      const region = () => screen.getByTestId('thinking').querySelector('summary [aria-live="polite"]')!;
      const label = () => region().querySelector('[aria-hidden="true"]')!.textContent;
      const spoken = () => region().querySelector('.sr-only')!.textContent;
      expect(label()).toBe('Mona is thinking… 0 s');
      expect(spoken()).toBe('Mona is thinking…');
      now = 1_400;
      act(() => vi.advanceTimersByTime(1_000));
      expect(label()).toBe('Mona is thinking… 1 s');
      now = 3_900;
      act(() => vi.advanceTimersByTime(1_000));
      expect(label()).toBe('Mona is thinking… 3 s');
      expect(spoken()).toBe('Mona is thinking…');
      expect([...region().children].filter((c) => !c.hasAttribute('aria-hidden')).map((c) => c.textContent)).toEqual(['Mona is thinking…']);
    } finally {
      vi.useRealTimers();
    }
  });

  it('a streaming part is not live once its message is no longer the streaming one', async () => {
    await renderInApp(
      <ReasoningClockContext.Provider value={new ReasoningClock()}>
        <MonaMessage message={twoBlocks('streaming', null)} streaming={false} newest />
      </ReasoningClockContext.Provider>,
    );
    expect(screen.getByTestId('thinking')).toHaveAttribute('data-live', 'false');
    expect(screen.getByTestId('thinking')).not.toHaveTextContent('Mona is thinking');
  });

  it('on reload, a lone block takes the turn reasoningMs and several blocks show no invented time', async () => {
    const { rerender } = await renderInApp(<MonaMessage message={twoBlocks('done', null, 6_200)} streaming={false} newest />);
    expect(screen.getByTestId('thinking')).toHaveTextContent('Thought for 6 seconds');
    rerender(<MonaMessage message={{ ...twoBlocks('done', 'done', 6_200), id: 'msg_reload' }} streaming={false} newest />);
    expect(screen.getAllByTestId('thinking').map((b) => b.querySelector('summary span')!.textContent)).toEqual(['Reasoning', 'Reasoning']);
  });
});

describe('the thread over the mock api', () => {
  const api = useMockApi();
  const page: PageContext = { route: '/chat', summary: 'Chat page' };

  async function open(props: Partial<Parameters<typeof ConversationThread>[0]> = {}) {
    chatBodies.length = 0;
    const onConversationId = vi.fn();
    const view = await renderInApp(<ConversationThread variant="page" pageContext={() => page} onConversationId={onConversationId} {...props} />);
    return { ...view, onConversationId, box: () => screen.getByRole('textbox', { name: 'Write to Mona…' }) };
  }

  async function say(box: HTMLElement, text: string) {
    await userEvent.type(box, `${text}{Enter}`);
    await waitFor(() => expect(document.querySelector('[data-chat-status="ready"]')).not.toBeNull());
  }

  it('sends only the new text with the page context and locale, and learns the conversation id', async () => {
    const { box, onConversationId } = await open();
    await say(box(), 'How much did we pay last year?');
    expect(await screen.findByText(/You paid these two amounts/)).toBeInTheDocument();
    expect(chatBodies[0]).toEqual({ message: 'How much did we pay last year?', pageContext: page, locale: 'en' });
    const id = onConversationId.mock.calls[0]![0] as string;
    expect(id).toMatch(/^cnv_/);
    await say(box(), "What's due this month?");
    expect(chatBodies[1]).toMatchObject({ conversationId: id });
    expect(document.querySelectorAll('[data-card="deadline"]').length).toBeGreaterThan(0);
  });

  it('Enter sends, Shift+Enter makes a new line, and an empty message never goes', async () => {
    const { box } = await open();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
    await userEvent.type(box(), 'line one{Shift>}{Enter}{/Shift}line two');
    expect(box()).toHaveValue('line one\nline two');
    expect(chatBodies).toHaveLength(0);
  });

  it('a reply in another language inserts a LanguageDivider; Keep English pins replyLanguage on the next turns', async () => {
    const { box } = await open();
    await say(box(), 'How much did we pay last year?');
    await say(box(), 'Pouvez-vous rédiger une réponse pour demander un échéancier ?');
    const divider = await screen.findByTestId('language-divider');
    expect(divider).toHaveTextContent('Continuing in French');
    const french = screen.getAllByTestId('mona-text').at(-1)!;
    expect(french).toHaveAttribute('lang', 'fr');
    await userEvent.click(within(divider).getByRole('button', { name: 'Keep English' }));
    expect(divider).toHaveTextContent('Replies stay in English');
    await say(box(), 'Merci, et pour la suite ?');
    expect(chatBodies.at(-1)).toMatchObject({ replyLanguage: 'en' });
  });

  it('a card action in this conversation reaches Mona in her next turn (C3 §6)', async () => {
    const world = api.world();
    const batchId = world.latestBatch().items[0]!.id;
    const ids = world.reviewList({}).items.filter((d) => d.status === 'review').slice(0, 2).map((d) => d.id);
    world.interviews.debrief(batchId, ids);
    const debrief: PageContext = { route: '/intake', summary: `Intake, batch ${batchId} finished, 2 questions` };
    chatBodies.length = 0;
    await renderInApp(<ConversationThread variant="panel" pageContext={() => debrief} />);
    const box = screen.getByRole('textbox', { name: 'Write to Mona…' });
    await say(box, "Let's go through your questions about this batch.");
    const card = await screen.findByRole('article', { name: 'A question from Mona' });
    await userEvent.click(within(card).getByRole('button', { name: 'For the practice' }));
    await within(card).findByText('You answered: For the practice');
    await say(box, 'Done, what next?');
    const texts = screen.getAllByTestId('mona-text');
    expect(texts.at(-1)).toHaveTextContent(/^Noted: Answered interview question ".*" with "For the practice"/);
  });

  it('"It depends; let me explain" fills the composer and gives the next turn the ids-only summary', async () => {
    const world = api.world();
    const batchId = world.latestBatch().items[0]!.id;
    const iv = world.interviews.debrief(batchId, world.reviewList({}).items.filter((d) => d.status === 'review').slice(0, 2).map((d) => d.id));
    const debrief: PageContext = { route: '/intake', summary: `Intake, batch ${batchId} finished, 2 questions` };
    chatBodies.length = 0;
    await renderInApp(<ConversationThread variant="panel" pageContext={() => debrief} />);
    const box = screen.getByRole('textbox', { name: 'Write to Mona…' });
    await say(box, "Let's go through your questions about this batch.");
    await userEvent.click(await screen.findByRole('button', { name: 'It depends; let me explain' }));
    const q = iv.questions[0]!;
    await waitFor(() => expect(box).toHaveFocus());
    expect(box).toHaveValue(`About “${q.question}”: `);
    await userEvent.type(box, 'only the retirement ones{Enter}');
    await waitFor(() => expect(chatBodies).toHaveLength(2));
    expect(chatBodies[1]).toMatchObject({ message: `About “${q.question}”: only the retirement ones`, pageContext: { route: '/intake', summary: `Interview ${iv.id}, question ${q.id} open` } });
  });

  it('mona_offline shows "Mona is offline" with Try again; another stream error is an inline retry line', async () => {
    const sse = (code: string) =>
      [{ type: 'start', messageId: 'msg_x' }, { type: 'start-step' }, { type: 'error', errorText: code }, { type: 'finish-step' }, { type: 'finish', finishReason: 'error' }]
        .map((c) => `data: ${JSON.stringify(c)}\n\n`)
        .join('') + 'data: [DONE]\n\n';
    let code = 'mona_offline';
    api.server.use(http.post('/api/chat', () => new HttpResponse(sse(code), { headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' } })));
    const { box } = await open();
    await userEvent.type(box(), 'Hello there Mona{Enter}');
    const offline = await screen.findByTestId('chat-offline');
    expect(offline).toHaveTextContent('Mona is offline');
    expect(offline).toHaveTextContent('Mona is offline right now. Try again in a moment.');
    code = 'stream_interrupted';
    await userEvent.click(within(offline).getByRole('button', { name: 'Try again' }));
    const line = await screen.findByTestId('chat-error');
    expect(line).toHaveTextContent('The answer was cut off. Try again.');
    expect(screen.getAllByText('Hello there Mona')).toHaveLength(1);
  });

  /** A /api/chat stand-in whose streams stay open until `finish` is called. */
  function heldStreams(open: 'reasoning' | 'text' | 'tool' = 'reasoning') {
    const enc = new TextEncoder();
    const frame = (c: object) => enc.encode(`data: ${JSON.stringify(c)}\n\n`);
    const held: { finish(): void }[] = [];
    api.server.use(
      http.post('/api/chat', async ({ request }) => {
        chatBodies.push((await request.json()) as Record<string, unknown>);
        const n = chatBodies.length;
        let ctl!: ReadableStreamDefaultController<Uint8Array>;
        const stream = new ReadableStream<Uint8Array>({
          start(c) {
            ctl = c;
            const opened = {
              reasoning: [],
              text: [{ type: 'reasoning-end', id: 'r1' }, { type: 'text-start', id: 't1' }, { type: 'text-delta', id: 't1', delta: 'Partial answer so far' }],
              tool: [{ type: 'reasoning-end', id: 'r1' }, { type: 'tool-input-start', toolCallId: 'call_held', toolName: 'search_documents', dynamic: true }, { type: 'tool-input-available', toolCallId: 'call_held', toolName: 'search_documents', input: {}, dynamic: true }],
            }[open];
            [{ type: 'start', messageId: `msg_held${n}` }, { type: 'start-step' }, { type: 'reasoning-start', id: 'r1' }, { type: 'reasoning-delta', id: 'r1', delta: 'Looking at the archive.' }, ...opened].forEach((c_) => c.enqueue(frame(c_)));
          },
        });
        held.push({
          finish() {
            [...{ reasoning: [{ type: 'reasoning-end', id: 'r1' }, { type: 'text-start', id: 't1' }], text: [], tool: [{ type: 'text-start', id: 't1' }] }[open], { type: 'text-delta', id: 't1', delta: `Reply ${n}.` }, { type: 'text-end', id: 't1' }, { type: 'finish-step' }, { type: 'finish', finishReason: 'stop' }].forEach((c) => ctl.enqueue(frame(c)));
            ctl.enqueue(enc.encode('data: [DONE]\n\n'));
            ctl.close();
          },
        });
        return new HttpResponse(stream, { headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' } });
      }),
    );
    return held;
  }

  it('Stop ends the live thinking and shows Stopped. with a Retry that regenerates the turn', async () => {
    const held = heldStreams();
    const { box } = await open();
    await userEvent.type(box(), 'Hello there Mona{Enter}');
    await waitFor(() => expect(screen.getByTestId('thinking')).toHaveAttribute('data-live', 'true'));
    expect(screen.queryByTestId('chat-stopped')).toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    const line = await screen.findByTestId('chat-stopped');
    expect(line).toHaveTextContent('Stopped.');
    expect(screen.getByTestId('thinking')).toHaveAttribute('data-live', 'false');
    expect(document.querySelector('[data-chat-status="ready"]')).not.toBeNull();
    await userEvent.click(within(line).getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(chatBodies).toHaveLength(2));
    expect(chatBodies[1]).toMatchObject({ message: 'Hello there Mona' });
    expect(screen.queryByTestId('chat-stopped')).toBeNull();
    held[1]!.finish();
    expect(await screen.findByText('Reply 2.')).toBeInTheDocument();
    expect(screen.getAllByText('Hello there Mona')).toHaveLength(1);
    expect(screen.queryByTestId('chat-stopped')).toBeNull();
  });

  it('Stop leaves no blinking caret on a text part that was still open', async () => {
    heldStreams('text');
    const { box } = await open();
    await userEvent.type(box(), 'Hello there Mona{Enter}');
    await waitFor(() => expect(document.querySelector('.mona-caret')).not.toBeNull());
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    await screen.findByTestId('chat-stopped');
    expect(screen.getByText('Partial answer so far')).toBeInTheDocument();
    expect(document.querySelector('.mona-caret')).toBeNull();
  });

  it('Stop shows a tool chip that was still running as interrupted, with no spinner', async () => {
    heldStreams('tool');
    const { box } = await open();
    await userEvent.type(box(), 'Hello there Mona{Enter}');
    await waitFor(() => expect(screen.getByTestId('tool-chip')).toHaveAttribute('data-state', 'running'));
    expect(screen.getByTestId('tool-chip').querySelector('.mona-spin')).not.toBeNull();
    await userEvent.click(screen.getByRole('button', { name: 'Stop' }));
    await screen.findByTestId('chat-stopped');
    const chip = screen.getByTestId('tool-chip');
    expect(chip).toHaveAttribute('data-state', 'interrupted');
    expect(chip).toHaveAttribute('data-live', 'false');
    expect(chip.querySelector('.mona-spin')).toBeNull();
    expect(chip).toHaveTextContent('· interrupted');
  });

  function withOutbox() {
    let post!: (o: ChatOutbox) => void;
    function Harness() {
      const [outbox, setOutbox] = useState<ChatOutbox | null>(null);
      post = setOutbox;
      return <ConversationThread variant="page" pageContext={() => page} outbox={outbox} />;
    }
    return { ui: <Harness />, post: (message: string, id: number) => act(() => post({ id, message, pageContext: page })) };
  }

  it('a queued message waits while Mona is answering, then sends', async () => {
    const held = heldStreams();
    chatBodies.length = 0;
    const harness = withOutbox();
    await renderInApp(harness.ui);
    await userEvent.type(screen.getByRole('textbox', { name: 'Write to Mona…' }), 'First question{Enter}');
    await waitFor(() => expect(document.querySelector('[data-chat-status="streaming"]')).not.toBeNull());
    harness.post('Queued question', 1);
    await new Promise((r) => setTimeout(r, 100));
    expect(chatBodies.map((b) => b.message)).toEqual(['First question']);
    held[0]!.finish();
    await waitFor(() => expect(chatBodies.map((b) => b.message)).toEqual(['First question', 'Queued question']));
    held[1]!.finish();
    expect(await screen.findByText('Reply 2.')).toBeInTheDocument();
  });

  it('a queued message still sends after a failed turn', async () => {
    let failing = true;
    api.server.use(
      http.post('/api/chat', async ({ request }) => {
        if (!failing) return undefined;
        chatBodies.push((await request.json()) as Record<string, unknown>);
        return HttpResponse.json({ error: { code: 'internal', message: 'x' } }, { status: 500 });
      }),
    );
    chatBodies.length = 0;
    const harness = withOutbox();
    await renderInApp(harness.ui);
    await userEvent.type(screen.getByRole('textbox', { name: 'Write to Mona…' }), 'First question{Enter}');
    await screen.findByTestId('chat-error');
    expect(document.querySelector('[data-chat-status="error"]')).not.toBeNull();
    failing = false;
    harness.post('How much did we pay last year?', 1);
    await waitFor(() => expect(chatBodies.map((b) => b.message)).toEqual(['First question', 'How much did we pay last year?']));
    expect(await screen.findByText(/You paid these two amounts/)).toBeInTheDocument();
    expect(chatBodies).toHaveLength(2);
  });

  it('a refused turn (409 turn_in_progress) explains itself', async () => {
    api.server.use(http.post('/api/chat', () => HttpResponse.json({ error: { code: 'turn_in_progress', message: 'busy' } }, { status: 409 })));
    const { box } = await open();
    await userEvent.type(box(), 'Hello there Mona{Enter}');
    expect(await screen.findByTestId('chat-error')).toHaveTextContent('Mona is still answering. Wait for her reply.');
  });

  it('the composer is disabled while Mona is offline', async () => {
    api.server.use(http.get('/api/health', () => HttpResponse.error()));
    const { box } = await open();
    await waitFor(() => expect(box()).toBeDisabled());
    expect(screen.getByTestId('chat-composer')).toHaveAttribute('data-state', 'disabled');
    expect(screen.getByText('Mona is offline. You can write again when she’s back.')).toBeInTheDocument();
  });

  it('a file attached in the composer goes to Intake, shows as an AttachmentChip, and is not sent to Mona', async () => {
    const uploads: number[] = [];
    api.server.use(
      http.post('/api/intake', () => {
        uploads.push(1);
        const item = { id: 'itm_01j9zq3k8e6y4v2m7c5r1t0b9a', originalName: 'Relance_2026-09-22.pdf', sha256: '0'.repeat(64), sizeBytes: 10, outcome: 'accepted', rejectReason: null, documentId: 'doc_01j9zq3k8e6y4v2m7c5r1t0b9z', deleted: false, restoreJournalId: null };
        return HttpResponse.json({ batch: api.world().latestBatch().items[0], items: [item] }, { status: 201 });
      }),
    );
    const { box } = await open();
    await userEvent.upload(screen.getByTestId('composer-file-input'), new File(['%PDF-1.4 x'], 'Relance_2026-09-22.pdf', { type: 'application/pdf' }));
    const chip = await screen.findByTestId('attachment-chip');
    await waitFor(() => expect(chip).toHaveAttribute('data-outcome', 'accepted'));
    expect(chip).toHaveTextContent('Relance_2026-09-22.pdf');
    expect(chip).toHaveTextContent('PDF · 10 B · Added to Intake');
    expect(uploads).toHaveLength(1);
    await say(box(), 'Can you read this one?');
    expect(Object.keys(chatBodies[0]!)).toEqual(['message', 'pageContext', 'locale']);
    expect(within(document.querySelector<HTMLElement>('[data-role="user"]')!).getByTestId('attachment-chip')).toHaveTextContent('Relance_2026-09-22.pdf');
  });

  it('reloading a conversation (C3 §7.2) rebuilds the same messages and cards from the server', async () => {
    const { box, onConversationId } = await open();
    await say(box(), 'How much did we pay last year?');
    const id = onConversationId.mock.calls[0]![0] as string;
    const ids = [...document.querySelectorAll('[data-role="assistant"] [data-card="doc"]')].map((c) => c.getAttribute('data-id'));
    cleanup();
    await act(async () => {
      await renderInApp(<ConversationThread variant="page" conversationId={id} pageContext={() => page} />);
    });
    await screen.findAllByTestId('mona-text');
    expect(screen.getAllByText('How much did we pay last year?')).toHaveLength(1);
    expect([...document.querySelectorAll('[data-card="doc"]')].map((c) => c.getAttribute('data-id'))).toEqual(ids);
    expect(screen.getAllByTestId('tool-chip').map((c) => c.dataset.tool)).toEqual(['search_documents', 'sum_amounts']);
  });
});
