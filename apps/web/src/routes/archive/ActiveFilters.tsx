import { Button, Tag, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { ALL_STATUSES, activeFilterCount, type ArchiveFilters } from '../../data/archive';
import type { DocumentFacets } from '../../data/dto';
import { useCategories } from '../../data/registry';
import { useLang } from '../../shell/useLang';

export interface ActiveFiltersProps {
  facets: DocumentFacets | undefined;
  filters: ArchiveFilters;
  scoped: boolean;
  onChange(patch: Partial<ArchiveFilters>): void;
  onClear(): void;
}

export function ActiveFilters({ facets, filters, scoped, onChange, onClear }: ActiveFiltersProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const categories = useCategories().data ?? [];
  const n = (v: number) => format.number(v, lang);
  const chips: { key: string; label: string; remove: Partial<ArchiveFilters> }[] = [];
  if (filters.entityId && !scoped) chips.push({ key: 'entity', label: facets?.entities.find((e) => e.id === filters.entityId)?.name ?? t('archive.facets.entity'), remove: { entityId: undefined } });
  if (filters.year !== undefined) chips.push({ key: 'year', label: format.number(filters.year, lang, { useGrouping: false }), remove: { year: undefined } });
  if (filters.categoryId) {
    const fallback = facets?.categories.find((c) => c.id === filters.categoryId)?.label ?? t('archive.facets.category');
    chips.push({ key: 'category', label: categories.find((c) => c.id === filters.categoryId)?.labels[lang] ?? fallback, remove: { categoryId: undefined } });
  }
  if (filters.counterpartyId) chips.push({ key: 'counterparty', label: facets?.counterparties.find((c) => c.id === filters.counterpartyId)?.name ?? t('archive.facets.counterparty'), remove: { counterpartyId: undefined } });
  if (filters.amountMin !== undefined || filters.amountMax !== undefined) {
    const { amountMin: lo, amountMax: hi } = filters;
    const label = lo !== undefined && hi !== undefined ? `${n(lo)} – ${n(hi)}` : lo !== undefined ? `≥ ${n(lo)}` : `≤ ${n(hi!)}`;
    chips.push({ key: 'amount', label, remove: { amountMin: undefined, amountMax: undefined } });
  }
  if (filters.statuses) {
    const names = ALL_STATUSES.filter((s) => filters.statuses!.includes(s)).map((s) => t(`archive.status.${s}`));
    chips.push({ key: 'status', label: names.join(', '), remove: { statuses: undefined } });
  }
  if (chips.length === 0 || activeFilterCount(filters) === 0) return null;
  return (
    <ul className="m-0 flex list-none flex-wrap items-center gap-2 p-0" aria-label={t('archive.active.label')} data-testid="active-filters">
      {chips.map((chip) => (
        <li key={chip.key}>
          <Tag lang={lang} onRemove={() => onChange(chip.remove)}>
            {chip.label}
          </Tag>
        </li>
      ))}
      <li>
        <Button variant="ghost" size="sm" onClick={onClear}>
          {t('archive.active.clear')}
        </Button>
      </li>
    </ul>
  );
}
