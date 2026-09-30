import type { Lang } from '@mona/ui';
import { api } from '../api/client';
import { entitiesFixture, settingsFixture } from './fixtures';
import type { ShellState } from './dto';
import { get } from './http';
import type { Entity, HealthState, Settings, ShellCounts } from './types';

export interface DataProviders {
  entities(): Promise<Entity[]>;
  settings(): Promise<Settings>;
  shellCounts(): Promise<ShellCounts>;
  health(): Promise<HealthState>;
}

export const LANGUAGE_OVERRIDE_KEY = 'mona.stub.language';

function overrideLanguage(): Lang | null {
  const v = globalThis.localStorage?.getItem(LANGUAGE_OVERRIDE_KEY);
  return v === 'en' || v === 'fr' || v === 'ro' ? v : null;
}

export const stubProviders = {
  entities: async () => entitiesFixture,
  settings: async () => ({ ...settingsFixture, locale: overrideLanguage() ?? settingsFixture.locale }),
} satisfies Partial<DataProviders>;

const OFFLINE: HealthState = { status: 'offline', version: null };

export async function fetchHealth(): Promise<HealthState> {
  try {
    const { data, error } = await api.GET('/api/health');
    const body = data ?? (error && typeof error === 'object' && 'status' in error ? error : undefined);
    if (!body) return OFFLINE;
    return { status: body.status === 'ok' && body.db === 'ok' ? 'ok' : 'degraded', version: body.version };
  } catch {
    return OFFLINE;
  }
}

export async function fetchShellCounts(): Promise<ShellCounts> {
  const s = await get<ShellState>('/api/shell');
  return { reviewCount: s.reviewCount, queueCount: s.queue.llm + s.queue.cpu };
}

export const defaultProviders: DataProviders = { ...stubProviders, shellCounts: fetchShellCounts, health: fetchHealth };
