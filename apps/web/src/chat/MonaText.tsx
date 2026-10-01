import { Citation, SourceList } from '@mona/ui';
import { useRouter } from '@tanstack/react-router';
import { Fragment, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { InternalLink } from '../components/InternalLink';
import type { DocumentSummary } from '../data/dto';
import { CITATION } from './citations';

function bold(text: string, key: string): ReactNode[] {
  return text.split(/(\*\*[^*\n]+\*\*)/g).map((piece, i) =>
    /^\*\*[^*\n]+\*\*$/.test(piece) ? <strong key={`${key}-${i}`}>{piece.slice(2, -2)}</strong> : <Fragment key={`${key}-${i}`}>{piece}</Fragment>,
  );
}

export interface MonaTextProps {
  text: string;
  streaming: boolean;
  docs: DocumentSummary[];
  lang?: string;
}

/** Mona's words, with `Citation`s for `[n]` markers and a caret while the part streams (`StreamingText`). */
export function MonaText({ text, streaming, docs, lang }: MonaTextProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const pieces: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(CITATION)) {
    const n = Number(m[1]);
    const doc = docs[n - 1];
    if (!doc) continue;
    pieces.push(...bold(text.slice(last, m.index), `t${last}`));
    pieces.push(<Citation key={`c${m.index}`} n={n} label={t('chat.citation', { n, title: doc.title })} onClick={() => router.history.push(`/documents/${doc.id}`)} />);
    last = m.index + m[0].length;
  }
  pieces.push(...bold(text.slice(last), `t${last}`));
  return (
    <p data-testid="mona-text" data-streaming={streaming || undefined} lang={lang} className="m-0 font-ui text-[17px] leading-[27px] whitespace-pre-wrap text-text">
      {pieces}
      {streaming ? <span aria-hidden className="mona-caret ml-0.5 inline-block h-[1.1em] w-[2px] translate-y-[3px] bg-accent" /> : null}
    </p>
  );
}

export function CitedSources({ docs, cited }: { docs: DocumentSummary[]; cited: number[] }) {
  const { t } = useTranslation();
  const used = [...new Set(cited)].sort((a, b) => a - b);
  if (used.length === 0) return null;
  return (
    <SourceList
      label={t('chat.sources')}
      sources={used.map((n) => ({
        n,
        title: (
          <InternalLink href={`/documents/${docs[n - 1]!.id}`} className="text-text underline">
            {docs[n - 1]!.title}
          </InternalLink>
        ),
        detail: docs[n - 1]!.entityName ?? undefined,
      }))}
    />
  );
}
