import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export function Home() {
  const { t } = useTranslation();
  const health = useQuery({
    queryKey: ['health'],
    queryFn: async () => (await api.GET('/api/health')).data ?? null,
  });
  return (
    <main className="mx-auto flex max-w-md flex-col gap-4 p-8 font-ui">
      <h1 className="font-voice text-text">{t('app.name')}</h1>
      <p className="text-text-muted">{t('app.tagline')}</p>
      <p className="text-text-muted" data-testid="health">
        {t('home.status')} {health.data ? `v${health.data.version} · db ${health.data.db}` : ''}
      </p>
    </main>
  );
}
