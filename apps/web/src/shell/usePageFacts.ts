import { useEffect } from 'react';
import { useAppState } from '../state/context';
import type { PageFacts } from './pageContext';

/** Publishes what a screen shows to the chat panel's page context for as long as it is mounted. */
export function usePublishPageFacts(facts: PageFacts | null) {
  const { setPageFacts } = useAppState();
  const key = JSON.stringify(facts);
  useEffect(() => {
    setPageFacts(JSON.parse(key) as PageFacts | null);
    return () => setPageFacts(null);
  }, [key, setPageFacts]);
}
