import { Avatar, AvatarGroup, DescriptionList, Icon, format } from '@mona/ui';
import { useTranslation } from 'react-i18next';
import type { Entity, PersonDetail } from '../../data/dto';
import { useLang } from '../../shell/useLang';
import { fiscalYearEndText, formatSiren, monogram, personLine } from './entityView';

export interface EntityCardProps {
  entity: Entity;
  documentCount: number;
  people: PersonDetail[];
  /** Set for the Visitors entity (C2 §8 `visitorsEntityId`): shown as the visitors' holding area, not as a practice entity. */
  visitors?: { purgeAfterHours: number | null };
}

export function EntityCard({ entity, documentCount, people, visitors }: EntityCardProps) {
  const { t } = useTranslation();
  const lang = useLang();
  const named = personLine(entity, people);
  const kind = visitors ? 'visitors' : entity.visibility;
  const items = visitors
    ? []
    : [
        { term: t('entities.card.siren'), detail: entity.siren ? formatSiren(entity.siren) : t('entities.card.notApplicable'), mono: true },
        { term: t('entities.card.accounts'), detail: entity.accounts.length > 0 ? <span className="flex flex-col gap-1">{entity.accounts.map((a) => <span key={a.id}>{a.label} <span className="whitespace-nowrap">•••• {a.ibanLast4}</span></span>)}</span> : t('entities.card.none'), mono: entity.accounts.length > 0 },
        { term: t('entities.card.fiscalYear'), detail: fiscalYearEndText(entity.fiscalYearEnd, lang) },
        { term: t('entities.card.subUnits'), detail: entity.subUnits.length > 0 ? entity.subUnits.map((s) => s.label).join(' · ') : t('entities.card.none') },
      ];
  return (
    <article aria-label={entity.displayName} data-testid="entity-card" data-entity-id={entity.id} data-kind={kind} className="flex min-w-0 flex-col gap-4 rounded-lg border border-border bg-surface p-5 shadow-1">
      <header className="flex items-start gap-3">
        <span aria-hidden className="inline-flex size-12 shrink-0 items-center justify-center rounded-t-full rounded-b-md bg-surface-sunken text-text [font:var(--type-voice)] text-[18px]">
          {monogram(entity.displayName)}
        </span>
        <div className="flex min-w-0 flex-1 flex-col">
          <h3 className="m-0 text-text [font:var(--type-heading)]">{entity.displayName}</h3>
          <span className="font-ui text-[13px] leading-[18px] text-text-muted">{visitors ? t('entities.card.visitorsRole') : [entity.legalForm, t('entities.card.documents', { count: documentCount, n: format.number(documentCount, lang) })].filter(Boolean).join(' · ')}</span>
        </div>
      </header>
      {visitors ? (
        <p className="m-0 text-text-muted" data-testid="visitors-note">
          {visitors.purgeAfterHours ? t('entities.card.visitorsNote', { count: visitors.purgeAfterHours }) : t('entities.card.visitorsNoteNoHours')}
        </p>
      ) : (
        <DescriptionList items={items} layout="rows" />
      )}
      {kind === 'personal' ? <p className="m-0 font-ui text-[13px] leading-[18px] text-text-muted">{t('entities.card.personalNote')}</p> : null}
      <footer className="mt-auto flex flex-wrap items-center gap-3 border-t border-border pt-3">
        {named.length > 0 ? (
          <>
            {named.length > 1 ? <AvatarGroup people={named.map((p) => ({ name: p.name }))} size={28} lang={lang} /> : <Avatar name={named[0]!.name} size={28} />}
            <span className="min-w-0 flex-1 font-ui text-[13px] leading-[18px] text-text-muted">{named.map((p) => (p.role ? `${p.name}, ${p.role}` : p.name)).join(' · ')}</span>
          </>
        ) : (
          <span className="flex-1" />
        )}
        <span
          data-visibility={kind}
          className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 font-ui text-[13px] leading-[18px] font-semibold ${kind === 'personal' ? 'border-danger bg-danger-soft text-danger' : kind === 'visitors' ? 'border-warning bg-warning-soft text-warning' : 'border-border bg-surface-sunken text-text'}`}
        >
          <Icon name={kind === 'personal' ? 'lock' : kind === 'visitors' ? 'clock' : 'folder'} size={13} />
          {t(`entities.card.visibility.${kind}`)}
        </span>
      </footer>
    </article>
  );
}
