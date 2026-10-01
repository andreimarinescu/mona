import type { Lang } from '@mona/ui';

export interface FirstRunState {
  locale: Lang;
  entities: number;
  documents: number;
  telegram: boolean | null;
}

export type FirstRunStep = 'language' | 'entities' | 'archive' | 'documents';

/** The steps the person can still do: language is always a choice; entities and documents are done once something exists; the archive folder is informational. */
export function firstRunDone(state: FirstRunState): Record<FirstRunStep, boolean> {
  return { language: true, entities: state.entities > 0, archive: true, documents: state.documents > 0 };
}
