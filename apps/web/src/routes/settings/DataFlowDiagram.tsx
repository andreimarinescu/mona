import { Icon } from '@mona/ui';
import { useTranslation } from 'react-i18next';

export interface DataFlowProps {
  cloudAi: boolean;
  telegram: boolean;
  visitorHours: number;
}

function Box({ tone, icon, title, children, testId }: { tone: 'stays' | 'telegram' | 'export' | 'cloud'; icon: 'lock' | 'send' | 'download' | 'alert'; title: string; children: React.ReactNode; testId: string }) {
  const styles = {
    stays: 'border-success bg-success-soft',
    telegram: 'border-warning border-dashed bg-warning-soft',
    export: 'border-border-strong bg-surface-raised',
    cloud: 'border-danger border-dashed bg-danger-soft',
  }[tone];
  return (
    <div className={`flex flex-col gap-2 rounded-lg border p-4 ${styles}`} data-testid={testId}>
      <h3 className="m-0 flex items-center gap-2 font-ui text-[15px] leading-[22px] font-semibold text-text">
        <Icon name={icon} size={16} />
        {title}
      </h3>
      {children}
    </div>
  );
}

/** The Privacy section: what stays on this computer, what passes through Telegram, what leaves only when you export. */
export function DataFlowDiagram({ cloudAi, telegram, visitorHours }: DataFlowProps) {
  const { t } = useTranslation();
  const stays = [t('settings.privacy.stays.documents'), cloudAi ? null : t('settings.privacy.stays.thinking'), t('settings.privacy.stays.index'), t('settings.privacy.stays.visitors', { count: visitorHours })].filter(Boolean);
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]" data-testid="data-flow">
      <Box tone="stays" icon="lock" title={t('settings.privacy.stays.title')} testId="flow-stays">
        <ul className="m-0 flex list-disc flex-col gap-1 pl-5 font-ui text-[14px] leading-5 text-text">
          {stays.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      </Box>
      <div className="flex flex-col gap-4">
        {cloudAi ? (
          <Box tone="cloud" icon="alert" title={t('settings.privacy.cloud.title')} testId="flow-cloud">
            <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('settings.privacy.cloud.body')}</p>
          </Box>
        ) : null}
        {telegram ? (
          <Box tone="telegram" icon="send" title={t('settings.privacy.telegram.title')} testId="flow-telegram">
            <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('settings.privacy.telegram.body')}</p>
            <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('settings.privacy.telegram.personal')}</p>
          </Box>
        ) : null}
        <Box tone="export" icon="download" title={t('settings.privacy.export.title')} testId="flow-export">
          <p className="m-0 font-ui text-[14px] leading-5 text-text">{t('settings.privacy.export.body')}</p>
        </Box>
      </div>
    </div>
  );
}
