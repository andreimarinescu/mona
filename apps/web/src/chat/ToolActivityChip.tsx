import { Icon } from '@mona/ui';
import { useTranslation } from 'react-i18next';

export type ToolState = 'running' | 'done' | 'interrupted';

/** C3 §4.5: the label comes from `chat.tool.<toolName>`, or the generic pair for any other tool. */
export function ToolActivityChip({ toolName, state }: { toolName: string; state: ToolState }) {
  const { t, i18n } = useTranslation();
  const key = i18n.exists(`chat.tool.${toolName}.done`) ? toolName : 'generic';
  const label = t(`chat.tool.${key}.${state === 'done' ? 'done' : 'running'}`);
  return (
    <span
      data-testid="tool-chip"
      data-tool={toolName}
      data-live={state === 'running'}
      data-state={state}
      className={`inline-flex min-h-9 items-center gap-2 rounded-full border bg-surface px-3 font-ui text-[14px] leading-5 ${
        state === 'running' ? 'border-dashed border-info text-info' : 'border-border text-text'
      }`}
    >
      <Icon name={state === 'running' ? 'loader' : state === 'done' ? 'check' : 'alert'} spin={state === 'running'} size={16} />
      {state === 'interrupted' ? `${label.replace(/…$/, '')} · ${t('chat.tool.interrupted')}` : label}
    </span>
  );
}
