import { SearchField, SegmentedControl, Select } from '@mona/ui';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ActivityFilters as Filters } from '../../data/journal';
import { useEntityList } from '../../data/registry';
import { useLang } from '../../shell/useLang';
import { KINDS } from './kinds';


const SEARCH_DELAY_MS = 300;

export function ActivityFilters({ value, onChange }: { value: Filters; onChange(next: Filters): void }) {
  const { t } = useTranslation();
  const lang = useLang();
  const entities = useEntityList().data?.items ?? [];
  const [text, setText] = useState(value.q ?? '');
  const latest = useRef({ value, onChange });
  useEffect(() => {
    latest.current = { value, onChange };
  });
  useEffect(() => {
    const timer = setTimeout(() => {
      const { value: current, onChange: emit } = latest.current;
      const q = text.trim() || undefined;
      if (q !== current.q) emit({ ...current, q });
    }, SEARCH_DELAY_MS);
    return () => clearTimeout(timer);
  }, [text]);

  return (
    <div className="flex flex-wrap items-end gap-3" role="search" aria-label={t('activity.filters.label')}>
      <SegmentedControl
        label={t('activity.filters.actor')}
        value={value.actor ?? 'all'}
        onChange={(actor) => onChange({ ...value, actor: actor === 'all' ? undefined : (actor as 'mona' | 'user') })}
        options={[
          { value: 'all', label: t('activity.filters.all') },
          { value: 'mona', label: t('activity.filters.mona') },
          { value: 'user', label: t('activity.filters.user') },
        ]}
      />
      <Select
        aria-label={t('activity.filters.entity')}
        value={value.entityId ?? ''}
        onChange={(e) => onChange({ ...value, entityId: e.target.value || undefined })}
        options={[{ value: '', label: t('shell.scope.all') }, ...entities.map((e) => ({ value: e.id, label: e.displayName }))]}
      />
      <Select
        aria-label={t('activity.filters.kind')}
        value={value.kind ?? ''}
        onChange={(e) => onChange({ ...value, kind: e.target.value || undefined })}
        options={[{ value: '', label: t('activity.filters.allKinds') }, ...KINDS.map((k) => ({ value: k, label: t(`activity.kind.${k}`) }))]}
      />
      <div className="min-w-[240px] flex-1 lg:max-w-[360px] lg:ml-auto">
        <SearchField value={text} onChange={setText} label={t('activity.filters.search')} placeholder={t('activity.filters.search')} lang={lang} />
      </div>
    </div>
  );
}
