import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { AppStateProvider } from '../state/AppStateProvider';
import { createToastStore } from '../toast/store';
import { ToastRegion } from './ToastRegion';

function setup() {
  const store = createToastStore();
  render(
    <AppStateProvider>
      <ToastRegion store={store} />
    </AppStateProvider>,
  );
  return store;
}

describe('ToastRegion', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('shows one grouped toast, past tense, with an Undo that runs every grouped undo', async () => {
    const store = setup();
    const undo = vi.fn();
    act(() => {
      for (let i = 0; i < 12; i++) store.push({ key: 'filed', message: 'toast.filed', from: 'mona', undo });
    });
    expect(screen.getAllByRole('status')).toHaveLength(1);
    expect(screen.getByText('Filed 12 documents')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Undo' }));
    expect(undo).toHaveBeenCalledTimes(12);
    expect(screen.queryByText('Filed 12 documents')).not.toBeInTheDocument();
  });

  it('renders at most three toasts', () => {
    const store = setup();
    act(() => {
      for (const key of ['a', 'b', 'c', 'd']) store.push({ key, message: 'toast.failed' });
    });
    expect(screen.getAllByRole('status')).toHaveLength(3);
  });

  it('gives a danger toast role="alert", no Undo, and a close button that dismisses it', async () => {
    const store = setup();
    act(() => void store.push({ key: 'err', message: 'toast.failed', tone: 'danger' }));
    expect(screen.getByRole('alert')).toHaveTextContent('Something went wrong');
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Close' }));
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it.each([
    ['fr', 1, '1 document classé'],
    ['fr', 12, '12 documents classés'],
    ['fr', 1_000_000, '1 000 000 de documents classés'],
    ['ro', 1, '1 document arhivat'],
    ['ro', 3, '3 documente arhivate'],
    ['ro', 20, '20 de documente arhivate'],
  ] as const)('%s, %i -> %s (CLDR plural forms, numbers through format)', async (lng, count, text) => {
    await i18n.changeLanguage(lng);
    const store = setup();
    act(() => void store.push({ key: 'filed', message: 'toast.filed', count }));
    expect(screen.getByText((content) => content.replace(/\u00a0/g, ' ') === text)).toBeInTheDocument();
  });
});
