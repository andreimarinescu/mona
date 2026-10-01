import logoUrl from '@design/mona-handoff/assets/mona-logo.svg';
import { Button, Input } from '@mona/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearch } from '@tanstack/react-router';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { fetchAuthState, safeNext, unlock } from '../data/auth';
import { errorKey } from '../data/errors';
import i18n from '../i18n';

const ARCHES = ['h-[120px]', 'h-[170px]', 'h-[120px]', 'h-[170px]', 'h-[120px]'];

export function Unlock() {
  const { t } = useTranslation();
  const router = useRouter();
  const qc = useQueryClient();
  const { next } = useSearch({ from: '/unlock' });
  const state = useQuery({ queryKey: ['auth-state'], queryFn: fetchAuthState, retry: false, staleTime: 0 });
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (state.data?.locale) void i18n.changeLanguage(state.data.locale);
  }, [state.data?.locale]);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (busy || password === '') return;
    setBusy(true);
    setError(null);
    try {
      await unlock(password);
      await qc.resetQueries();
      router.history.push(safeNext(next));
    } catch (err) {
      setError(t(errorKey(err)));
      setPassword('');
    } finally {
      setBusy(false);
    }
  }

  return (
    <main id="main-content" className="grid min-h-screen bg-bg font-ui text-text lg:grid-cols-2">
      <div className="hidden flex-col justify-between bg-surface p-10 lg:flex">
        <img src={logoUrl} alt="Mona" width={120} height={38} />
        <div className="flex flex-col gap-4">
          <p className="m-0 max-w-[420px] text-text [font:var(--type-display)]">{t('app.tagline')}</p>
          <p className="m-0 text-text-muted">{t('auth.unlock.privacy')}</p>
        </div>
        <div aria-hidden className="flex items-end gap-4">
          {ARCHES.map((h, i) => (
            <span key={i} className={`${h} w-[66px] rounded-t-full bg-surface-sunken`} />
          ))}
        </div>
      </div>
      <div className="flex flex-col items-center justify-center gap-6 p-6">
        <img src={logoUrl} alt="Mona" width={120} height={38} className="lg:hidden" />
        <form onSubmit={(e) => void submit(e)} className="flex w-full max-w-[420px] flex-col gap-5 rounded-lg border border-border bg-surface-raised p-8 shadow-2" aria-labelledby="unlock-title" data-testid="unlock-form">
          <div className="flex flex-col gap-1">
            <h1 id="unlock-title" className="m-0 text-text [font:var(--type-title)]">
              {t('auth.unlock.title')}
            </h1>
            <p className="m-0 text-[13px] leading-[18px] text-text-muted">{t('auth.unlock.subtitle')}</p>
          </div>
          <div className="flex flex-col gap-2">
            <Input label={t('auth.unlock.password')} type="password" autoComplete="current-password" value={password} error={error} onChange={(e) => setPassword(e.target.value)} />
            <p className="m-0 text-[13px] leading-[18px] text-text-muted">{t('auth.unlock.hint')}</p>
          </div>
          <div>
            <Button type="submit" variant="primary" icon="lock" loading={busy} disabled={password === ''}>
              {t('auth.unlock.submit')}
            </Button>
          </div>
        </form>
      </div>
    </main>
  );
}
