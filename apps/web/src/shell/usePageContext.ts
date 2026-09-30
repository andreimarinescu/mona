import { useRouterState } from '@tanstack/react-router';
import { useAppState } from '../state/context';
import { pageContext } from './pageContext';

export function usePageContext() {
  const location = useRouterState({ select: (s) => s.location });
  const { scope } = useAppState();
  return pageContext({ pathname: location.pathname, search: location.searchStr, hash: location.hash, scope });
}
