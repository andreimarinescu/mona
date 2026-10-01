import { api } from '../api/client';
import type { EntityList, SettingsView, ShellState } from './dto';
import { get } from './http';
import type { Entity, HealthState, Settings, ShellCounts } from './types';

export interface DataProviders {
  entities(): Promise<Entity[]>;
  settings(): Promise<Settings>;
  shellCounts(): Promise<ShellCounts>;
  health(): Promise<HealthState>;
}

export const fetchEntities = () => get<EntityList>('/api/entities').then((r) => r.items);
export const fetchSettings = () => get<SettingsView>('/api/settings');

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
  return { reviewCount: s.reviewCount, queueCount: s.queue.llm + s.queue.cpu, mona: s.mona };
}

export const defaultProviders: DataProviders = { entities: fetchEntities, settings: fetchSettings, shellCounts: fetchShellCounts, health: fetchHealth };
