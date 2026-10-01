import type { components } from '../api/client';

export type Health = components['schemas']['Health'];

export interface HealthState {
  status: 'ok' | 'degraded' | 'offline';
  version: string | null;
}

import type { SettingsView } from './dto';

export type { Entity } from './dto';

export type Settings = SettingsView;

export interface ShellCounts {
  reviewCount: number;
  queueCount: number;
  mona: 'online' | 'offline';
}
