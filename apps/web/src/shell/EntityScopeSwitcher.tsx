import { Select } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import { useEntities } from '../data/hooks';
import { useAppState } from '../state/context';

export function EntityScopeSwitcher() {
  const { t } = useTranslation();
  const { scope, setScope } = useAppState();
  const entities = useEntities().data ?? [];
  return (
    <Select
      label={t('shell.scope.label')}
      value={scope}
      onChange={(e) => setScope(e.target.value)}
      options={[{ value: 'all', label: t('shell.scope.all') }, ...entities.map((e) => ({ value: e.id, label: e.displayName }))]}
    />
  );
}
