import { Button, Dialog, Input, LanguageSwitch, Select, format } from '@mona/ui';
import { useQueryClient } from '@tanstack/react-query';
import { Link, useRouterState } from '@tanstack/react-router';
import { useEffect, useState, type FormEvent } from 'react';
import type { TFunction } from 'i18next';
import { useTranslation } from 'react-i18next';
import { LoadError, LoadingState } from '../../components/states';
import { errorKey } from '../../data/errors';
import type { SettingsView } from '../../data/dto';
import { useSettings } from '../../data/hooks';
import { ApiError } from '../../data/http';
import { useEntityDetail, useEntityList } from '../../data/registry';
import { RANGES, changePassword, draftOf, patchSettings, settingsChanges, useSystemStatus, validateSettings, type SettingsDraft, type SettingsErrorCode, type SettingsField } from '../../data/settings';
import { useLang } from '../../shell/useLang';
import { toasts } from '../../toast/store';
import { DataFlowDiagram } from './DataFlowDiagram';
import { SettingsSection } from './SettingsSection';
import { StatusTile } from './StatusTile';
import { statusTiles } from './statusView';

const SECTIONS = ['profile', 'language', 'thresholds', 'status', 'privacy', 'about'] as const;
const PROFILE_FIELDS: SettingsField[] = ['profileName', 'practiceName', 'autoLockMinutes'];
const THRESHOLD_FIELDS: SettingsField[] = ['confidenceHigh', 'confidenceLow', 'badgeHours', 'debriefQueueThreshold', 'debriefEarlyMin'];

function SectionNav() {
  const { t } = useTranslation();
  return (
    <nav aria-label={t('settings.nav.label')} className="hidden lg:block">
      <ul className="sticky top-10 m-0 flex list-none flex-col gap-1 p-0">
        {SECTIONS.map((id) => (
          <li key={id}>
            <Link to="/settings" hash={id} activeOptions={{ exact: true, includeHash: true }} className="block rounded-md px-3 py-2 font-ui text-[14px] leading-5 text-text no-underline hover:bg-surface-sunken aria-[current=page]:font-semibold aria-[current=page]:text-accent-strong">
              {t(`settings.nav.${id}`)}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function useDraft(view: SettingsView) {
  const [draft, setDraft] = useState<SettingsDraft>(() => draftOf(view));
  const [serverErrors, setServerErrors] = useState<Partial<Record<SettingsField, string>>>({});
  const [saving, setSaving] = useState(false);
  const qc = useQueryClient();
  const { t } = useTranslation();
  const errors = validateSettings(draft);
  const saved = draftOf(view);

  const set = (field: SettingsField, value: string) => {
    setDraft((d) => ({ ...d, [field]: value }));
    setServerErrors((e) => ({ ...e, [field]: undefined }));
  };

  async function save(fields: SettingsField[]) {
    const changes = settingsChanges(draft, view);
    const patch = Object.fromEntries(Object.entries(changes).filter(([key]) => fields.includes(key as SettingsField)));
    if (Object.keys(patch).length === 0) return;
    setSaving(true);
    try {
      const next = await patchSettings(patch);
      qc.setQueryData(['settings'], next);
      setDraft((d) => ({ ...d, ...Object.fromEntries(fields.map((f) => [f, draftOf(next)[f]])) }));
      toasts.push({ key: 'settings-saved', message: 'settings.saved', tone: 'success' });
    } catch (err) {
      if (err instanceof ApiError && err.code === 'invalid_value' && err.field) setServerErrors((e) => ({ ...e, [err.field as SettingsField]: t(errorKey(err)) }));
      else toasts.push({ key: 'settings-failed', message: errorKey(err), tone: 'danger' });
    } finally {
      setSaving(false);
    }
  }

  const dirty = (fields: SettingsField[]) => fields.some((f) => draft[f].trim() !== saved[f]);
  const invalid = (fields: SettingsField[]) => fields.some((f) => errors[f] !== undefined);
  return { draft, set, errors, serverErrors, save, saving, dirty, invalid, saved };
}

type Draft = ReturnType<typeof useDraft>;

function fieldError(d: Draft, field: SettingsField, t: TFunction): string | undefined {
  if (d.serverErrors[field]) return d.serverErrors[field];
  const code: SettingsErrorCode | undefined = d.errors[field];
  if (!code || d.draft[field].trim() === d.saved[field]) return undefined;
  const range = field in RANGES ? RANGES[field as keyof typeof RANGES] : undefined;
  return t(`settings.error.${code}`, { min: range?.[0], max: range?.[1] });
}

function Field({ d, field, label, hint }: { d: Draft; field: SettingsField; label: string; hint?: string }) {
  const { t } = useTranslation();
  const numeric = field !== 'profileName' && field !== 'practiceName';
  return (
    <Input
      label={label}
      hint={hint}
      value={d.draft[field]}
      error={fieldError(d, field, t)}
      inputMode={numeric ? 'numeric' : undefined}
      maxLength={numeric ? 4 : 120}
      onChange={(e) => d.set(field, e.target.value)}
    />
  );
}

function PasswordDialog({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [again, setAgain] = useState('');
  const [errors, setErrors] = useState<{ current?: string; next?: string; again?: string }>({});
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    const found: typeof errors = {};
    if (next.length < 8) found.next = t('settings.password.tooShort');
    else if (next !== again) found.again = t('settings.password.mismatch');
    if (current === '') found.current = t('settings.error.whole');
    setErrors(found);
    if (Object.keys(found).length > 0) return;
    setBusy(true);
    try {
      await changePassword({ currentPassword: current, newPassword: next });
      toasts.push({ key: 'password-changed', message: 'settings.password.changed', tone: 'success' });
      onClose();
    } catch (err) {
      if (err instanceof ApiError && err.code === 'invalid_password') setErrors({ current: t(errorKey(err)) });
      else if (err instanceof ApiError && err.code === 'invalid_value') setErrors({ next: t('settings.password.tooShort') });
      else toasts.push({ key: 'password-failed', message: errorKey(err), tone: 'danger' });
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      title={t('settings.password.title')}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="primary" type="submit" form="password-form" loading={busy}>
            {t('settings.password.save')}
          </Button>
        </>
      }
    >
      <form id="password-form" onSubmit={(e) => void submit(e)} className="flex flex-col gap-4">
        <Input label={t('settings.password.current')} type="password" autoComplete="current-password" value={current} error={errors.current} onChange={(e) => setCurrent(e.target.value)} />
        <Input label={t('settings.password.new')} type="password" autoComplete="new-password" value={next} error={errors.next} hint={t('settings.password.hint')} onChange={(e) => setNext(e.target.value)} />
        <Input label={t('settings.password.again')} type="password" autoComplete="new-password" value={again} error={errors.again} onChange={(e) => setAgain(e.target.value)} />
      </form>
    </Dialog>
  );
}

function SaveRow({ d, fields, label }: { d: Draft; fields: SettingsField[]; label: string }) {
  return (
    <div>
      <Button variant="primary" loading={d.saving} disabled={!d.dirty(fields) || d.invalid(fields)} onClick={() => void d.save(fields)}>
        {label}
      </Button>
    </div>
  );
}

function StatusSection() {
  const { t } = useTranslation();
  const lang = useLang();
  const status = useSystemStatus();
  return (
    <SettingsSection id="status" title={t('settings.nav.status')} actions={<Button variant="quiet" size="sm" icon="loader" onClick={() => void status.refetch()}>{t('settings.status.refresh')}</Button>}>
      {status.isError ? (
        <LoadError onRetry={() => void status.refetch()}>{t('settings.status.failed')}</LoadError>
      ) : status.isPending ? (
        <LoadingState label={t('states.loading.status')} lines={3} />
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {statusTiles(status.data, t, lang).map((tile) => (
            <StatusTile key={tile.id} label={tile.label} value={tile.value} status={tile.status} tone={tile.tone} detail={tile.detail} />
          ))}
        </div>
      )}
    </SettingsSection>
  );
}

function PrivacySection() {
  const { t } = useTranslation();
  const status = useSystemStatus();
  const list = useEntityList();
  const visitors = useEntityDetail(list.data?.visitorsEntityId);
  return (
    <SettingsSection id="privacy" title={t('settings.privacy.title')}>
      <DataFlowDiagram cloudAi={status.data?.privacy.cloudAi ?? false} telegram={status.data?.privacy.telegram ?? true} visitorHours={visitors.data?.purgeAfterHours ?? 24} />
      <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('settings.privacy.limit')}</p>
    </SettingsSection>
  );
}

function AboutSection() {
  const { t } = useTranslation();
  const status = useSystemStatus();
  return (
    <SettingsSection id="about" title={t('settings.nav.about')}>
      <dl className="m-0 grid grid-cols-1 gap-3 sm:grid-cols-[160px_minmax(0,1fr)]">
        <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{t('settings.about.app')}</dt>
        <dd className="m-0 text-text" data-testid="about-web-version">
          Mona {__MONA_VERSION__}
        </dd>
        <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{t('settings.about.server')}</dt>
        <dd className="m-0 text-text" data-testid="about-server-version">
          {status.data ? [status.data.version, status.data.build].filter(Boolean).join(' · ') : '…'}
        </dd>
        <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{t('settings.about.mode')}</dt>
        <dd className="m-0 text-text">{status.data ? t(`settings.about.env.${status.data.env}`) : '…'}</dd>
      </dl>
    </SettingsSection>
  );
}

export function SettingsPage() {
  const { t } = useTranslation();
  const lang = useLang();
  const settings = useSettings();
  const qc = useQueryClient();
  const hash = useRouterState({ select: (s) => s.location.hash });
  const [dialog, setDialog] = useState(false);
  const [langBusy, setLangBusy] = useState(false);

  useEffect(() => {
    if (hash && settings.data) document.getElementById(hash)?.scrollIntoView({ block: 'start' });
  }, [hash, settings.data]);

  async function saveLanguage(patch: Partial<SettingsView>) {
    setLangBusy(true);
    try {
      qc.setQueryData(['settings'], await patchSettings(patch));
    } catch (err) {
      toasts.push({ key: 'settings-failed', message: errorKey(err), tone: 'danger' });
    } finally {
      setLangBusy(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-[1080px] flex-col gap-6 p-6 lg:p-10">
      <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.settings')}</h1>
      {settings.isPending ? <LoadingState label={t('states.loading.settings')} /> : null}
      {settings.isError ? <LoadError onRetry={() => void settings.refetch()} /> : null}
      {settings.data ? (
        <SettingsBody view={settings.data} lang={lang} langBusy={langBusy} onLanguage={saveLanguage} openPassword={() => setDialog(true)} />
      ) : null}
      {dialog ? <PasswordDialog onClose={() => setDialog(false)} /> : null}
    </div>
  );
}

function SettingsBody({ view, lang, langBusy, onLanguage, openPassword }: { view: SettingsView; lang: 'en' | 'fr' | 'ro'; langBusy: boolean; onLanguage: (patch: Partial<SettingsView>) => Promise<void>; openPassword: () => void }) {
  const { t } = useTranslation();
  const d = useDraft(view);
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[180px_minmax(0,1fr)]">
      <SectionNav />
      <div className="flex min-w-0 flex-col gap-6">
        <SettingsSection id="profile" title={t('settings.profile.title')}>
          <p className="m-0 text-text-muted">{t('settings.profile.body')}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field d={d} field="profileName" label={t('settings.profile.name')} />
            <Field d={d} field="practiceName" label={t('settings.profile.practice')} />
            <Field d={d} field="autoLockMinutes" label={t('settings.profile.autoLock')} hint={t('settings.profile.autoLockHint')} />
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <SaveRow d={d} fields={PROFILE_FIELDS} label={t('settings.save')} />
            <Button variant="secondary" icon="lock" onClick={openPassword}>
              {t('settings.password.change')}
            </Button>
          </div>
        </SettingsSection>

        <SettingsSection id="language" title={t('settings.nav.language')}>
          <div className="flex flex-col gap-2">
            <span className="font-ui text-[14px] leading-5 font-semibold text-text">{t('settings.language.interface')}</span>
            <div className="flex flex-wrap items-center gap-3">
              <LanguageSwitch label={t('settings.language.interface')} value={view.locale} onChange={(v) => void onLanguage({ locale: v })} />
              <span aria-live="polite" className="font-ui text-[13px] text-text-muted">
                {langBusy ? '…' : format.date(new Date(2026, 2, 14), lang) + ' · ' + format.money(1284.6, 'EUR', lang)}
              </span>
            </div>
            <span className="font-ui text-[13px] leading-[18px] text-text-muted">{t('settings.language.interfaceHint')}</span>
          </div>
          <Select
            label={t('settings.language.filing')}
            hint={t('settings.language.filingHint')}
            value={view.filingLanguage}
            onChange={(e) => void onLanguage({ filingLanguage: e.target.value as 'en' | 'fr' | 'ro' })}
            options={[
              { value: 'fr', label: t('language.fr') },
              { value: 'en', label: t('language.en') },
              { value: 'ro', label: t('language.ro') },
            ]}
          />
        </SettingsSection>

        <SettingsSection id="thresholds" title={t('settings.thresholds.title')}>
          <p className="m-0 text-text-muted">{t('settings.thresholds.body')}</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field d={d} field="confidenceHigh" label={t('settings.thresholds.high')} hint={t('settings.thresholds.highHint')} />
            <Field d={d} field="confidenceLow" label={t('settings.thresholds.low')} hint={t('settings.thresholds.lowHint')} />
            <Field d={d} field="badgeHours" label={t('settings.thresholds.badge')} hint={t('settings.thresholds.badgeHint')} />
            <Field d={d} field="debriefQueueThreshold" label={t('settings.thresholds.debrief')} hint={t('settings.thresholds.debriefHint')} />
            <Field d={d} field="debriefEarlyMin" label={t('settings.thresholds.early')} hint={t('settings.thresholds.earlyHint')} />
          </div>
          <SaveRow d={d} fields={THRESHOLD_FIELDS} label={t('settings.save')} />
        </SettingsSection>

        <StatusSection />
        <PrivacySection />
        <AboutSection />
      </div>
    </div>
  );
}
