import { Avatar, Button, Icon, Input, MonaAvatar } from '@mona/ui';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter, useSearch } from '@tanstack/react-router';
import { useEffect, useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { MonaLogo, type LogoStroke } from '../components/MonaLogo';
import { fetchAuthState, firstName, safeNext, unlock } from '../data/auth';
import { errorKey } from '../data/errors';
import i18n from '../i18n';
import { useMinWidth } from '../shell/useMinWidth';

const ARCHES = [156, 198, 156, 198, 156];

export function Unlock() {
  const { t } = useTranslation();
  const router = useRouter();
  const qc = useQueryClient();
  const { next } = useSearch({ from: '/unlock' });
  const state = useQuery({ queryKey: ['auth-state'], queryFn: fetchAuthState, retry: false, staleTime: 0 });
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const wide = useMinWidth(1750);
  const mid = useMinWidth(1280);
  const stroke: LogoStroke = wide ? 5 : mid ? 4 : 3;
  const avatarSize = wide ? 72 : mid ? 56 : 44;
  const name = firstName(state.data?.profileName);
  const tagline = t('app.tagline').split('\n');

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
    <main id="main-content" className="unlock grid min-h-screen bg-bg font-ui text-text lg:grid-cols-[1.116fr_1fr]">
      <div className="hidden box-border min-h-screen flex-col justify-between overflow-hidden border-r border-border bg-surface pt-[calc(66*var(--u))] pl-[calc(75*var(--u))] lg:flex">
        <MonaLogo stroke={stroke} label="Mona" />
        <div className="flex flex-col gap-[calc(36*var(--u))] self-start">
          <p className="unlock-headline" data-testid="unlock-headline">
            {tagline.map((line) => (
              <span key={line} className="block">
                {line}
              </span>
            ))}
          </p>
          <p className="m-0 text-text-muted [font-size:calc(17*var(--u))] [line-height:calc(26*var(--u))]">{t('auth.unlock.privacy')}</p>
        </div>
        <div aria-hidden className="flex items-end gap-[calc(22*var(--u))]" data-testid="unlock-arches">
          {ARCHES.map((h, i) => (
            <span key={i} className="relative w-[calc(110*var(--u))] shrink-0 rounded-t-full bg-surface-sunken" style={{ height: `calc(${h} * var(--u))` }}>
              {i === 2 ? <span className="absolute top-[calc(44*var(--u))] left-1/2 size-[calc(27*var(--u))] -translate-x-1/2 rounded-full bg-[var(--brand-saffron)]" data-testid="unlock-dot" /> : null}
            </span>
          ))}
        </div>
      </div>
      <div className="relative box-border flex min-h-screen flex-col items-center justify-center gap-6 p-6">
        <div className="lg:hidden">
          <MonaLogo stroke={stroke} label="Mona" />
        </div>
        <form
          onSubmit={(e) => void submit(e)}
          className="box-border flex w-full max-w-[420px] flex-col gap-[calc(28*var(--u))] rounded-lg border border-border bg-surface-raised p-8 shadow-2 lg:w-[min(100%,calc(544*var(--u)))] lg:max-w-none lg:p-[calc(42*var(--u))]"
          aria-labelledby="unlock-title"
          data-testid="unlock-form"
        >
          <div className="flex items-center gap-[calc(15*var(--u))]">
            {name ? <Avatar name={state.data?.profileName ?? name} size={avatarSize} /> : <MonaAvatar size={avatarSize} />}
            <div className="flex min-w-0 flex-col gap-1">
              <h1 id="unlock-title" className="unlock-title">
                {name ? t('auth.unlock.welcome', { name }) : t('auth.unlock.title')}
              </h1>
              <p className="m-0 text-text-muted [font-size:max(13px,calc(14*var(--u)))] [line-height:max(18px,calc(19*var(--u)))]">{t('auth.unlock.subtitle')}</p>
            </div>
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
        <p className="m-0 flex items-center justify-center gap-2 text-center text-text-muted [font-size:max(13px,calc(14*var(--u)))] lg:absolute lg:inset-x-6 lg:bottom-[calc(32*var(--u))]" data-testid="unlock-footer">
          <Icon name="hard-drive" size={16} />
          {t('auth.unlock.footer')}
        </p>
      </div>
    </main>
  );
}
