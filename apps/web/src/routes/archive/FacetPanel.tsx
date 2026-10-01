import { Checkbox, Combobox, Input, RadioGroup, Select, StatusPill, Tag, format } from '@mona/ui';
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ALL_STATUSES, type ArchiveFilters } from '../../data/archive';
import type { ArchiveStatus, DocumentFacets } from '../../data/dto';
import { useCategories } from '../../data/registry';
import { useLang } from '../../shell/useLang';

export interface FacetPanelProps {
  facets: DocumentFacets;
  filters: ArchiveFilters;
  /** The shell's entity scope is set, so the entity facet would only contradict it. */
  scoped: boolean;
  onChange(patch: Partial<ArchiveFilters>): void;
}

const heading = 'font-ui text-[14px] leading-5 font-semibold text-text';
const muted = 'text-text-muted';

function AmountRange({ filters, onChange }: Pick<FacetPanelProps, 'filters' | 'onChange'>) {
  const { t } = useTranslation();
  const [min, setMin] = useState(filters.amountMin?.toString() ?? '');
  const [max, setMax] = useState(filters.amountMax?.toString() ?? '');
  const commit = () => {
    const parse = (v: string) => (v.trim() === '' || !Number.isFinite(Number(v)) || Number(v) < 0 ? undefined : Number(v));
    const next = { amountMin: parse(min), amountMax: parse(max) };
    if (next.amountMin !== filters.amountMin || next.amountMax !== filters.amountMax) onChange(next);
  };
  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        commit();
      }}
    >
      <Input type="number" min={0} inputMode="decimal" label={t('archive.facets.amountMin')} placeholder={t('archive.facets.min')} value={min} onChange={(e) => setMin(e.target.value)} onBlur={commit} />
      <Input type="number" min={0} inputMode="decimal" label={t('archive.facets.amountMax')} placeholder={t('archive.facets.max')} value={max} onChange={(e) => setMax(e.target.value)} onBlur={commit} />
      <button type="submit" hidden aria-hidden tabIndex={-1} />
    </form>
  );
}

export function FacetPanel({ facets, filters, scoped, onChange }: FacetPanelProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const categories = useCategories().data ?? [];
  const n = (v: number) => format.number(v, lang);
  const statuses = filters.statuses ?? ALL_STATUSES;
  const statusCount = (s: ArchiveStatus) => facets.statuses.find((x) => x.status === s)?.count ?? 0;
  const totalEntities = facets.entities.reduce((sum, e) => sum + e.count, 0);

  const counterpartyOptions = [
    { value: '', label: t('archive.facets.anyCounterparty') },
    ...facets.counterparties.map((c) => ({ value: c.id, label: `${c.name} · ${n(c.count)}` })),
  ];

  return (
    <div className="flex flex-col gap-6" data-testid="facet-panel">
      {scoped ? null : (
        <RadioGroup
          legend={t('archive.facets.entity')}
          value={filters.entityId ?? ''}
          onChange={(v) => onChange({ entityId: v || undefined })}
          options={[
            { value: '', label: <span>{t('shell.scope.all')} <span className={muted}>{n(totalEntities)}</span></span> },
            ...facets.entities.map((e) => ({ value: e.id, label: <span>{e.name} <span className={muted}>{n(e.count)}</span></span> })),
          ]}
        />
      )}
      {facets.years.length > 0 ? (
        <div role="group" aria-labelledby="facet-year" className="flex flex-col gap-2">
          <span id="facet-year" className={heading}>
            {t('archive.facets.year')}
          </span>
          <div className="flex flex-wrap gap-2">
            {facets.years.map((y) => (
              <Tag key={y.year} lang={lang} selected={filters.year === y.year} onToggle={(on) => onChange({ year: on ? y.year : undefined })}>
                {`${format.number(y.year, lang, { useGrouping: false })} · ${n(y.count)}`}
              </Tag>
            ))}
          </div>
        </div>
      ) : null}
      <Select
        label={t('archive.facets.category')}
        value={filters.categoryId ?? ''}
        onChange={(e) => onChange({ categoryId: e.target.value || undefined })}
        options={[
          { value: '', label: t('archive.facets.anyCategory') },
          ...facets.categories.map((c) => ({ value: c.id, label: `${categories.find((x) => x.id === c.id)?.labels[lang] ?? c.label} · ${n(c.count)}` })),
        ]}
      />
      <Combobox
        label={t('archive.facets.counterparty')}
        lang={lang}
        value={filters.counterpartyId ?? ''}
        options={counterpartyOptions}
        emptyText={t('archive.facets.noCounterparty')}
        onChange={(v: string | null) => onChange({ counterpartyId: v || undefined })}
      />
      <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend className={`${heading} mb-2 p-0`}>{t('archive.facets.amount')}</legend>
        <AmountRange key={`${filters.amountMin ?? ''}-${filters.amountMax ?? ''}`} filters={filters} onChange={onChange} />
      </fieldset>
      <fieldset className="m-0 flex min-w-0 flex-col gap-2 border-0 p-0">
        <legend className={`${heading} mb-2 p-0`}>{t('archive.facets.status')}</legend>
        {ALL_STATUSES.map((s) => (
          <Checkbox
            key={s}
            checked={statuses.includes(s)}
            onChange={(e) => {
              const next = e.target.checked ? ALL_STATUSES.filter((x) => x === s || statuses.includes(x)) : statuses.filter((x) => x !== s);
              onChange({ statuses: next.length === 0 || next.length === ALL_STATUSES.length ? undefined : next });
            }}
            label={
              <span className="inline-flex items-center gap-2">
                <StatusPill status={s} size="sm" lang={lang} label={s === 'filed' ? t('common.filed') : undefined} />
                <span className={muted}>{n(statusCount(s))}</span>
              </span>
            }
          />
        ))}
      </fieldset>
    </div>
  );
}
