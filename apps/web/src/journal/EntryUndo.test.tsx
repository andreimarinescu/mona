import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { entry } from '../test/fixtures';
import { EntryUndo } from './EntryUndo';
import { badgeLive, undoView } from './entryView';

function setup(props: Partial<Parameters<typeof EntryUndo>[0]> & { entry: ReturnType<typeof entry> }) {
  const onUndo = vi.fn();
  const onRedo = vi.fn();
  render(<EntryUndo onUndo={onUndo} onRedo={onRedo} {...props} />);
  return { onUndo, onRedo };
}

describe('EntryUndo: the three states of C7 §5.2', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('live: an enabled Undo that acts on the entry', async () => {
    const e = entry();
    const { onUndo } = setup({ entry: e });
    await userEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(onUndo).toHaveBeenCalledWith(e);
    expect(screen.queryByRole('button', { name: 'Redo' })).not.toBeInTheDocument();
  });

  it('superseded: Undo is shown disabled with the reason in words', async () => {
    const { onUndo } = setup({ entry: entry({ undoState: 'superseded', undoable: false }) });
    const undo = screen.getByRole('button', { name: 'Undo' });
    expect(undo).toBeDisabled();
    expect(screen.getByText('Moved since')).toBeInTheDocument();
    expect(undo).toHaveAccessibleDescription('Moved since');
    await userEvent.click(undo);
    expect(onUndo).not.toHaveBeenCalled();
  });

  it('undone: an "Undone at" pill and a Redo that acts on the undo entry', async () => {
    const e = entry({ undoState: 'undone', undoable: false, undoneBy: 4240 });
    const { onRedo, onUndo } = setup({ entry: e, undoneAt: '2026-10-01T09:34:00.000Z' });
    expect(screen.getByText(/^Undone at \d\d:\d\d$/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Redo' }));
    expect(onRedo).toHaveBeenCalledWith(e);
    expect(onUndo).not.toHaveBeenCalled();
  });

  it('undone without a known undo entry: the pill, no Redo', () => {
    setup({ entry: entry({ undoState: 'undone', undoable: false }) });
    expect(screen.getByText('Undone')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Redo' })).not.toBeInTheDocument();
  });

  it('not undoable: no control at all', () => {
    setup({ entry: entry({ action: 'doc.update', undoState: 'not_undoable', undoable: false }) });
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('labels follow the language', async () => {
    await i18n.changeLanguage('fr');
    setup({ entry: entry() });
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeInTheDocument();
  });

  it('maps each undoState to a view', () => {
    expect(['undoable', 'undone', 'superseded', 'not_undoable'].map((undoState) => undoView({ undoState: undoState as never }))).toEqual(['live', 'undone', 'superseded', 'none']);
  });
});

describe('badgeLive (C7 §6)', () => {
  const now = Date.parse('2026-10-01T12:00:00Z');
  const hours = (h: number) => new Date(now - h * 3_600_000).toISOString();

  it('is on for Mona\'s live filing inside the window', () => {
    expect(badgeLive(entry({ at: hours(2) }), 24, now)).toBe(true);
    expect(badgeLive(entry({ at: hours(2), action: 'move' }), 24, now)).toBe(true);
  });

  it.each([
    ['past the window', { at: hours(25) }],
    ['your own action', { at: hours(2), actor: 'user' as const }],
    ['undone', { at: hours(2), undoState: 'undone' as const }],
    ['moved since', { at: hours(2), undoState: 'superseded' as const }],
    ['not a filing', { at: hours(2), action: 'doc.update' as const }],
  ])('is off: %s', (_name, over) => {
    expect(badgeLive(entry(over), 24, now)).toBe(false);
  });

  it('respects the badge hours from settings', () => {
    expect(badgeLive(entry({ at: hours(5) }), 4, now)).toBe(false);
    expect(badgeLive(entry({ at: hours(5) }), 6, now)).toBe(true);
  });
});
