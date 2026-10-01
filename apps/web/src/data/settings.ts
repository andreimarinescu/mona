import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { SettingsPatch, SettingsView, SystemStatus } from './dto';
import { get, patch, put } from './http';

export const patchSettings = (body: SettingsPatch) => patch<SettingsView>('/api/settings', body);
export const changePassword = (body: { currentPassword: string; newPassword: string }) => put<void>('/api/auth/password', body);

export function useSystemStatus(enabled = true) {
  return useQuery({
    queryKey: ['system-status'],
    enabled,
    queryFn: ({ signal }) => get<SystemStatus>('/api/system/status', undefined, signal),
    staleTime: 30_000,
    refetchInterval: 30_000,
    retry: false,
  });
}

export function useSaveSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: SettingsPatch) => patchSettings(body),
    onSuccess: (view) => qc.setQueryData(['settings'], view),
  });
}

export interface SettingsDraft {
  profileName: string;
  practiceName: string;
  autoLockMinutes: string;
  confidenceHigh: string;
  confidenceLow: string;
  badgeHours: string;
  debriefQueueThreshold: string;
  debriefEarlyMin: string;
}

export type SettingsField = keyof SettingsDraft;

export function draftOf(view: SettingsView): SettingsDraft {
  return {
    profileName: view.profileName,
    practiceName: view.practiceName,
    autoLockMinutes: String(view.autoLockMinutes),
    confidenceHigh: String(view.confidenceHigh),
    confidenceLow: String(view.confidenceLow),
    badgeHours: String(view.badgeHours),
    debriefQueueThreshold: String(view.debriefQueueThreshold),
    debriefEarlyMin: String(view.debriefEarlyMin),
  };
}

export type SettingsErrorCode = 'name' | 'whole' | 'range' | 'order';

export const RANGES: Record<Exclude<SettingsField, 'profileName' | 'practiceName'>, [number, number]> = {
  autoLockMinutes: [1, 1440],
  confidenceHigh: [1, 100],
  confidenceLow: [1, 100],
  badgeHours: [1, 168],
  debriefQueueThreshold: [1, 50],
  debriefEarlyMin: [1, 50],
};

/** C2 §15.1 on the client: the same limits the server enforces, so a bad value never leaves the form. */
export function validateSettings(draft: SettingsDraft): Partial<Record<SettingsField, SettingsErrorCode>> {
  const errors: Partial<Record<SettingsField, SettingsErrorCode>> = {};
  for (const field of ['profileName', 'practiceName'] as const) {
    const length = draft[field].trim().length;
    if (length < 1 || length > 120) errors[field] = 'name';
  }
  for (const field of Object.keys(RANGES) as (keyof typeof RANGES)[]) {
    const raw = draft[field].trim();
    const n = Number(raw);
    if (raw === '' || !Number.isInteger(n)) {
      errors[field] = 'whole';
      continue;
    }
    const [min, max] = RANGES[field];
    if (n < min || n > max) errors[field] = 'range';
  }
  if (!errors.confidenceHigh && !errors.confidenceLow && Number(draft.confidenceLow) >= Number(draft.confidenceHigh)) errors.confidenceLow = 'order';
  return errors;
}

/** Only the fields that differ from the saved view, as numbers. */
export function settingsChanges(draft: SettingsDraft, view: SettingsView): SettingsPatch {
  const out: SettingsPatch = {};
  const saved = draftOf(view);
  if (draft.profileName.trim() !== saved.profileName) out.profileName = draft.profileName.trim();
  if (draft.practiceName.trim() !== saved.practiceName) out.practiceName = draft.practiceName.trim();
  for (const field of ['autoLockMinutes', 'confidenceHigh', 'confidenceLow', 'badgeHours', 'debriefQueueThreshold', 'debriefEarlyMin'] as const) {
    if (draft[field].trim() !== saved[field]) out[field] = Number(draft[field]);
  }
  return out;
}
