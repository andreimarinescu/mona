import { act, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { APPLIED_PREVIEW, DEADLINE, DOC, DRAFT, EXPORT, INTERVIEW, cardsMessage } from '../../test/chatFixtures';
import { useMockApi } from '../../test/mockApi';
import { renderInApp } from '../../test/renderInApp';
import { toasts } from '../../toast/store';
import { MonaMessage } from '../Messages';
import { DeadlineCard } from './DeadlineCard';
import { DraftCard } from './DraftCard';
import { InterviewCard } from './InterviewCard';

const card = (kind: string) => document.querySelector<HTMLElement>(`[data-card="${kind}"]`)!;

describe('each card renders from its C3 part (C1 DTOs)', () => {
  useMockApi();

  async function renderCards(over?: Parameters<typeof cardsMessage>[0]) {
    await renderInApp(<MonaMessage message={cardsMessage(over)} streaming={false} newest />);
    await waitFor(() => expect(card('doc')).not.toBeNull());
  }

  it('DocCard: title, entity, category, date, amount, path, confidence, status and Open', async () => {
    await renderCards();
    const doc = within(card('doc'));
    expect(card('doc').dataset.id).toBe(DOC.id);
    expect(doc.getByText('Personnel')).toBeInTheDocument();
    expect(await doc.findByText('Insurance')).toBeInTheDocument();
    expect(doc.getByText('6 Jan 2026')).toBeInTheDocument();
    expect(doc.getByText('€955.20')).toBeInTheDocument();
    expect(doc.getByText(/Personnel \/ 2026 Personnel \/ Assurances \/ 2026-01-06_Previa_Avis\.pdf/)).toBeInTheDocument();
    expect(doc.getByRole('meter', { name: 'Confidence' })).toHaveAttribute('aria-valuenow', '71');
    expect(doc.getByText('Filed')).toBeInTheDocument();
    expect(doc.getByRole('link', { name: `Open: ${DOC.title}` })).toHaveAttribute('href', `/documents/${DOC.id}`);
  });

  it('DeadlineCard: date tile, label, entity and paying account, amount, due badge, Open letter, Remind me', async () => {
    await renderCards();
    const d = within(card('deadline'));
    expect(d.getByTestId('date-tile')).toHaveAttribute('data-urgent', 'true');
    expect(d.getByText('Contributions, third quarter')).toBeInTheDocument();
    expect(d.getByText('Cabinet Marchand · debit from Main account •• 4471')).toBeInTheDocument();
    expect(d.getByText('€1,284.00')).toBeInTheDocument();
    expect(d.getByText('Due in 2 days')).toBeInTheDocument();
    expect(d.getByRole('link', { name: 'Open letter' })).toHaveAttribute('href', `/documents/${DOC.id}`);
    expect(d.getByRole('button', { name: /^Remind me on/ })).toBeEnabled();
  });

  it('InterviewCard: the question in the voice font, affects N, evidence that opens the viewer, three answers with the suggested one primary', async () => {
    await renderCards();
    const iv = within(card('interview'));
    expect(iv.getByText(INTERVIEW.questions[0]!.question)).toHaveClass('m-0');
    expect(iv.getByText('Affects 4 documents')).toBeInTheDocument();
    const links = iv.getAllByTestId('evidence-snippet');
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveAttribute('href', `/documents/${DOC.id}?page=1&q=Madelin`);
    expect(links[1]).toHaveAttribute('href', `/documents/${DOC.id}?page=2`);
    expect(links[0]!.querySelector('mark')).toHaveTextContent('Madelin');
    expect(links[0]!.querySelector('[lang="fr"]')).not.toBeNull();
    const options = iv.getAllByRole('button').filter((b) => b.hasAttribute('data-option'));
    expect(options.map((b) => b.textContent)).toEqual(['For the practice', 'Personal', 'Ask me each time']);
    expect(options.map((b) => b.getAttribute('aria-keyshortcuts'))).toEqual(['1', '2', '3']);
    expect(options[0]).toHaveClass('mona-btn--primary');
    expect(options[1]).toHaveClass('mona-btn--secondary');
    expect(options[0]).toHaveAccessibleDescription('Suggested');
    expect(iv.getByRole('button', { name: 'It depends; let me explain' })).toBeInTheDocument();
    expect(iv.getByRole('button', { name: 'Skip this question' })).toBeInTheDocument();
  });

  it('RulePreviewCard in its applied state (C1 §11.5): the counts it showed before, no Apply, Adjust', async () => {
    await renderCards();
    const preview = card('rulePreview');
    expect(preview).toHaveAttribute('data-applied', 'true');
    const p = within(preview);
    expect(p.getByText('4 move · 2 stay')).toBeInTheDocument();
    expect(p.getByRole('status')).toHaveTextContent('Applied: 4 documents moved');
    expect(p.queryByRole('button', { name: 'Apply' })).toBeNull();
    expect(p.getAllByTestId('path-diff')).toHaveLength(2);
    expect(p.getByRole('link', { name: 'Adjust' })).toHaveAttribute('href', `/rules/${APPLIED_PREVIEW.rule.id}`);
  });

  it('DraftCard: body in its language with [BRACKETS] marked, Copy and Download, the promise, and never Send', async () => {
    await renderCards();
    const d = within(card('draft'));
    expect(d.getByText('Réponse au centre des cotisations')).toBeInTheDocument();
    expect(d.getByText('Draft · not sent')).toBeInTheDocument();
    expect(d.getByTestId('draft-body')).toHaveAttribute('lang', 'fr');
    expect(d.getByText('[VOTRE N° DE COMPTE]').tagName).toBe('MARK');
    expect(d.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    expect(d.getByRole('button', { name: 'Download .docx' })).toBeInTheDocument();
    expect(d.getByText(/Mona never sends anything/)).toBeInTheDocument();
    expect(d.queryByRole('button', { name: /send/i })).toBeNull();
  });

  it('ExportCard: the ready pack with its two downloads', async () => {
    await renderCards();
    const e = within(card('export'));
    expect(e.getByText('12 documents from Cabinet Marchand, fiscal year 2025.')).toBeInTheDocument();
    expect(e.getByRole('link', { name: 'Download the zip' })).toHaveAttribute('href', EXPORT.zipUrl);
    expect(e.getByRole('link', { name: 'Download the CSV index' })).toHaveAttribute('href', EXPORT.csvUrl);
  });

  it('a [n] marker becomes a Citation of the n-th document card, listed under Sources', async () => {
    await renderCards();
    expect(screen.getByRole('button', { name: `Source 1: ${DOC.title}` })).toBeInTheDocument();
    expect(within(screen.getByRole('list', { name: 'Sources' })).getByRole('link', { name: DOC.title })).toBeInTheDocument();
  });

  it('a single reasoning block reloads with the turn reasoningMs; the tool chip shows its done label', async () => {
    await renderCards();
    expect(screen.getByTestId('thinking')).toHaveTextContent('Thought for 2 seconds');
    expect(screen.getByTestId('tool-chip')).toHaveTextContent('Searched the archive');
  });
});

describe('InterviewCard actions (C2 §11, §14)', () => {
  const api = useMockApi();
  const CNV = 'cnv_01j9zq3k8e6y4v2m7c5r1t0b9a';

  function debrief() {
    const world = api.world();
    const ids = world.reviewList({}).items.filter((d) => d.status === 'review').slice(0, 3).map((d) => d.id);
    return { world, interview: world.interviews.debrief('bat_01j9zq3k8e6y4v2m7c5r1t0b9a', ids) };
  }

  it('keys 1/2/3 pick the answers in order, with the conversation for the note', async () => {
    const { world, interview } = debrief();
    await renderInApp(<InterviewCard interview={interview} />, { conversationId: CNV });
    const group = screen.getByRole('group', { name: interview.questions[0]!.question });
    group.focus();
    await userEvent.keyboard('2');
    expect(await screen.findByText('You answered: For the practice')).toBeInTheDocument();
    expect(world.interviews.get(interview.id).questions[0]!.answer?.optionId).toBe('o2');
    expect(world.notes).toEqual([expect.objectContaining({ conversationId: CNV, kind: 'interview.answer', text: expect.stringContaining('with "For the practice"') })]);
  });

  it('keys do nothing outside the card, and 4 is not an answer', async () => {
    const { world, interview } = debrief();
    await renderInApp(<InterviewCard interview={interview} />);
    await userEvent.keyboard('1');
    screen.getByRole('group', { name: interview.questions[0]!.question }).focus();
    await userEvent.keyboard('4');
    expect(world.interviews.get(interview.id).questions[0]!.status).toBe('open');
  });

  it('answer 1 drafts two rules: two previews and Apply all; Apply all applies both; the toast undo sends both back to draft', async () => {
    const { world, interview } = debrief();
    await renderInApp(<InterviewCard interview={interview} />, { conversationId: CNV });
    await userEvent.click(screen.getByRole('button', { name: 'Personal: split retirement and life insurance' }));
    await waitFor(() => expect(document.querySelectorAll('[data-card="rulePreview"]')).toHaveLength(2));
    const previews = [...document.querySelectorAll<HTMLElement>('[data-card="rulePreview"]')];
    expect(previews.map((p) => p.dataset.applied)).toEqual(['false', 'false']);
    expect(within(previews[0]!).getByText('2 move · 0 stay')).toBeInTheDocument();
    expect(within(previews[1]!).getByText('1 move · 0 stay')).toBeInTheDocument();

    await userEvent.click(screen.getByRole('button', { name: 'Apply all (2 rules)' }));
    await waitFor(() => expect(previews.map((p) => p.dataset.applied)).toEqual(['true', 'true']));
    expect(screen.getByText('All 2 rules applied')).toBeInTheDocument();
    const ids = interview.questions[0]!.affects;
    expect(ids.map((id) => world.docs.get(id)!.summary.status)).toEqual(['filed', 'filed', 'filed']);
    expect(world.notes.filter((n) => n.kind === 'rule.apply')).toHaveLength(2);
    const toast = toasts.getSnapshot().find((t) => t.message === 'interview.toast.appliedAll')!;
    expect(toast.count).toBe(3);

    await act(async () => toasts.undo(toast.id));
    await waitFor(() => expect(previews.map((p) => p.dataset.applied)).toEqual(['false', 'false']));
    expect(previews.map((p) => p.dataset.state)).toEqual(['draft', 'draft']);
    expect(ids.map((id) => world.docs.get(id)!.summary.status)).toEqual(['review', 'review', 'review']);
    expect(world.notes.filter((n) => n.kind === 'undo' && n.conversationId === CNV)).toHaveLength(2);
    expect(screen.getByRole('button', { name: 'Apply all (2 rules)' })).toBeEnabled();
  });

  it('Skip moves to the next question, and the interview is done when none is left', async () => {
    const { world, interview } = debrief();
    await renderInApp(<InterviewCard interview={interview} />);
    expect(screen.getByText('Question 1 of 2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Skip this question' }));
    expect(await screen.findByText('You skipped this question.')).toBeInTheDocument();
    expect(screen.getByText('Question 2 of 2')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Skip this question' }));
    expect(await screen.findByText('That’s all my questions. Thank you.')).toBeInTheDocument();
    expect(world.interviews.get(interview.id).status).toBe('done');
  });

  it('"It depends; let me explain" prefills the composer with the question quoted and an ids-only summary (C6 §5.3)', async () => {
    const { interview } = debrief();
    const prefill = vi.fn();
    await renderInApp(<InterviewCard interview={interview} />, { prefill });
    await userEvent.click(screen.getByRole('button', { name: 'It depends; let me explain' }));
    const q = interview.questions[0]!;
    expect(prefill).toHaveBeenCalledWith(`About “${q.question}”: `, `Interview ${interview.id}, question ${q.id} open`);
  });

  it('a generating card polls GET /api/interviews/{id} and turns into the question (C2 §1.5)', async () => {
    const { interview } = debrief();
    const gets: string[] = [];
    api.server.events.on('request:start', ({ request }) => {
      if (request.method === 'GET' && request.url.includes('/api/interviews/')) gets.push(request.url);
    });
    await renderInApp(<InterviewCard interview={{ ...interview, status: 'generating', questions: [], openQuestions: 0 }} />);
    expect(screen.getByText('Mona is preparing her questions…')).toBeInTheDocument();
    expect(await screen.findByText(interview.questions[0]!.question, {}, { timeout: 4_000 })).toBeInTheDocument();
    expect(gets.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText('Mona is preparing her questions…')).toBeNull();
  });

  it('a refused answer shows the error and refreshes the card', async () => {
    const { interview } = debrief();
    api.server.use(http.post('/api/interviews/:id/questions/:qid/answer', () => HttpResponse.json({ error: { code: 'already_answered', message: 'x' } }, { status: 409 })));
    await renderInApp(<InterviewCard interview={interview} />);
    await userEvent.click(screen.getByRole('button', { name: 'For the practice' }));
    await waitFor(() => expect(toasts.getSnapshot().some((t) => t.message === 'errors.already_answered')).toBe(true));
  });
});

describe('DeadlineCard and DraftCard actions', () => {
  const api = useMockApi();
  const CNV = 'cnv_01j9zq3k8e6y4v2m7c5r1t0b9a';

  it('Remind me posts C2 §10 with the conversation, then shows the reminder', async () => {
    const world = api.world();
    const deadline = world.allDeadlines()[0]!;
    await renderInApp(<DeadlineCard deadline={deadline} />, { conversationId: CNV });
    await userEvent.click(screen.getByRole('button', { name: /^Remind me on/ }));
    expect(await screen.findByTestId('reminder-set')).toHaveTextContent(/^Reminder set for/);
    expect(world.notes).toEqual([expect.objectContaining({ conversationId: CNV, kind: 'reminder.add' })]);
  });

  it('Mark as done patches the deadline', async () => {
    const world = api.world();
    const deadline = world.allDeadlines()[0]!;
    await renderInApp(<DeadlineCard deadline={deadline} />);
    await userEvent.click(screen.getByRole('button', { name: 'Mark as done' }));
    expect(await screen.findByText('Marked as done')).toBeInTheDocument();
    expect(world.allDeadlines().find((d) => d.id === deadline.id)!.status).toBe('done');
  });

  it('a generating draft polls until ready; Download fetches the .docx with the conversation (draft.download note); Copy copies the body', async () => {
    const world = api.world();
    const draft = api.chat().startDraft([...world.docs.values()][0]!.summary.id, 'fr');
    const created = vi.fn(() => 'blob:docx');
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: created, revokeObjectURL: vi.fn() }));
    const writeText = vi.fn(async () => undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    await renderInApp(<DraftCard draft={draft} />, { conversationId: CNV });
    expect(screen.getByText('Mona is writing the draft…')).toBeInTheDocument();
    const body = await screen.findByTestId('draft-body', {}, { timeout: 4_000 });
    await userEvent.click(screen.getByRole('button', { name: 'Copy' }));
    expect(writeText).toHaveBeenCalledWith(api.chat().draft(draft.id).body);
    expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Download .docx' }));
    await waitFor(() => expect(created).toHaveBeenCalledTimes(1));
    expect(world.notes).toEqual([expect.objectContaining({ conversationId: CNV, kind: 'draft.download' })]);
    expect(body).toHaveAttribute('lang', 'fr');
  });

  it('a failed draft says so and offers nothing to send', async () => {
    await renderInApp(<DraftCard draft={{ ...DRAFT, status: 'failed', body: null }} />);
    expect(screen.getByText(/I couldn’t write this draft/)).toBeInTheDocument();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('a deadline already past is overdue, not urgent-due', async () => {
    await renderInApp(<DeadlineCard deadline={{ ...DEADLINE, daysLeft: -3 }} />);
    expect(screen.getByText('Overdue by 3 days')).toBeInTheDocument();
  });
});
