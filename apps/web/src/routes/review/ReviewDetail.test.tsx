import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { HttpResponse, http } from 'msw';
import { describe, expect, it, vi } from 'vitest';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { ReviewDetail } from './ReviewDetail';

describe('ReviewDetail', () => {
  const api = useMockApi();

  function setup(title: string, over: Partial<Parameters<typeof ReviewDetail>[0]> = {}) {
    const doc = api.world().reviewList({}).items.find((d) => d.title === title)!;
    const onConfirm = vi.fn(async () => true);
    const onCorrect = vi.fn(async () => true);
    const onSkip = vi.fn();
    const { Wrapper } = queryWrapper();
    render(
      <ReviewDetail documentId={doc.id} position={{ index: 0, total: 6 }} nextId="doc_next" onMove={vi.fn()} scopePending={false} onConfirm={onConfirm} onCorrect={onCorrect} onScopeDone={vi.fn()} onSkip={onSkip} {...over} />,
      { wrapper: Wrapper },
    );
    return { doc, onConfirm, onCorrect, onSkip };
  }

  it('shows Mona\'s sentence, numbered evidence with pages, and the position', async () => {
    setup('Nordtel invoice, September 2026');
    expect(await screen.findByTestId('suggestion-sentence')).toHaveTextContent("Atelier's line");
    const evidence = screen.getByRole('list', { name: 'Evidence from the document' });
    expect(evidence.querySelectorAll('li')).toHaveLength(3);
    expect(evidence.querySelector('li a')).toHaveAttribute('href', expect.stringMatching(/^\/documents\/doc_\w+\?page=1&q=/));
    expect(screen.getByTestId('review-position')).toHaveTextContent('1 of 6');
    expect(screen.getByRole('button', { name: 'Previous document' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Next document' })).toBeEnabled();
  });

  it('draws the confidence meter with the thresholds from settings', async () => {
    api.server.use(http.get('/api/settings', () => HttpResponse.json({ confidenceHigh: 60, confidenceLow: 40, badgeHours: 24 })));
    setup('Nordtel invoice, September 2026');
    const meter = await screen.findByRole('meter');
    await waitFor(() => expect(meter).toHaveAttribute('aria-valuetext', expect.stringContaining('high')));
    expect(meter).toHaveAttribute('aria-valuenow', '64');
  });

  it('Confirm files the suggestion as it is', async () => {
    const { doc, onConfirm, onCorrect } = setup('Nordtel invoice, September 2026');
    await userEvent.click(await screen.findByRole('button', { name: 'Confirm' }));
    expect(onConfirm).toHaveBeenCalledWith(expect.objectContaining({ id: doc.id }));
    expect(onCorrect).not.toHaveBeenCalled();
  });

  it('changing the entity turns Confirm into "Correct and file" and sends only what changed', async () => {
    const { onCorrect, onConfirm } = setup('Nordtel invoice, September 2026');
    const entity = await screen.findByLabelText('Entity');
    await waitFor(() => expect(screen.getByRole('option', { name: 'Cabinet Marchand' })).toBeInTheDocument());
    await userEvent.selectOptions(entity, 'Cabinet Marchand');
    expect(screen.queryByRole('button', { name: 'Confirm' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Correct and file' }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(onCorrect).toHaveBeenCalledWith(expect.anything(), { entityId: api.world().entityList().items[0]!.id });
  });

  it('changing the category resets the subcategory to none', async () => {
    const { onCorrect } = setup('Nordtel invoice, September 2026');
    await waitFor(() => expect(screen.getByRole('option', { name: 'Bank' })).toBeInTheDocument());
    await userEvent.selectOptions(await screen.findByLabelText('Category'), 'Bank');
    await userEvent.click(screen.getByRole('button', { name: 'Correct and file' }));
    expect(onCorrect).toHaveBeenCalledWith(expect.anything(), { categoryId: 'bank', subcategoryKey: null });
  });

  it('a visitor document shows Visitors read-only with its purge note, and a correction keeps it there', async () => {
    const world = api.world();
    const base = world.reviewList({}).items.find((d) => d.title === 'Nordtel invoice, September 2026')!;
    const detail = world.document(base.id);
    const visitors = world.entityList().visitorsEntityId!;
    api.server.use(http.get(`/api/documents/${base.id}`, () => HttpResponse.json({ ...detail, entityId: visitors, suggestion: { ...detail.suggestion!, entityId: visitors } })));
    const { onCorrect } = setup('Nordtel invoice, September 2026');
    const field = await screen.findByTestId('visitors-entity');
    await waitFor(() => expect(field).toHaveValue('Visitors'));
    expect(field).toHaveAttribute('readonly');
    expect(await screen.findByText("A visitor's document: deleted after 24 hours, with everything Mona derived from it.")).toBeInTheDocument();
    expect(screen.queryByRole('combobox', { name: 'Entity' })).not.toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole('option', { name: 'Bank' })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Category'), 'Bank');
    await userEvent.click(screen.getByRole('button', { name: 'Correct and file' }));
    expect(onCorrect).toHaveBeenCalledWith(expect.anything(), { categoryId: 'bank', subcategoryKey: null });
  });

  it('a document with no entity cannot be confirmed until one is chosen', async () => {
    setup('Delivery note, Laboratoire du Val');
    expect(await screen.findByRole('button', { name: 'Confirm' })).toBeDisabled();
    await waitFor(() => expect(screen.getByRole('option', { name: 'SCI Les Tilleuls' })).toBeInTheDocument());
    await userEvent.selectOptions(screen.getByLabelText('Entity'), 'SCI Les Tilleuls');
    expect(screen.getByRole('button', { name: 'Correct and file' })).toBeEnabled();
  });

  it('an unreadable document has no meter and cannot be confirmed; Mark unreadable is not offered yet', async () => {
    setup('IMG_2231.jpg');
    expect(await screen.findByTestId('suggestion-sentence')).toHaveTextContent("I can't read this document.");
    expect(screen.queryByRole('meter')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Mark unreadable' })).toBeDisabled();
  });

  it('Enter confirms, unless focus is on a control that uses Enter itself', async () => {
    const { onConfirm } = setup('Nordtel invoice, September 2026');
    await screen.findByRole('button', { name: 'Confirm' });
    await userEvent.keyboard('{Enter}');
    expect(onConfirm).toHaveBeenCalledTimes(1);
    screen.getByRole('button', { name: 'Skip' }).focus();
    await userEvent.keyboard('{Enter}');
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('Skip goes on without filing', async () => {
    const { onSkip, onConfirm } = setup('Nordtel invoice, September 2026');
    await userEvent.click(await screen.findByRole('button', { name: 'Skip' }));
    expect(onSkip).toHaveBeenCalled();
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
