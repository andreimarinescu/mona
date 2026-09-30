import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { entry } from '../test/fixtures';
import { queryWrapper, useMockApi } from '../test/mockApi';
import { JournalTimeline } from './JournalTimeline';

describe('JournalTimeline', () => {
  const api = useMockApi();

  it('shows live, superseded and undone entries, each in its own state', () => {
    const { Wrapper } = queryWrapper();
    const entries = [
      entry({ id: 12, action: 'move', undoState: 'superseded', undoable: false }),
      entry({ id: 11, action: 'undo', actor: 'user', undoOf: 10 }),
      entry({ id: 10, undoState: 'undone', undoable: false, undoneBy: 11 }),
    ];
    render(<JournalTimeline entries={entries} documents={{ doc_a: { title: 'Nordtel invoice', fileName: 'o.pdf', deleted: false } }} />, { wrapper: Wrapper });
    const rows = screen.getAllByRole('listitem');
    expect(within(rows[0]!).getByRole('button', { name: 'Undo' })).toBeDisabled();
    expect(within(rows[1]!).getByRole('button', { name: 'Undo' })).toBeEnabled();
    expect(within(rows[2]!).getByRole('button', { name: 'Redo' })).toBeEnabled();
    expect(within(rows[2]!).getByText(/^Undone at/)).toBeInTheDocument();
    expect(within(rows[2]!).getByText('Mona filed Nordtel invoice')).toHaveClass('line-through');
    expect(within(rows[0]!).getByText(/Journal #12/)).toBeInTheDocument();
  });

  it('Undo then Redo go through the C2 endpoints and the entry follows', async () => {
    const world = api.world();
    const doc = world.reviewList({}).items[0]!;
    const confirmed = world.confirm(doc.id);
    const journalId = confirmed.journalIds[0]!;
    const { Wrapper, client } = queryWrapper();
    const view = () => world.document(doc.id).journal;
    const { rerender } = render(<JournalTimeline entries={view()} />, { wrapper: Wrapper });
    await userEvent.click(screen.getByRole('button', { name: 'Undo' }));
    await waitFor(() => expect(world.entries.find((e) => e.id === journalId)?.undoneBy).toBeDefined());
    rerender(<JournalTimeline entries={view()} />);
    expect(screen.getByRole('button', { name: 'Redo' })).toBeInTheDocument();
    expect(world.document(doc.id).status).toBe('review');
    await userEvent.click(screen.getByRole('button', { name: 'Redo' }));
    await waitFor(() => expect(world.document(doc.id).status).toBe('filed'));
    client.clear();
  });
});
