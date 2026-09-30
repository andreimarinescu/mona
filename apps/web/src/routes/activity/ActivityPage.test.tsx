import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { queryWrapper, useMockApi } from '../../test/mockApi';
import { ActivityPage } from './ActivityPage';

describe('ActivityPage', () => {
  const api = useMockApi();

  function requests() {
    const seen: URL[] = [];
    api.server.events.on('request:start', ({ request }) => {
      const url = new URL(request.url);
      if (url.pathname === '/api/activity') seen.push(url);
    });
    return seen;
  }

  it('lists batches with an Undo whole batch and single entries with Undo, newest day first', async () => {
    const { Wrapper } = queryWrapper();
    render(<ActivityPage />, { wrapper: Wrapper });
    const batch = (await screen.findByText('Mona processed an intake batch')).closest('li')!;
    expect(within(batch).getByRole('button', { name: 'Undo whole batch' })).toBeEnabled();
    expect(within(batch).getByText('5 changes · 1 moved since')).toBeInTheDocument();
    const days = screen.getAllByRole('heading', { level: 2 });
    expect(days.length).toBeGreaterThan(1);
  });

  it('expands a batch to its entries, with the superseded one disabled', async () => {
    const { Wrapper } = queryWrapper();
    render(<ActivityPage />, { wrapper: Wrapper });
    const batch = (await screen.findByText('Mona processed an intake batch')).closest('li')!;
    expect(within(batch).queryByText('Mona filed Energie Verte bill, September')).not.toBeInTheDocument();
    await userEvent.click(within(batch).getByRole('button', { name: 'Show the changes in this group' }));
    const edf = within(batch).getByText('Mona filed Energie Verte bill, September').closest('li')!;
    expect(edf).toHaveAttribute('data-undo-state', 'superseded');
    expect(within(edf).getByRole('button', { name: 'Undo' })).toBeDisabled();
  });

  it('undoing the whole batch marks it undone and offers Redo', async () => {
    const { Wrapper } = queryWrapper();
    render(<ActivityPage />, { wrapper: Wrapper });
    const batch = (await screen.findByText('Mona processed an intake batch')).closest('li')!;
    const id = batch.getAttribute('data-group-id')!;
    await userEvent.click(within(batch).getByRole('button', { name: 'Undo whole batch' }));
    await waitFor(() => expect(document.querySelector(`li[data-group-id="${id}"]`)).toHaveAttribute('data-undo-state', 'undone'));
    const again = document.querySelector<HTMLElement>(`li[data-group-id="${id}"]`)!;
    expect(within(again).getAllByRole('button', { name: 'Redo' })[0]).toBeEnabled();
  });

  it('asks the API for the actor filter and the search text', async () => {
    const seen = requests();
    const { Wrapper } = queryWrapper();
    render(<ActivityPage />, { wrapper: Wrapper });
    await screen.findByText('Mona processed an intake batch');
    await userEvent.click(screen.getByRole('radio', { name: 'By you' }));
    await waitFor(() => expect(seen.some((u) => u.searchParams.get('actor') === 'user')).toBe(true));
    await userEvent.click(screen.getByRole('radio', { name: 'All' }));
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the journal' }), 'Energie');
    await waitFor(() => expect(seen.some((u) => u.searchParams.get('q') === 'Energie')).toBe(true), { timeout: 2_000 });
    api.server.events.removeAllListeners();
  });

  it('says so when nothing matches', async () => {
    const { Wrapper } = queryWrapper();
    render(<ActivityPage />, { wrapper: Wrapper });
    await screen.findByText('Mona processed an intake batch');
    await userEvent.type(screen.getByRole('searchbox', { name: 'Search the journal' }), 'zzzz');
    expect(await screen.findByText('Nothing here yet', undefined, { timeout: 2_000 })).toBeInTheDocument();
  });
});
