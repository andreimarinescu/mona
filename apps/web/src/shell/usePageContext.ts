import { useRouterState } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { useEntities } from '../data/hooks';
import { useAppState } from '../state/context';
import { pageContext } from './pageContext';
import { pageDisplay } from './pageDisplay';

export function usePageContext() {
  const location = useRouterState({ select: (s) => s.location });
  const { scope, pageFacts } = useAppState();
  return pageContext({ pathname: location.pathname, search: location.searchStr, hash: location.hash, scope, facts: pageFacts });
}

/** The "Mona can see" line in the interface language; the model gets the English `usePageContext` summary. */
export function usePageDisplay(): string {
  const { t } = useTranslation();
  const location = useRouterState({ select: (s) => s.location });
  const { scope, pageFacts } = useAppState();
  const entities = useEntities().data ?? [];
  const { key, values } = pageDisplay({ pathname: location.pathname, search: location.searchStr, facts: pageFacts });
  const what = t(key, values);
  const entity = scope === 'all' ? undefined : entities.find((e) => e.id === scope)?.displayName;
  const scoped = !!entity && !['chat', 'settings', 'unlock', 'dev', 'unknown'].some((k) => key === `shell.seen.${k}`);
  return scoped ? t('shell.seen.filtered', { what, entity }) : what;
}
