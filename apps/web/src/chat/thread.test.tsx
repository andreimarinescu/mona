import { act, cleanup, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { chatBodies } from '../mocks';
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
