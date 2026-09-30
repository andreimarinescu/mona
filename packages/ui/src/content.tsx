import { createElement, useId, useState, type ReactNode } from 'react';
import { MonaAvatar } from './avatar';
import { Button } from './button';
import { format } from './format';
import { CLOSE, ui } from './i18n';
import { Icon } from './icon';
import type {
  AccordionProps,
  BannerProps,
  BreadcrumbsProps,
  CitationProps,
  Crumb,
  DescriptionListProps,
  EmptyStateProps,
  LinkProps,
  ListItemProps,
  ListProps,
  PaginationProps,
  ProgressProps,
  SkeletonProps,
  SourceListProps,
  SpinnerProps,
  Tone,
} from './types';
import { cx, pick } from './util';

export function Citation(props: CitationProps) {
  const label = props.label || 'Source ' + props.n;
  return props.href ? (
    <a className="mona-cite" href={props.href} aria-label={label}>
      {props.n}
    </a>
  ) : (
    <button type="button" className="mona-cite" aria-label={label} onClick={props.onClick}>
      {props.n}
    </button>
  );
}

export function SourceList(props: SourceListProps) {
  return (
    <ol className={cx('mona-sources', props.className)} aria-label={props.label || 'Sources'}>
      {(props.sources || []).map((s, i) => {
        const n = s.n || i + 1;
        return (
          <li key={n} id={s.id}>
            <span className="mona-sources__n" aria-hidden>
              {n}
            </span>
            {s.href ? (
              <a className="mona-sources__title" href={s.href}>
                {s.title}
              </a>
            ) : (
              <span className="mona-sources__title">{s.title}</span>
            )}
            {s.detail ? <span className="mona-sources__detail">{s.detail}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

export function EmptyState(props: EmptyStateProps) {
  return (
    <div className={cx('mona-empty', props.className)}>
      {props.art ? typeof props.art === 'string' ? <img className="mona-empty__art" src={props.art} alt="" /> : props.art : null}
      <h3 className="mona-empty__title">{props.title}</h3>
      {props.children ? <p className="mona-empty__body">{props.children}</p> : null}
      {props.action ? <div className="mona-empty__action">{props.action}</div> : null}
    </div>
  );
}

export function Link(props: LinkProps) {
  const { variant, external, className, children, ...rest } = props;
  const ext = external ? { target: '_blank', rel: 'noopener noreferrer' } : {};
  return (
    <a {...ext} {...rest} className={cx('mona-link', variant && 'mona-link--' + variant, className)}>
      {children}
      {external ? <Icon name="external" size={14} className="mona-link__ext" /> : null}
    </a>
  );
}

const BANNER_ICON = { neutral: 'info', info: 'info', success: 'circle-check', warning: 'alert', danger: 'alert' } as const satisfies Record<Tone, string>;

export function Banner(props: BannerProps) {
  const tone = props.tone || 'info';
  const lang = props.lang || 'en';
  return (
    <div
      className={cx('mona-banner', 'mona-banner--' + tone, props.variant === 'page' && 'mona-banner--page', props.className)}
      role={tone === 'danger' || tone === 'warning' ? 'alert' : 'status'}
    >
      <span className="mona-banner__icon">{props.from === 'mona' ? <MonaAvatar size={20} /> : <Icon name={props.icon || BANNER_ICON[tone]} size={20} />}</span>
      <div className="mona-banner__text">
        {props.title ? <div className="mona-banner__title">{props.title}</div> : null}
        {props.children ? <div className="mona-banner__msg">{props.children}</div> : null}
      </div>
      {props.actions ? <div className="mona-banner__actions">{props.actions}</div> : null}
      {props.onDismiss ? (
        <button type="button" className="mona-toast__close" aria-label={pick(CLOSE, lang)} onClick={props.onDismiss}>
          <Icon name="x" size={18} />
        </button>
      ) : null}
    </div>
  );
}

export function Progress(props: ProgressProps) {
  const lang = props.lang || 'en';
  const max = props.max || 100;
  const value = props.value;
  const pct = value == null ? null : Math.max(0, Math.min(1, value / max));
  const showValue = pct !== null && props.showValue !== false;
  return (
    <div className={cx('mona-progress', props.size === 'sm' && 'mona-progress--sm', props.className)}>
      {props.label || showValue ? (
        <div className="mona-progress__head">
          <span>{props.label}</span>
          {showValue ? <span className="mona-num">{props.valueText || format.percent(pct, lang)}</span> : null}
        </div>
      ) : null}
      <div
        className="mona-progress__track"
        role="progressbar"
        aria-label={typeof props.label === 'string' ? props.label : ui(lang, 'loading')}
        aria-valuemin={pct === null ? undefined : 0}
        aria-valuemax={pct === null ? undefined : max}
        aria-valuenow={pct === null ? undefined : value}
        aria-valuetext={props.valueText}
      >
        <div className={cx('mona-progress__bar', pct === null && 'mona-progress__bar--ind')} style={pct === null ? undefined : { width: pct * 100 + '%' }} />
      </div>
    </div>
  );
}

export function Spinner(props: SpinnerProps) {
  const lang = props.lang || 'en';
  const size = props.size || 20;
  return (
    <span className={cx('mona-spinner', props.className)} role="status">
      <Icon name="loader" size={size} spin strokeWidth={size <= 16 ? 2.4 : 2} />
      {props.label ? <span className="mona-spinner__label">{props.label}</span> : <span className="mona-sr">{ui(lang, 'loading')}</span>}
    </span>
  );
}

export function Skeleton(props: SkeletonProps) {
  const v = props.variant || 'text';
  if (v === 'text') {
    const lines = props.lines || 1;
    return (
      <div className={cx('mona-skel-lines', props.className)} aria-hidden>
        {Array.from({ length: lines }, (_, i) => (
          <span key={i} className="mona-skel mona-skel--text" style={{ width: i === lines - 1 && lines > 1 ? '62%' : props.width || '100%' }} />
        ))}
      </div>
    );
  }
  return (
    <span
      className={cx('mona-skel', 'mona-skel--' + v, props.className)}
      aria-hidden
      style={{ width: props.width || (v === 'circle' ? 40 : '100%'), height: props.height || (v === 'circle' ? props.width || 40 : 80) }}
    />
  );
}

type Shown = Crumb | { ellipsis: true };

export function Breadcrumbs(props: BreadcrumbsProps) {
  const lang = props.lang || 'en';
  const items = props.items || [];
  const max = props.maxItems || 4;
  const [expanded, setExpanded] = useState(false);
  const collapse = !expanded && items.length > max;
  const first = items[0];
  const shown: Shown[] = collapse && first ? [first, { ellipsis: true }, ...items.slice(items.length - (max - 2))] : items;
  return (
    <nav className={cx('mona-crumbs', props.className)} aria-label={props.label || ui(lang, 'crumbs')}>
      <ol>
        {shown.map((it, i) => {
          const last = i === shown.length - 1;
          return (
            <li key={i}>
              {'ellipsis' in it ? (
                <button type="button" className="mona-crumbs__more" aria-label={ui(lang, 'fullPath')} onClick={() => setExpanded(true)}>
                  …
                </button>
              ) : last ? (
                <span aria-current="page" className="mona-crumbs__current">
                  {it.label}
                </span>
              ) : (
                <a href={it.href || '#'} onClick={it.onClick} className="mona-crumbs__link">
                  {it.label}
                </a>
              )}
              {last ? null : (
                <span className="mona-crumbs__sep" aria-hidden>
                  /
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

function pageList(p: number, n: number): Array<number | '…'> {
  if (n <= 7) return Array.from({ length: n }, (_, i) => i + 1);
  const out: Array<number | '…'> = [1];
  let s = Math.max(2, p - 1);
  let e = Math.min(n - 1, p + 1);
  if (p <= 3) {
    s = 2;
    e = 4;
  }
  if (p >= n - 2) {
    s = n - 3;
    e = n - 1;
  }
  if (s > 2) out.push('…');
  for (let i = s; i <= e; i++) out.push(i);
  if (e < n - 1) out.push('…');
  out.push(n);
  return out;
}

export function Pagination(props: PaginationProps) {
  const lang = props.lang || 'en';
  const p = props.page || 1;
  const n = props.pageCount || 1;
  function go(x: number) {
    if (x >= 1 && x <= n && x !== p && props.onChange) props.onChange(x);
  }
  const range =
    props.total != null && props.pageSize
      ? ui(lang, 'range', {
          a: format.number((p - 1) * props.pageSize + 1, lang),
          b: format.number(Math.min(p * props.pageSize, props.total), lang),
          n: format.number(props.total, lang),
        })
      : null;
  return (
    <nav className={cx('mona-pages', props.className)} aria-label={props.label || ui(lang, 'page', { p, n })}>
      {range ? <span className="mona-pages__range mona-num">{range}</span> : null}
      <div className="mona-pages__ctrls">
        <Button variant="quiet" size="sm" iconOnly icon="chevron-left" aria-label={ui(lang, 'prev')} disabled={p <= 1} onClick={() => go(p - 1)} />
        {props.variant === 'compact' ? (
          <span className="mona-pages__of mona-num">{ui(lang, 'page', { p, n })}</span>
        ) : (
          pageList(p, n).map((x, i) =>
            x === '…' ? (
              <span key={'e' + i} className="mona-pages__gap" aria-hidden>
                …
              </span>
            ) : (
              <button
                key={x}
                type="button"
                className={cx('mona-pages__num', x === p && 'mona-pages__num--on')}
                aria-current={x === p ? 'page' : undefined}
                aria-label={ui(lang, 'page', { p: x, n })}
                onClick={() => go(x)}
              >
                {format.number(x, lang)}
              </button>
            ),
          )
        )}
        <Button variant="quiet" size="sm" iconOnly icon="chevron-right" aria-label={ui(lang, 'next')} disabled={p >= n} onClick={() => go(p + 1)} />
      </div>
    </nav>
  );
}

export function Accordion(props: AccordionProps) {
  const base = useId();
  const multiple = !!props.multiple;
  const [inner, setInner] = useState<string[]>(props.defaultOpen || []);
  const open = props.open || inner;
  function toggle(id: string) {
    const isOpen = open.indexOf(id) >= 0;
    const next = isOpen ? open.filter((x) => x !== id) : multiple ? open.concat([id]) : [id];
    if (!props.open) setInner(next);
    if (props.onChange) props.onChange(next);
  }
  const heading = 'h' + (props.headingLevel || 3);
  return (
    <div className={cx('mona-accordion', props.variant === 'card' && 'mona-accordion--card', props.className)}>
      {(props.items || []).map((it) => {
        const on = open.indexOf(it.id) >= 0;
        const bid = base + '-b-' + it.id;
        const pid = base + '-p-' + it.id;
        return (
          <div key={it.id} className={cx('mona-accordion__item', on && 'mona-accordion__item--open')}>
            {createElement(
              heading,
              { className: 'mona-accordion__h' },
              <button type="button" id={bid} className="mona-accordion__btn" aria-expanded={on} aria-controls={pid} onClick={() => toggle(it.id)}>
                <span className="mona-accordion__title">{it.title}</span>
                {it.meta ? <span className="mona-accordion__meta">{it.meta}</span> : null}
                <Icon name="chevron-down" size={18} className="mona-accordion__chev" />
              </button>,
            )}
            <div id={pid} role="region" aria-labelledby={bid} hidden={!on} className="mona-accordion__panel">
              {it.content}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function DescriptionList(props: DescriptionListProps) {
  const layout = props.layout || 'rows';
  return (
    <dl
      className={cx('mona-dl', 'mona-dl--' + layout, props.className)}
      style={layout === 'grid' ? { gridTemplateColumns: 'repeat(' + (props.columns || 2) + ', minmax(0, 1fr))' } : undefined}
    >
      {(props.items || []).map((it, i) => (
        <div key={i} className="mona-dl__row">
          <dt>{it.term}</dt>
          <dd className={cx(it.numeric && 'mona-num', it.mono && 'mona-dl__mono')}>{it.detail}</dd>
        </div>
      ))}
    </dl>
  );
}

export function List(props: ListProps) {
  const Root = props.ordered ? 'ol' : 'ul';
  return (
    <Root className={cx('mona-list', props.variant === 'card' && 'mona-list--card', props.dividers === false && 'mona-list--plain', props.className)} aria-label={props.label}>
      {props.children}
    </Root>
  );
}

export function ListItem(props: ListItemProps) {
  const interactive = props.href || props.onClick;
  const inner: ReactNode[] = [
    props.leading ? (
      <span key="l" className="mona-li__lead">
        {props.leading}
      </span>
    ) : null,
    <span key="t" className="mona-li__text">
      <span className="mona-li__title">{props.title}</span>
      {props.description ? <span className="mona-li__desc">{props.description}</span> : null}
    </span>,
    props.meta ? (
      <span key="m" className="mona-li__meta">
        {props.meta}
      </span>
    ) : null,
    interactive && !props.action ? <Icon key="c" name="chevron-right" size={16} className="mona-li__chev" /> : null,
  ];
  return (
    <li className={cx('mona-li', props.selected && 'mona-li--selected', props.className)}>
      {props.href ? (
        <a href={props.href} className="mona-li__hit" aria-current={props.selected ? 'page' : undefined}>
          {inner}
        </a>
      ) : props.onClick ? (
        <button type="button" className="mona-li__hit" onClick={props.onClick} aria-pressed={props.selected != null ? !!props.selected : undefined}>
          {inner}
        </button>
      ) : (
        <div className="mona-li__hit mona-li__hit--static">{inner}</div>
      )}
      {props.action ? <span className="mona-li__action">{props.action}</span> : null}
    </li>
  );
}

