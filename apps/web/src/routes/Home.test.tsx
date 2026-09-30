import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { Home } from './Home';

function renderHome() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <Home />
    </QueryClientProvider>,
  );
}

describe('Home', () => {
  afterEach(async () => {
    vi.unstubAllGlobals();
    await i18n.changeLanguage('en');
  });

  it('shows the translated tagline and the typed health response', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => Response.json({ status: 'ok', db: 'ok', version: '0.1.0' })),
    );
    await i18n.changeLanguage('fr');
    renderHome();
    expect(screen.getByText('Vos papiers, réglés — ici, au cabinet.')).toBeInTheDocument();
    expect(await screen.findByText(/v0\.1\.0 · db ok/)).toBeInTheDocument();
  });
});
