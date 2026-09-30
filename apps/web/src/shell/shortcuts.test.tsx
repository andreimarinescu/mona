import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { AppStateProvider } from '../state/AppStateProvider';
import { useAppState } from '../state/context';
import { useShellShortcuts } from './shortcuts';

function Harness({ home = false, entry = false }: { home?: boolean; entry?: boolean }) {
  useShellShortcuts(home);
  const { chat, openChat, registerAskButton, registerChatEntry } = useAppState();
  return (
    <>
      <button ref={registerAskButton} onClick={(e) => openChat({ opener: e.currentTarget })}>
        Ask Mona
      </button>
      <button>Other</button>
      <input aria-label="Field" />
      {entry ? <input aria-label="Home entry" ref={registerChatEntry} /> : null}
      <div role="menu">
        <button role="menuitem">Item</button>
      </div>
      <output data-testid="chat">{chat.open ? 'open' : 'closed'}</output>
    </>
  );
}

function setup(props: { home?: boolean; entry?: boolean } = {}) {
  render(
    <AppStateProvider>
      <Harness {...props} />
    </AppStateProvider>,
  );
  return userEvent.setup();
}

describe('shell shortcuts', () => {
  it('"/" opens the panel and Esc closes it, returning focus to the element focused before', async () => {
    const user = setup();
    await user.click(screen.getByRole('button', { name: 'Other' }));
    await user.keyboard('/');
    expect(screen.getByTestId('chat')).toHaveTextContent('open');
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('chat')).toHaveTextContent('closed');
    expect(screen.getByRole('button', { name: 'Other' })).toHaveFocus();
  });

  it('Esc returns focus to the Ask Mona button that opened the panel', async () => {
    const user = setup();
    await user.click(screen.getByRole('button', { name: 'Ask Mona' }));
    expect(screen.getByTestId('chat')).toHaveTextContent('open');
    await user.click(screen.getByRole('button', { name: 'Other' }));
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Ask Mona' })).toHaveFocus();
  });

  it('falls back to the Ask Mona button when nothing was focused', async () => {
    const user = setup();
    await user.keyboard('/');
    await user.keyboard('{Escape}');
    expect(screen.getByRole('button', { name: 'Ask Mona' })).toHaveFocus();
  });

  it('does nothing in a text field', async () => {
    const user = setup();
    await user.click(screen.getByRole('textbox', { name: 'Field' }));
    await user.keyboard('a/b');
    expect(screen.getByTestId('chat')).toHaveTextContent('closed');
    expect(screen.getByRole('textbox', { name: 'Field' })).toHaveValue('a/b');
  });

  it('focuses the Home chat entry instead of opening the panel on Home', async () => {
    const user = setup({ home: true, entry: true });
    await user.keyboard('/');
    expect(screen.getByRole('textbox', { name: 'Home entry' })).toHaveFocus();
    expect(screen.getByTestId('chat')).toHaveTextContent('closed');
  });

  it('opens the panel off Home even when a Home entry is registered', async () => {
    const user = setup({ home: false, entry: true });
    await user.keyboard('/');
    expect(screen.getByTestId('chat')).toHaveTextContent('open');
  });

  it('leaves Esc to an open menu', async () => {
    const user = setup();
    await user.keyboard('/');
    await user.click(screen.getByRole('menuitem', { name: 'Item' }));
    await user.keyboard('{Escape}');
    expect(screen.getByTestId('chat')).toHaveTextContent('open');
  });
});
