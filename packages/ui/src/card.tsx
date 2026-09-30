import { createElement, type ElementType, type Key, type ReactNode } from 'react';
import { MonaAvatar } from './avatar';
import { StatusPill } from './status';
import type { CardProps, TableProps } from './types';
import { cx } from './util';

export function Card(props: CardProps) {
  const interactive = !!props.onClick;
  const root = (props.as || (props.title ? 'article' : 'section')) as ElementType;
  const head =
    props.from === 'mona' || props.status || props.meta ? (
      <div className="mona-card__head">
        {props.from === 'mona' ? <MonaAvatar size={40} state={props.avatarState} /> : null}
        <div className="mona-card__who">
          {props.from === 'mona' ? (
            <span className="mona-card__name">Mona</span>
          ) : props.eyebrow ? (
            <span className="mona-card__eyebrow">{props.eyebrow}</span>
          ) : null}
          {props.meta ? <span className="mona-card__meta">{props.meta}</span> : null}
        </div>
        {props.status ? typeof props.status === 'string' ? <StatusPill status={props.status} lang={props.lang} /> : props.status : null}
      </div>
    ) : null;
  return createElement(
    root,
    {
      className: cx('mona-card', props.variant === 'flat' && 'mona-card--flat', interactive && 'mona-card--interactive', props.className),
      onClick: props.onClick,
      style: props.style,
    },
    head,
    !head && props.eyebrow ? <span className="mona-card__eyebrow">{props.eyebrow}</span> : null,
    props.title ? <h3 className="mona-card__title">{props.title}</h3> : null,
    props.voice ? (
      <p className="mona-card__voice" lang={props.lang}>
        {props.voice}
      </p>
    ) : null,
    props.children ? <div className="mona-card__body">{props.children}</div> : null,
    props.actions ? <div className="mona-card__actions">{props.actions}</div> : null,
    props.footer ? <div className="mona-card__foot">{props.footer}</div> : null,
  );
}

export function Table<R extends object = Record<string, unknown>>(props: TableProps<R>) {
  const cols = props.columns || [];
  const rows = props.rows || [];
  const numeric = (c: { numeric?: boolean }) => (c.numeric ? '' : undefined);
  const align = (c: { align?: 'start' | 'end' }) => (c.align === 'end' ? 'end' : undefined);
  return (
    <div className={cx('mona-table-wrap', props.className)} style={props.maxHeight ? { maxHeight: props.maxHeight } : undefined}>
      <table className="mona-table">
        {props.caption ? <caption>{props.caption}</caption> : null}
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c.key} scope="col" data-numeric={numeric(c)} data-align={align(c)}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={props.rowKey ? ((r as Record<string, unknown>)[props.rowKey] as Key) : i}>
              {cols.map((c) => (
                <td key={c.key} data-numeric={numeric(c)} data-align={align(c)}>
                  {c.render ? c.render(r) : ((r as Record<string, unknown>)[c.key] as ReactNode)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {props.footer ? (
          <tfoot>
            <tr>
              {cols.map((c) => (
                <td key={c.key} data-numeric={numeric(c)} data-align={align(c)}>
                  {props.footer?.[c.key]}
                </td>
              ))}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  );
}
