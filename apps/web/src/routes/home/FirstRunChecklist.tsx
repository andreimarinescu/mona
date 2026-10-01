import { Icon, LanguageSwitch, MonaAvatar, type Lang } from '@mona/ui';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../../components/InternalLink';
import { firstRunDone, type FirstRunState } from './firstRun';

function Row({ done, title, children, action, info = false }: { done: boolean; title: string; children: ReactNode; action?: ReactNode; info?: boolean }) {
  const { t } = useTranslation();
  return (
    <li className="flex list-none items-start gap-3 border-t border-border py-4 first:border-t-0" data-done={done ? '' : undefined}>
      <span aria-hidden className={`mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full ${done ? 'bg-success-soft text-success' : info ? 'bg-info-soft text-info' : 'border border-border-strong text-text-muted'}`}>
        <Icon name={done ? 'check' : info ? 'info' : 'clock'} size={14} strokeWidth={2.6} />
      </span>
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="font-ui text-[15px] leading-[22px] font-semibold text-text">
          {title}
          <span className="mona-sr">{done ? ` · ${t('firstRun.done')}` : info ? '' : ` · ${t('firstRun.todo')}`}</span>
        </span>
        <span className="font-ui text-[14px] leading-5 text-text-muted">{children}</span>
        {action ? <div className="pt-1">{action}</div> : null}
      </div>
    </li>
  );
}

export function FirstRunChecklist({ state, onLanguage }: { state: FirstRunState; onLanguage: (lang: Lang) => void }) {
  const { t } = useTranslation();
  const done = firstRunDone(state);
  return (
    <section aria-labelledby="first-run-title" className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-6 shadow-1" data-testid="first-run">
      <header className="flex items-center gap-3 pb-2">
        <MonaAvatar size={40} />
        <div className="flex flex-col">
          <h2 id="first-run-title" className="m-0 text-text [font:var(--type-title)]">
            {t('firstRun.title')}
          </h2>
          <p className="m-0 text-text-muted">{t('firstRun.intro')}</p>
        </div>
      </header>
      <ol className="m-0 flex flex-col p-0">
        <Row
          done={done.language}
          title={t('firstRun.language.title')}
          action={
            <LanguageSwitch label={t('settings.language.interface')} value={state.locale} onChange={onLanguage} />
          }
        >
          {t('firstRun.language.body')}
        </Row>
        <Row
          done={done.entities}
          title={t('firstRun.entities.title')}
          action={
            done.entities ? undefined : (
              <InternalLink href="/entities" className="mona-btn mona-btn--secondary no-underline">
                {t('firstRun.entities.action')}
              </InternalLink>
            )
          }
        >
          {done.entities ? t('firstRun.entities.done', { count: state.entities }) : t('firstRun.entities.body')}
        </Row>
        <Row done={done.archive} title={t('firstRun.archive.title')} info>
          {t('firstRun.archive.body')}
        </Row>
        <Row
          done={done.documents}
          title={t('firstRun.documents.title')}
          action={
            <InternalLink href="/intake" className="mona-btn mona-btn--primary no-underline">
              {t('firstRun.documents.action')}
            </InternalLink>
          }
        >
          {t('firstRun.documents.body')}
        </Row>
        <Row done={false} info title={t('firstRun.telegram.title')}>
          {state.telegram ? t('firstRun.telegram.linked') : t('firstRun.telegram.body')}
        </Row>
      </ol>
    </section>
  );
}
