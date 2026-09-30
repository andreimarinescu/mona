import { Icon, format } from '@mona/ui';
import { Link } from '@tanstack/react-router';
import { useTranslation } from 'react-i18next';
import { useHealth, useShellCounts } from '../data/hooks';
import { useLang } from './useLang';

export function SystemStatusLine() {
  const { t } = useTranslation();
  const lang = useLang();
  const health = useHealth().data;
  const queue = useShellCounts().data?.queueCount ?? 0;
  const offline = health !== undefined && health.status !== 'ok';
  const text = offline
    ? t('shell.status.offline')
    : health
      ? `${t('shell.status.ok')} · ${t('shell.status.queue', { n: format.number(queue, lang) })}`
      : t('shell.status.checking');
  return (
    <Link
      to="/settings"
      hash="status"
      className="flex min-h-11 items-center gap-2 no-underline rounded-md px-3 font-ui text-[13px] leading-[18px] text-text-muted hover:bg-surface-sunken"
      data-status={health?.status ?? 'checking'}
    >
      <Icon name={offline ? 'alert' : 'hard-drive'} size={16} />
      <span>{text}</span>
    </Link>
  );
}
