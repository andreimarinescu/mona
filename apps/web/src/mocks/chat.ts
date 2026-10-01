import type { ConversationSummary, Draft, Feed } from '../data/dto';
import type { World } from './world';

type Lang = 'en' | 'fr' | 'ro';
type Chunk = Record<string, unknown>;
type Stored =
  | { type: 'reasoning'; text: string }
  | { type: 'text'; text: string }
  | { type: 'tool'; tool_call_id: string; tool_name: string; completed: boolean }
  | { type: 'data'; kind: 'doc' | 'deadline' | 'interview' | 'rulePreview' | 'draft' | 'export'; id: string };

interface Turn {
  id: string;
  uiMessageId: string;
  userText: string;
  replyLanguage: Lang;
  reasoningMs: number;
  parts: Stored[];
}

interface Conversation {
  id: string;
  title: string;
  lastMessageAt: number;
  turns: Turn[];
}

export interface ChatRequestBody {
  conversationId?: string;
  message: string;
  pageContext: { route: string; summary: string };
  locale: Lang;
  replyLanguage?: Lang;
}

export class ChatError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
  ) {
    super(code);
  }
}

const FR = /\b(combien|rédigez|rédige|pouvez|merci|bonjour|nous|avons|pour|une|est|quoi|réponse|échéancier)\b|[éèêàçùœ]/gi;

function detect(message: string): Lang | null {
  return (message.match(FR) ?? []).length >= 2 ? 'fr' : message.trim().split(/\s+/).length >= 3 ? 'en' : null;
}

function title(message: string): string {
  const text = message.trim().replace(/\s+/g, ' ');
  if (text.length <= 60) return text;
  const cut = text.slice(0, 60);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(' '), 1))}…`;
}

const DEBRIEF = /^Intake, batch (bat_[0-9a-hjkmnp-tv-z]{26}) (?:running|finished), \d+ questions$/;

/** A scripted Mona over the mock world: C3 streams for a few asks, transcripts, and pending notes in her next reply. */
export function createChat(world: World, options: { chunkDelayMs?: number; draftMs?: number } = {}) {
  const chunkDelayMs = options.chunkDelayMs ?? 25;
  const draftMs = options.draftMs ?? 1_200;
  const conversations = new Map<string, Conversation>();
  const drafts = new Map<string, { draft: Draft; readyAt: number }>();

  function draftView(id: string): Draft {
    const entry = drafts.get(id);
    if (!entry) throw new ChatError(404, 'not_found');
    if (entry.draft.status === 'generating' && world.now() >= entry.readyAt) {
      entry.draft = {
        ...entry.draft,
        status: 'ready',
        docxUrl: `/api/drafts/${id}/docx`,
        title: entry.draft.lang === 'fr' ? 'Réponse au centre des cotisations' : 'Reply to the contributions office',
        body:
          entry.draft.lang === 'fr'
            ? 'Objet : demande d’échéancier — cotisations du 3e trimestre 2026 · compte n° [VOTRE N° DE COMPTE]\n\nMadame, Monsieur,\n\nsuite à votre courrier du 22 septembre 2026, je sollicite un échéancier pour les cotisations du 3e trimestre, d’un montant de 1 284,00 €, en trois mensualités de 428,00 €. [MOTIF, SI VOUS LE SOUHAITEZ]\n\nVeuillez agréer, Madame, Monsieur, mes salutations distinguées.'
            : 'Subject: payment schedule — Q3 2026 contributions · account no. [YOUR ACCOUNT NUMBER]\n\nDear Sir or Madam,\n\nFollowing your letter of 22 September 2026, I would like to pay the Q3 contributions of €1,284.00 in three monthly instalments of €428.00. [REASON, IF YOU WISH]\n\nYours faithfully,',
      };
    }
    return entry.draft;
  }

  function startDraft(documentId: string, lang: Lang): Draft {
    const id = world.id('drf');
    const draft: Draft = { id, documentId, lang, status: 'generating', title: null, body: null, docxUrl: null };
    drafts.set(id, { draft, readyAt: world.now() + draftMs });
    return draft;
  }

  function payload(kind: Stored & { type: 'data' }): unknown {
    switch (kind.kind) {
      case 'doc':
        return world.summaryOf(world.docs.get(kind.id)!);
      case 'deadline':
        return world.allDeadlines().find((d) => d.id === kind.id) ?? null;
      case 'interview':
        return world.interviews.get(kind.id);
      case 'rulePreview':
        return world.previewRule(kind.id);
      case 'draft':
        return draftView(kind.id);
      case 'export':
        return world.exports.get(kind.id);
    }
  }

  function script(body: ChatRequestBody, lang: Lang, notes: string[]): { reasoning: string[]; tools: { name: string; cards: (Stored & { type: 'data' })[] }[]; text: string } {
    const m = body.message.toLowerCase();
    const noted = notes.length > 0 ? `Noted: ${notes.join(' ')} ` : '';
    const debrief = DEBRIEF.exec(body.pageContext.summary);
    if (debrief) {
      const batch = world.batchDetail(debrief[1]!).batch;
      const cards = batch.debrief ? [{ type: 'data' as const, kind: 'interview' as const, id: batch.debrief.interviewId }] : [];
      return { reasoning: ['The person opened the debrief for this batch. I will show the existing questions.'], tools: [{ name: 'start_interview', cards }], text: `${noted}Let us go through your questions.` };
    }
    if (/draft|brouillon|rédige|réponse/.test(m)) {
      const doc = [...world.docs.values()].find((d) => d.summary.dueDate && !d.deleted)!;
      const { id } = startDraft(doc.summary.id, lang);
      return {
        reasoning: ['The person wants a reply asking to spread the payment. I start a draft in the letter’s language.'],
        tools: [{ name: 'draft_reply', cards: [{ type: 'data', kind: 'draft', id }] }],
        text: lang === 'fr' ? `${noted}Voici un brouillon. Ce que je n’ai pas trouvé reste entre crochets.` : `${noted}Here is a draft. Anything I couldn’t find is left in brackets.`,
      };
    }
    if (/due|échéance|deadline/.test(m)) {
      const due = world.allDeadlines().filter((d) => d.status === 'open').slice(0, 2);
      return {
        reasoning: ['Checking the deadlines in the next 30 days.'],
        tools: [{ name: 'list_deadlines', cards: due.map((d) => ({ type: 'data' as const, kind: 'deadline' as const, id: d.id })) }],
        text: `${noted}${due.length === 0 ? 'Nothing is due this month.' : `${due.length} payment${due.length === 1 ? ' is' : 's are'} due soon.`}`,
      };
    }
    if (/how much|combien|paid|payé/.test(m)) {
      const docs = [...world.docs.values()].filter((d) => !d.deleted && d.summary.amount && d.summary.status === 'filed').slice(0, 2);
      return {
        reasoning: ['Searching the archive for the payments.', 'Adding up the two amounts I found.'],
        tools: [
          { name: 'search_documents', cards: [] },
          { name: 'sum_amounts', cards: docs.map((d) => ({ type: 'data' as const, kind: 'doc' as const, id: d.summary.id })) },
        ],
        text: lang === 'fr' ? `${noted}Vous avez payé ces deux montants [1] [2].` : `${noted}You paid these two amounts [1] [2].`,
      };
    }
    return { reasoning: ['A general question.'], tools: [], text: lang === 'fr' ? `${noted}Je suis là. Que voulez-vous savoir ?` : `${noted}I’m here. What would you like to know about your documents?` };
  }

  function stream(body: ChatRequestBody, signal: AbortSignal): Response {
    const message = body.message.trim();
    if (!message || message.length > 4_000) throw new ChatError(400, 'invalid_request');
    let conv = body.conversationId ? conversations.get(body.conversationId) : undefined;
    if (body.conversationId && !conv) throw new ChatError(404, 'not_found');
    if (!conv) {
      conv = { id: world.id('cnv'), title: title(message), lastMessageAt: world.now(), turns: [] };
      conversations.set(conv.id, conv);
    }
    const previous = conv.turns.at(-1)?.replyLanguage;
    const replyLanguage: Lang = body.replyLanguage ?? detect(message) ?? previous ?? body.locale;
    const turn: Turn = { id: world.id('trn'), uiMessageId: world.id('msg'), userText: message, replyLanguage, reasoningMs: 0, parts: [] };
    conv.turns.push(turn);
    conv.lastMessageAt = world.now();
    const plan = script(body, replyLanguage, world.consumeNotes(conv.id));
    const chunks: Chunk[] = [
      { type: 'start', messageId: turn.uiMessageId, messageMetadata: { conversationId: conv.id, turnId: turn.id, replyLanguage } },
      { type: 'start-step' },
    ];
    let r = 0;
    const reasoningRun = (text: string) => {
      const id = `r${++r}`;
      chunks.push({ type: 'reasoning-start', id }, ...text.split(/(?<= )/).map((delta) => ({ type: 'reasoning-delta', id, delta })), { type: 'reasoning-end', id });
      turn.parts.push({ type: 'reasoning', text });
    };
    reasoningRun(plan.reasoning[0]!);
    plan.tools.forEach((tool, i) => {
      const toolCallId = `call_${turn.id}_${i}`;
      chunks.push({ type: 'tool-input-available', toolCallId, toolName: tool.name, input: {}, dynamic: true });
      chunks.push({ type: 'tool-output-available', toolCallId, output: { status: 'completed' }, dynamic: true });
      turn.parts.push({ type: 'tool', tool_call_id: toolCallId, tool_name: tool.name, completed: true });
      for (const card of tool.cards) {
        chunks.push({ type: `data-${card.kind}`, id: card.id, data: payload(card) });
        turn.parts.push(card);
      }
      if (plan.reasoning[i + 1]) reasoningRun(plan.reasoning[i + 1]!);
    });
    const textId = 't1';
    chunks.push({ type: 'text-start', id: textId }, ...plan.text.split(/(?<= )/).map((delta) => ({ type: 'text-delta', id: textId, delta })), { type: 'text-end', id: textId });
    turn.parts.push({ type: 'text', text: plan.text });
    turn.reasoningMs = 1_000 * plan.reasoning.length;
    chunks.push({ type: 'finish-step' }, { type: 'finish', finishReason: 'stop', messageMetadata: { reasoningMs: turn.reasoningMs } });

    const encoder = new TextEncoder();
    const body$ = new ReadableStream<Uint8Array>({
      async start(controller) {
        for (const chunk of chunks) {
          if (signal.aborted) break;
          if (chunkDelayMs > 0) await new Promise((resolve) => setTimeout(resolve, chunkDelayMs));
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(chunk)}\n\n`));
        }
        if (!signal.aborted) controller.enqueue(encoder.encode('data: [DONE]\n\n'));
        controller.close();
      },
    });
    return new Response(body$, { headers: { 'content-type': 'text/event-stream', 'x-vercel-ai-ui-message-stream': 'v1' } });
  }

  function list(q: string, cursor: string | null, limit: number): Feed<ConversationSummary> {
    const fold = (s: string) => s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();
    const all = [...conversations.values()]
      .filter((c) => !q || fold(c.title).includes(fold(q)))
      .sort((a, b) => b.lastMessageAt - a.lastMessageAt || (a.id < b.id ? 1 : -1));
    const start = cursor ? all.findIndex((c) => c.id === cursor) + 1 : 0;
    const page = all.slice(start, start + limit);
    return {
      items: page.map((c) => ({ id: c.id, title: c.title, lastMessageAt: new Date(c.lastMessageAt).toISOString(), turnCount: c.turns.length })),
      nextCursor: start + limit < all.length ? page.at(-1)!.id : null,
    };
  }

  function messages(id: string): unknown[] {
    const conv = conversations.get(id);
    if (!conv) throw new ChatError(404, 'not_found');
    return conv.turns.flatMap((turn) => {
      const user = { id: `${turn.id}:u`, role: 'user', parts: [{ type: 'text', text: turn.userText }] };
      if (turn.parts.length === 0) return [user];
      const seen = new Set<string>();
      const parts = turn.parts.flatMap((p): Record<string, unknown>[] => {
        if (p.type === 'reasoning' || p.type === 'text') return [{ type: p.type, text: p.text, state: 'done' }];
        if (p.type === 'tool') return [{ type: 'dynamic-tool', toolName: p.tool_name, toolCallId: p.tool_call_id, state: 'output-available', input: {}, output: { status: 'completed' } }];
        const key = `${p.kind}:${p.id}`;
        if (seen.has(key)) return [];
        seen.add(key);
        const data = payload(p);
        return data ? [{ type: `data-${p.kind}`, id: p.id, data }] : [];
      });
      return [user, { id: turn.uiMessageId, role: 'assistant', metadata: { conversationId: conv.id, turnId: turn.id, replyLanguage: turn.replyLanguage, reasoningMs: turn.reasoningMs }, parts }];
    });
  }

  function docx(id: string, conversationId: string | undefined): { bytes: Uint8Array; name: string } {
    const draft = draftView(id);
    if (draft.status !== 'ready') throw new ChatError(404, 'not_ready');
    world.note(conversationId, 'draft.download', `Downloaded the draft "${draft.title}".`);
    return { bytes: new TextEncoder().encode(`PK mock docx: ${draft.title}`), name: `${draft.title}.docx` };
  }

  return { stream, list, messages, draft: draftView, startDraft, docx, conversations };
}

export type MockChat = ReturnType<typeof createChat>;
