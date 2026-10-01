import { Button, Input, Skeleton, format } from '@mona/ui';
import { Link, useParams } from '@tanstack/react-router';
import { useState, type FormEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { LoadError } from '../../components/states';
import { errorKey } from '../../data/errors';
import { ApiError } from '../../data/http';
import { usePatchRule, useRule } from '../../data/rules';
import { useLang } from '../../shell/useLang';
import { RuleSwitch, SourceChip } from './RuleRow';
import { destinationText, lastFiredLabel, needsCheck } from './ruleView';

function NameForm({ name: saved, busy, onSave }: { name: string; busy: boolean; onSave(name: string, onError: (err: unknown) => void): void }) {
  const { t } = useTranslation();
  const [name, setName] = useState(saved);
  const [error, setError] = useState<string | null>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > 120) {
      setError(t('rules.detail.nameInvalid'));
      return;
    }
    setError(null);
    onSave(trimmed, (err) => setError(t(errorKey(err), { message: err instanceof ApiError ? String(err.details?.message ?? '') : '' })));
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-3" aria-label={t('rules.detail.nameForm')}>
      <div className="min-w-[260px] flex-1">
        <Input label={t('rules.detail.name')} value={name} error={error} maxLength={120} onChange={(e) => setName(e.target.value)} />
      </div>
      <Button type="submit" variant="secondary" loading={busy} disabled={name.trim() === saved}>
        {t('rules.detail.save')}
      </Button>
    </form>
  );
}

export function RuleDetail() {
  const { t } = useTranslation();
  const lang = useLang();
  const { ruleId } = useParams({ from: '/shell/rules/$ruleId' });
  const query = useRule(ruleId);
  const patch = usePatchRule();
  const rule = query.data?.rule;
  if (query.isPending) return <div className="mx-auto max-w-[880px] p-6 lg:p-10"><h1 className="mona-sr">{t('nav.rules')}</h1><Skeleton lines={5} /></div>;
  if (query.isError || !rule) {
    const missing = query.error instanceof ApiError && query.error.status === 404;
    return (
      <div className="mx-auto flex max-w-[880px] flex-col gap-4 p-6 lg:p-10">
        <h1 className="m-0 text-text [font:var(--type-title)]">{t('nav.rules')}</h1>
        {missing ? <p className="m-0 text-text-muted">{t('rules.detail.notFound')}</p> : <LoadError onRetry={() => void query.refetch()} />}
        <Link to="/rules" className="font-ui text-[14px] font-semibold text-info underline underline-offset-2">
          {t('rules.detail.back')}
        </Link>
      </div>
    );
  }

  const n = (v: number) => format.number(v, lang);
  const stats: [string, string][] = [
    [t('rules.table.fired'), n(rule.firedCount)],
    [t('rules.table.lastFired'), lastFiredLabel(rule.lastFiredAt, query.dataUpdatedAt, lang, t)],
    [t('rules.table.corrections'), needsCheck(rule) ? t('rules.row.check', { n: n(rule.correctionsSince) }) : n(rule.correctionsSince)],
  ];

  return (
    <div className="mx-auto flex max-w-[880px] flex-col gap-6 p-6 lg:p-10" data-testid="rule-detail" data-rule-id={rule.id}>
      <Link to="/rules" className="w-fit font-ui text-[14px] font-semibold text-info underline underline-offset-2">
        {t('rules.detail.back')}
      </Link>
      <header className="flex flex-col gap-2">
        <h1 className="m-0 text-text [font:var(--type-title)]">{rule.name}</h1>
        <div className="flex flex-wrap items-center gap-3">
          <SourceChip source={rule.source} />
          <span className="font-ui text-[14px] leading-5 text-text-muted">{t(`rules.state.${rule.state}`)}</span>
          <RuleSwitch on={rule.state === 'active'} label={t('rules.row.switch', { name: rule.name })} disabled={patch.isPending} onChange={(enabled) => patch.mutate({ id: ruleId, body: { enabled } })} />
        </div>
      </header>
      <NameForm key={rule.name} name={rule.name} busy={patch.isPending} onSave={(name, onError) => patch.mutate({ id: ruleId, body: { name } }, { onError })} />
      <dl className="m-0 grid grid-cols-1 gap-4 rounded-lg border border-border bg-surface p-5 sm:grid-cols-[160px_minmax(0,1fr)]">
        <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{t('rules.detail.condition')}</dt>
        <dd className="m-0 text-text">{rule.condition}</dd>
        <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{t('rules.detail.destination')}</dt>
        <dd className="m-0 [font:var(--type-filename)] text-text">{destinationText(rule)}</dd>
        {stats.map(([term, value]) => (
          <div key={term} className="contents">
            <dt className="font-ui text-[14px] leading-5 font-semibold text-text-muted">{term}</dt>
            <dd className="m-0 text-text">{value}</dd>
          </div>
        ))}
      </dl>
      {query.data && query.data.problems.length > 0 ? (
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 text-danger" aria-label={t('rules.detail.problems')}>
          {query.data.problems.map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
