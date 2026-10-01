import { RouterProvider, createMemoryHistory, createRootRoute, createRoute, createRouter } from '@tanstack/react-router';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it } from 'vitest';
import i18n from '../i18n';
import { MOCK_PASSWORD } from '../mocks/account';
import { queryWrapper, useMockApi } from '../test/mockApi';
import { Unlock } from './Unlock';

describe('Unlock', () => {
  const api = useMockApi({ locked: true, locale: 'fr' });
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  async function open(url: string) {
    const { Wrapper } = queryWrapper();
    const root = createRootRoute();
    const unlock = createRoute({ getParentRoute: () => root, path: '/unlock', validateSearch: (s: Record<string, unknown>): { next?: string } => (typeof s.next === 'string' ? { next: s.next } : {}), component: () => <Wrapper><Unlock /></Wrapper> });
    const rest = createRoute({ getParentRoute: () => root, path: '$', component: () => <p>landed</p> });
    const router = createRouter({ routeTree: root.addChildren([unlock, rest]), history: createMemoryHistory({ initialEntries: [url] }) });
    await router.load();
    render(<RouterProvider router={router} />);
    return router;
  }

  it('renders in the profile language, with the reset hint and no recovery-key line', async () => {
    await open('/unlock');
    expect(await screen.findByRole('heading', { level: 1, name: 'Bon retour' })).toBeInTheDocument();
    expect(screen.getByText(/mona profile set-password/)).toBeInTheDocument();
    expect(screen.queryByText(/recovery|récupération/i)).toBeNull();
    expect(document.documentElement.lang).toBe('fr');
  });

  it('a wrong password is an inline error, and the field is cleared', async () => {
    await open('/unlock');
    const field = await screen.findByLabelText('Mot de passe');
    await userEvent.type(field, 'wrong');
    await userEvent.click(screen.getByRole('button', { name: 'Déverrouiller' }));
    expect(await screen.findByText('Ce mot de passe n’est pas le bon.')).toBeInTheDocument();
    expect(field).toHaveValue('');
    expect(api.world().account.isLocked()).toBe(true);
  });

  it('the right password unlocks and goes to next', async () => {
    const router = await open('/unlock?next=%2Frules%2Frul_a');
    await userEvent.type(await screen.findByLabelText('Mot de passe'), MOCK_PASSWORD);
    await userEvent.click(screen.getByRole('button', { name: 'Déverrouiller' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/rules/rul_a'));
    expect(api.world().account.isLocked()).toBe(false);
  });

  it('ignores a next that leaves the app', async () => {
    const router = await open('/unlock?next=%2F%2Fevil.example');
    await userEvent.type(await screen.findByLabelText('Mot de passe'), MOCK_PASSWORD);
    await userEvent.click(screen.getByRole('button', { name: 'Déverrouiller' }));
    await waitFor(() => expect(router.state.location.pathname).toBe('/'));
  });

  it('five wrong passwords throttle the sixth, even with the right one', async () => {
    await open('/unlock');
    const field = await screen.findByLabelText('Mot de passe');
    for (let i = 0; i < 5; i++) {
      await userEvent.type(field, 'wrong');
      await userEvent.click(screen.getByRole('button', { name: 'Déverrouiller' }));
      await screen.findByText(/pas le bon|Trop de tentatives/);
    }
    await userEvent.type(field, MOCK_PASSWORD);
    await userEvent.click(screen.getByRole('button', { name: 'Déverrouiller' }));
    expect(await screen.findByText(/Trop de tentatives/)).toBeInTheDocument();
    expect(api.world().account.isLocked()).toBe(true);
  });
});
