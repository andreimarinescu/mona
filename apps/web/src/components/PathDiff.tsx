import { useTranslation } from 'react-i18next';

function changedSegments(from: string[], to: string[]): { from: boolean[]; to: boolean[] } {
  return {
    from: from.map((seg, i) => seg !== to[i]),
    to: to.map((seg, i) => seg !== from[i]),
  };
}

function Segments({ parts, changed, kind }: { parts: string[]; changed: boolean[]; kind: 'del' | 'ins' }) {
  return (
    <>
      {parts.map((part, i) => {
        const sep = i > 0 ? <span aria-hidden> / </span> : null;
        if (!changed[i]) {
          return (
            <span key={i}>
              {sep}
              {part}
            </span>
          );
        }
        const Tag = kind;
        return (
          <span key={i}>
            {sep}
            <Tag className={kind === 'del' ? 'rounded-xs bg-danger-soft px-1 line-through decoration-danger' : 'rounded-xs bg-success-soft px-1 font-semibold no-underline'}>{part}</Tag>
          </span>
        );
      })}
    </>
  );
}

export interface PathDiffProps {
  from: string[];
  to: string[];
  fromFileName?: string;
  toFileName?: string;
}

export function PathDiff({ from, to, fromFileName, toFileName }: PathDiffProps) {
  const { t } = useTranslation();
  const changed = changedSegments(from, to);
  return (
    <div className="flex flex-col gap-1 font-ui text-[14px] leading-5 text-text" data-testid="path-diff">
      <span>
        <Segments parts={from} changed={changed.from} kind="del" />
      </span>
      <span className="mona-sr">{t('rules.preview.becomes')}</span>
      <span aria-hidden className="text-text-muted">
        ↓
      </span>
      <span>
        <Segments parts={to} changed={changed.to} kind="ins" />
      </span>
      {toFileName ? (
        <span className="text-text-muted [font:var(--type-filename)]">{fromFileName && fromFileName !== toFileName ? `${fromFileName} → ${toFileName}` : toFileName}</span>
      ) : null}
    </div>
  );
}
