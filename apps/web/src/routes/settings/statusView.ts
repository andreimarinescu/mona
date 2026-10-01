import { format, type Lang } from '@mona/ui';
import type { TFunction } from 'i18next';
import type { SystemStatus } from '../../data/dto';

export interface Tile {
  id: 'mona' | 'model' | 'queue' | 'disk' | 'database';
  label: string;
  value: string;
  status: string;
  tone: 'ok' | 'warn' | 'bad' | 'unknown';
  detail?: string;
}

export const DISK_WARN_FRACTION = 0.1;
export const DISK_LOW_FRACTION = 0.03;

export function diskTone(free: number, total: number): Tile['tone'] {
  if (total <= 0) return 'unknown';
  const fraction = free / total;
  return fraction < DISK_LOW_FRACTION ? 'bad' : fraction < DISK_WARN_FRACTION ? 'warn' : 'ok';
}

/** C2 §15.2 as the StatusTiles of Settings › System status. Nulls are shown as "not reported", never as zero. */
export function statusTiles(s: SystemStatus, t: TFunction, lang: Lang): Tile[] {
  const n = (v: number) => format.number(v, lang);
  const online = s.mona.status === 'online';
  const waiting = s.queues.llm.todo + s.queues.llm.doing + s.queues.cpu.todo + s.queues.cpu.doing;
  const { dataFreeBytes: free, dataTotalBytes: total } = s.disk;
  const modelDetail = [s.llm.quantization, s.llm.contextPerSlot !== null && s.llm.slots !== null ? t('settings.status.model.context', { context: n(s.llm.contextPerSlot), slots: n(s.llm.slots) }) : null].filter(Boolean).join(' · ');
  return [
    {
      id: 'mona',
      label: t('settings.status.mona.label'),
      value: online ? t('settings.status.mona.online') : t('settings.status.mona.offline'),
      status: online ? t('settings.status.healthy') : t('settings.status.attention'),
      tone: online ? 'ok' : 'bad',
      detail: s.mona.hermesVersion ? t('settings.status.mona.version', { version: s.mona.hermesVersion }) : undefined,
    },
    {
      id: 'model',
      label: t('settings.status.model.label'),
      value: s.llm.model ?? t('settings.status.notReported'),
      status: s.llm.endpoint === 'local' ? t('settings.status.model.local') : t('settings.status.model.cloud'),
      tone: s.llm.model === null ? 'unknown' : s.llm.endpoint === 'local' ? 'ok' : 'warn',
      detail: modelDetail || undefined,
    },
    {
      id: 'queue',
      label: t('settings.status.queue.label'),
      value: t('settings.status.queue.waiting', { count: waiting }),
      status: waiting === 0 ? t('settings.status.queue.idle') : t('settings.status.queue.working'),
      tone: 'ok',
      detail: t('settings.status.queue.detail', { llm: n(s.queues.llm.todo + s.queues.llm.doing), cpu: n(s.queues.cpu.todo + s.queues.cpu.doing) }),
    },
    {
      id: 'disk',
      label: t('settings.status.disk.label'),
      value: t('settings.status.disk.free', { size: format.fileSize(free, lang) }),
      status: diskTone(free, total) === 'ok' ? t('settings.status.healthy') : t('settings.status.disk.low'),
      tone: diskTone(free, total),
      detail: t('settings.status.disk.of', { size: format.fileSize(total, lang) }),
    },
    {
      id: 'database',
      label: t('settings.status.database.label'),
      value: s.database === 'ok' ? t('settings.status.database.ok') : t('settings.status.database.error'),
      status: s.database === 'ok' ? t('settings.status.healthy') : t('settings.status.attention'),
      tone: s.database === 'ok' ? 'ok' : 'bad',
    },
  ];
}
