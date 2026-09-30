import type { Lang } from '@mona/ui';
import type { components } from '../api/client';

export type Health = components['schemas']['Health'];

export interface HealthState {
  status: 'ok' | 'degraded' | 'offline';
  version: string | null;
}

/** C1 §11.8 Entity. */
export interface Entity {
  id: string;
  key: string;
  displayName: string;
  folderName: string;
  legalForm: string | null;
  siren: string | null;
  visibility: 'practice' | 'personal';
  fiscalYearEnd: string;
  filingLanguage: Lang | null;
  subUnits: { id: string; key: string; label: string; personId: string | null }[];
  people: { personId: string; role: string | null }[];
  accounts: { id: string; key: string; label: string; ibanLast4: string; subUnitId: string | null }[];
}

/** The profile and settings the shell needs (C1 §8). */
export interface Settings {
  locale: Lang;
  profileName: string;
  practiceName: string;
}

export interface ShellCounts {
  reviewCount: number;
  queueCount: number;
}
