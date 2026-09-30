import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { toasts } from '../../toast/store';
import { CorrectionScopePrompt } from './CorrectionScopePrompt';

describe('CorrectionScopePrompt: scope, then preview, then apply', () => {
  const api = useMockApi();

  function orangeCorrected() {
    const world = api.world();
    const orange = world.reviewList({}).items.find((d) => d.title.startsWith('Nordtel'))!;
    const cabinet = world.entityList().items[0]!;
    world.correct(orange.id, { entityId: cabinet.id });
    return { world, orange, cabinet };
  }

  it('offers the two scopes and calls nothing until one is chosen', async () => {
    const { orange, world } = orangeCorrected();
    const { Wrapper } = queryWrapper();
    render(<CorrectionScopePrompt documentId={orange.id} onDone={vi.fn()} />, { wrapper: Wrapper });
    expect(screen.getByRole('radio', { name: /Just this one/ })).not.toBeChecked();
    expect(screen.getByRole('radio', { name: /Every document like this/ })).not.toBeChecked();
    expect(screen.queryByTestId('rule-preview')).not.toBeInTheDocument();
    expect(world.entries.some((e) => e.action === 'rule.change')).toBe(false);
  });

  it('"Just this one" asks for no rule and finishes on Done', async () => {
    const { orange, world } = orangeCorrected();
    const onDone = vi.fn();
    const { Wrapper } = queryWrapper();
    render(<CorrectionScopePrompt documentId={orange.id} onDone={onDone} />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole('radio', { name: /Just this one/ }));
    expect(screen.queryByTestId('rule-preview')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Done' }));
    expect(onDone).toHaveBeenCalledTimes(1);
    expect(world.entries.some((e) => e.action === 'rule.change')).toBe(false);
  });

  it('"Every document like this" shows the preview without moving anything, then Apply moves them and finishes', async () => {
    const { orange, world } = orangeCorrected();
    const onDone = vi.fn();
    const { Wrapper } = queryWrapper();
    render(<CorrectionScopePrompt documentId={orange.id} onDone={onDone} />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole('radio', { name: /Every document like this/ }));

    const preview = await screen.findByTestId('rule-preview');
    expect(within(preview).getByText('3 move · 1 stay')).toBeInTheDocument();
    expect(within(preview).getAllByTestId('path-diff')).toHaveLength(3);
    const filedBefore = [...world.docs.values()].filter((d) => d.summary.counterparty === 'Nordtel').map((d) => d.summary.path.join('/'));
    expect(new Set(filedBefore).size).toBe(2);
    expect(onDone).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole('button', { name: 'Apply' }));
    await waitFor(() => expect(onDone).toHaveBeenCalledTimes(1));
    const after = [...world.docs.values()].filter((d) => d.summary.counterparty === 'Nordtel').map((d) => d.summary.path.join('/'));
    expect(new Set(after).size).toBe(1);
    expect(world.entries.filter((e) => e.action === 'move' && e.groupId !== null)).toHaveLength(3);
    const toast = toasts.getSnapshot().find((t) => t.message === 'review.toast.ruleApplied');
    expect(toast).toMatchObject({ count: 3 });
    expect(toast?.undo).toHaveLength(1);
  });

  it('the preview marks only the changed path segments', async () => {
    const { orange } = orangeCorrected();
    const { Wrapper } = queryWrapper();
    render(<CorrectionScopePrompt documentId={orange.id} onDone={vi.fn()} />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole('radio', { name: /Every document like this/ }));
    const diff = (await screen.findAllByTestId('path-diff'))[0]!;
    const removed = [...diff.querySelectorAll('del')].map((n) => n.textContent);
    const added = [...diff.querySelectorAll('ins')].map((n) => n.textContent);
    expect(removed).toEqual(['Atelier Numérique', '2026 Atelier Numérique']);
    expect(added).toEqual(['Cabinet Marchand', '2026 Cabinet Marchand']);
  });

  it('a document with no counterparty gets a plain explanation instead of a rule', async () => {
    const world = api.world();
    const img = world.reviewList({}).items.find((d) => d.title === 'IMG_2231.jpg')!;
    world.correct(img.id, { entityId: world.entityList().items[0]!.id, categoryId: 'tax' });
    const { Wrapper } = queryWrapper();
    render(<CorrectionScopePrompt documentId={img.id} onDone={vi.fn()} />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole('radio', { name: /Every document like this/ }));
    expect(await screen.findByText("This document has no counterparty, so I can't write a rule for it.")).toBeInTheDocument();
    expect(screen.queryByTestId('rule-preview')).not.toBeInTheDocument();
  });
});
