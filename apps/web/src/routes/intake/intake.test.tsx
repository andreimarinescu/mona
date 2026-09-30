import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { BatchCounts, BatchDetail, BatchSummary, DocumentSummary } from '../../data/dto';
import i18n from '../../i18n';
import { AppStateProvider } from '../../state/AppStateProvider';
import { useAppState } from '../../state/context';
import { BatchQuestionsBanner } from './BatchQuestionsBanner';
import { PipelineRow } from './PipelineRow';
import { PipelineStepper } from './PipelineStepper';
import { intakeSummary, showsQuestionsBanner, stepOf, timeLeftMs } from './summary';

const counts = (over: Partial<BatchCounts> = {}): BatchCounts => ({ items: 12, accepted: 12, duplicate: 0, rejected: 0, processing: 0, filed: 0, review: 0, unreadable: 0, failed: 0, ...over });

function batch(over: Partial<BatchSummary> = {}): BatchSummary {
  return {
    id: 'bat_00000000000000000000000001',
    source: 'drop',
    status: 'done',
    title: null,
    visitor: false,
    startedAt: '2026-10-01T10:00:00Z',
    finishedAt: '2026-10-01T10:05:00Z',
    counts: counts(),
    groupId: 'grp_x',
    debrief: { interviewId: 'int_x', status: 'ready', openQuestions: 5 },
    ...over,
  };
}

function docAt(stage: DocumentSummary['pipelineStage'], status: DocumentSummary['status'], over: Partial<DocumentSummary> = {}): DocumentSummary {
  return { id: 'doc_a', title: 't', reasons: [], pipelineStage: stage, status, path: [], entityName: null, badgeUntil: null, ...over } as DocumentSummary;
}

describe('summary line pieces', () => {
  it('folds the counts into "filed, need you, unreadable, already had"', () => {
    expect(intakeSummary(counts({ filed: 4, review: 2, failed: 1, unreadable: 1, rejected: 2, duplicate: 3 }))).toEqual({ filed: 4, needYou: 3, unreadable: 3, alreadyHad: 3 });
  });

  it('places each pipeline stage on its step, with filing and the end states on Result', () => {
    expect(['queued', 'reading', 'ocr', 'classifying', 'filing', 'done', 'failed'].map(stepOf)).toEqual([1, 2, 3, 4, 5, 5, 5]);
  });

  it('estimates the time left from the pace so far, and not before anything is done', () => {
    const start = '2026-10-01T10:00:00Z';
    const at = Date.parse(start) + 60_000;
    expect(timeLeftMs(start, at, 0, 10)).toBeNull();
    expect(timeLeftMs(start, at, 5, 10)).toBe(60_000);
    expect(timeLeftMs(start, at, 10, 10)).toBeNull();
  });
});

describe('PipelineStepper', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('says the step in words: "Step 3 of 5: OCR"', () => {
    render(<PipelineStepper doc={docAt('ocr', 'processing')} />);
    const steps = screen.getByRole('list', { name: 'Step 3 of 5: OCR' });
    expect(steps).toHaveAttribute('data-step', '3');
    expect(within(steps).getAllByRole('listitem').map((li) => li.getAttribute('data-step-state'))).toEqual(['done', 'done', 'active', 'todo', 'todo']);
  });

  it('a settled document sits on Result with every step done', () => {
    render(<PipelineStepper doc={docAt('done', 'filed')} />);
    const steps = screen.getByRole('list', { name: 'Step 5 of 5: Result' });
    expect(within(steps).getAllByRole('listitem').every((li) => li.getAttribute('data-step-state') === 'done')).toBe(true);
  });

  it('is translated', async () => {
    await i18n.changeLanguage('fr');
    render(<PipelineStepper doc={docAt('reading', 'processing')} />);
    expect(screen.getByRole('list', { name: 'Étape 2 sur 5 : Lecture' })).toBeInTheDocument();
  });
});

describe('PipelineRow per-file results (C2 §5.1)', () => {
  const item = (over: Partial<BatchDetail['items'][number]>): BatchDetail['items'][number] => ({
    id: 'itm_1',
    originalName: 'file.pdf',
    sha256: 'a'.repeat(64),
    sizeBytes: 10,
    outcome: 'accepted',
    rejectReason: null,
    documentId: null,
    deleted: false,
    restoreJournalId: null,
    document: null,
    ...over,
  });
  const renderRow = (i: BatchDetail['items'][number], onRestore = vi.fn()) =>
    render(
      <table>
        <tbody>
          <PipelineRow item={i} onRestore={onRestore} busy={false} />
        </tbody>
      </table>,
    );

  it.each([
    ['unsupported_type', 'Only PDF, JPG and PNG files can be read.'],
    ['too_large', 'Too large: files can be up to 25 MB.'],
    ['empty', 'The file is empty.'],
    ['unreadable_file', "The file can't be opened. Send it again or take a clearer photo."],
  ] as const)('a rejected file says why (%s)', (rejectReason, text) => {
    renderRow(item({ outcome: 'rejected', rejectReason }));
    expect(screen.getByText('Not added')).toBeInTheDocument();
    expect(screen.getAllByText(text).length).toBeGreaterThan(0);
  });

  it('a duplicate says it is one already had, and names the earlier document', () => {
    renderRow(item({ outcome: 'duplicate', documentId: 'doc_old', document: docAt('done', 'filed', { title: 'Energie Verte bill' }) }));
    expect(screen.getByText('Already had')).toBeInTheDocument();
    expect(screen.getAllByText('Same as “Energie Verte bill”').length).toBeGreaterThan(0);
  });

  it('a duplicate that is in the trash offers Restore, which undoes the delete entry', async () => {
    const onRestore = vi.fn();
    renderRow(item({ outcome: 'duplicate', deleted: true, restoreJournalId: 4200, documentId: 'doc_old' }), onRestore);
    await userEvent.click(screen.getAllByRole('button', { name: 'Restore' })[0]!);
    expect(onRestore).toHaveBeenCalledWith(4200);
  });

  it('shows "Filed by Mona" only inside the 24 h badge window', () => {
    const { unmount } = renderRow(item({ documentId: 'doc_a', document: docAt('done', 'filed', { badgeUntil: '2026-10-02T06:00:00Z', path: ['Cabinet'] }) }));
    expect(screen.getByText('Filed by Mona')).toBeInTheDocument();
    unmount();
    renderRow(item({ documentId: 'doc_a', document: docAt('done', 'filed', { badgeUntil: null, path: ['Cabinet'] }) }));
    expect(screen.queryByText('Filed by Mona')).not.toBeInTheDocument();
    expect(screen.getByText('Filed')).toBeInTheDocument();
  });
});

describe('BatchQuestionsBanner (A11)', () => {
  function Probe() {
    const { chat } = useAppState();
    return <pre data-testid="outbox">{JSON.stringify({ open: chat.open, outbox: chat.outbox })}</pre>;
  }
  const renderBanner = (b: BatchSummary) =>
    render(
      <AppStateProvider>
        <BatchQuestionsBanner batch={b} />
        <Probe />
      </AppStateProvider>,
    );
  const outbox = () => JSON.parse(screen.getByTestId('outbox').textContent!) as { open: boolean; outbox: { message: string; pageContext: { route: string; summary: string } } | null };

  it('shows only when the debrief is ready with open questions', () => {
    expect(showsQuestionsBanner(batch())).toBe(true);
    expect(showsQuestionsBanner(batch({ debrief: null }))).toBe(false);
    expect(showsQuestionsBanner(batch({ debrief: { interviewId: 'i', status: 'generating', openQuestions: 3 } }))).toBe(false);
    expect(showsQuestionsBanner(batch({ debrief: { interviewId: 'i', status: 'ready', openQuestions: 0 } }))).toBe(false);
  });

  it('says how many questions, and opens the chat with the fixed message and the A11 summary', async () => {
    renderBanner(batch());
    expect(screen.getByText('Mona has 5 questions about this batch')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Answer now' }));
    expect(outbox()).toEqual({
      open: true,
      outbox: { id: 1, message: "Let's go through your questions about this batch.", pageContext: { route: '/intake', summary: 'Intake, batch bat_00000000000000000000000001 finished, 5 questions' } },
    });
  });

  it('the summary says "running" while the batch is still running', async () => {
    renderBanner(batch({ status: 'running', finishedAt: null, debrief: { interviewId: 'i', status: 'ready', openQuestions: 1 } }));
    expect(screen.getByText('Mona has one question about this batch')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Answer now' }));
    expect(outbox().outbox?.pageContext.summary).toBe('Intake, batch bat_00000000000000000000000001 running, 1 questions');
  });

  it('renders nothing otherwise', () => {
    const { container } = renderBanner(batch({ debrief: null }));
    expect(container.querySelector('.mona-banner')).toBeNull();
  });
});
