import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import i18n from '../i18n';
import { LanguageSync } from '../shell/LanguageSync';
import { DataProvidersContext } from './context';
import { useEntities, useHealth, useSettings } from './hooks';
import { createWorld } from '../mocks';
import { useMockApi } from '../test/mockApi';
import { renderRoute } from '../test/renderRoute';
import { ENTITIES } from '../mocks/seed';
import { defaultProviders, fetchHealth, type DataProviders } from './providers';

function wrapper(providers: DataProviders = defaultProviders) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>
      <DataProvidersContext.Provider value={providers}>{children}</DataProvidersContext.Provider>
    </QueryClientProvider>
  );
}

describe('health', () => {
  afterEach(() => vi.unstubAllGlobals());

  it('reads the real endpoint', async () => {
    const fetch = vi.fn<(req: Request) => Promise<Response>>(async () => Response.json({ status: 'ok', db: 'ok', version: '0.1.0' }));
    vi.stubGlobal('fetch', fetch);
    await expect(fetchHealth()).resolves.toEqual({ status: 'ok', version: '0.1.0' });
    expect(new URL(fetch.mock.calls[0]![0].url).pathname).toBe('/api/health');
  });

  it('reports degraded from a 503 body and offline when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Response.json({ status: 'degraded', db: 'error', version: '0.1.0' }, { status: 503 })));
    await expect(fetchHealth()).resolves.toEqual({ status: 'degraded', version: '0.1.0' });
    vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 500 })));
    await expect(fetchHealth()).resolves.toEqual({ status: 'offline', version: null });
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('network'); }));
    await expect(fetchHealth()).resolves.toEqual({ status: 'offline', version: null });
  });

  it('useHealth goes through the provider', async () => {
    const health = vi.fn(async () => ({ status: 'ok' as const, version: '9' }));
    const { result } = renderHook(() => useHealth(), { wrapper: wrapper({ ...defaultProviders, health }) });
    await waitFor(() => expect(result.current.data).toEqual({ status: 'ok', version: '9' }));
  });
});

describe('the C2 providers', () => {
  const api = useMockApi();

  it('serve the entity list and the settings view', async () => {
    const { result } = renderHook(() => ({ e: useEntities(), s: useSettings() }), { wrapper: wrapper() });
    await waitFor(() => expect(result.current.e.data).toEqual(ENTITIES));
    await waitFor(() => expect(result.current.s.data).toMatchObject({ locale: 'en', profileName: 'Léa Marchand', confidenceHigh: 85 }));
  });

  it('follow the profile language of the API', async () => {
    api.world().account.patch({ locale: 'ro' });
    await expect(defaultProviders.settings()).resolves.toMatchObject({ locale: 'ro' });
  });
});

describe('LanguageSync', () => {
  afterEach(async () => {
    await i18n.changeLanguage('en');
  });

  it('applies the settings language to i18n and <html lang>', async () => {
    const settings = async () => ({ ...createWorld({ seed: false }).account.settings(), locale: 'fr' as const });
    await renderRoute(<LanguageSync />, '/', (children) => <DataProvidersContext.Provider value={{ ...defaultProviders, settings }}>{children}</DataProvidersContext.Provider>);
    await waitFor(() => expect(document.documentElement.lang).toBe('fr'));
    expect(i18n.t('nav.home')).toBe('Accueil');
  });
});
