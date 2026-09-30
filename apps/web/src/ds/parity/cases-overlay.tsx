import { useState, type ReactNode } from 'react';
import { combos, label, type Case, type Log, type Mona } from './harness';

function ModalHarness({ M, log, kind, extra, persistentScrim }: { M: Mona; log: Log; kind: 'Dialog' | 'Drawer'; extra?: Record<string, unknown>; persistentScrim?: boolean }) {
  const [open, setOpen] = useState(!!extra?.startOpen);
  const Modal = M[kind]!;
  const { Button, Input } = M as Record<string, any>;
  return (
    <div>
      <Button onClick={() => setOpen(true)}>Open</Button>
      <Modal
        open={open}
        title="Delete this document?"
        onClose={
          extra?.noClose
            ? undefined
            : () => {
                log.fn('onClose')();
                setOpen(false);
              }
        }
        footer={extra?.noFooter ? undefined : <Button variant="danger">Confirm</Button>}
        {...Object.fromEntries(Object.entries(extra ?? {}).filter(([k]) => !['startOpen', 'noClose', 'noFooter'].includes(k)))}
      >
        <Input label="Reason" data-autofocus={persistentScrim ? '' : undefined} />
        <a href="#x">Link</a>
      </Modal>
    </div>
  );
}

function TooltipHarness({ M, extra }: { M: Mona; extra?: Record<string, unknown> }) {
  const T = M.Tooltip!;
  return (
    <T content="Helpful text" {...extra}>
      <button type="button">Hover me</button>
    </T>
  );
}

function PopoverHarness({ M, log, render, extra }: { M: Mona; log: Log; render: 'element' | 'function'; extra?: Record<string, unknown> }) {
  const P = M.Popover!;
  const trigger =
    render === 'element' ? (
      <button type="button">Trigger</button>
    ) : (
      ({ open, toggle, id }: { open: boolean; toggle: () => void; id: string }) => (
        <button type="button" aria-expanded={open} aria-controls={id} onClick={toggle}>
          Trigger
        </button>
      )
    );
  return (
    <P trigger={trigger} label="Filters" onOpenChange={log.fn('onOpenChange')} {...extra}>
      {(api: { close: () => void }) => (
        <div>
          <button type="button" onClick={api.close}>
            Inside
          </button>
        </div>
      )}
    </P>
  );
}

function ControlledPopover({ M, log }: { M: Mona; log: Log }) {
  const [open, setOpen] = useState(false);
  const P = M.Popover!;
  return (
    <div>
      <button type="button" onClick={() => setOpen(!open)}>
        Outside toggle
      </button>
      <P
        open={open}
        onOpenChange={(v: boolean) => {
          log.fn('onOpenChange')(v);
          setOpen(v);
        }}
        trigger={<button type="button">Trigger</button>}
      >
        <p>Static content</p>
      </P>
    </div>
  );
}

const MENU_ITEMS = (log: Log) => [
  { type: 'label', label: 'Document' },
  { id: 'open', label: 'Open', icon: 'file', shortcut: '⏎', onSelect: log.fn('select') },
  { id: 'copy', label: 'Copy name', icon: 'copy', onSelect: log.fn('select') },
  { type: 'separator' },
  { id: 'move', label: 'Move…', disabled: true, onSelect: log.fn('select') },
  { id: 'delete', label: 'Delete', icon: 'trash', danger: true, onSelect: log.fn('select') },
];

function MenuHarness({ M, log, extra }: { M: Mona; log: Log; extra?: Record<string, unknown> }) {
  const Menu = M.Menu!;
  const { Button } = M as Record<string, any>;
  return <Menu label="Actions" items={MENU_ITEMS(log)} trigger={<Button variant="secondary">Actions</Button>} onOpenChange={log.fn('onOpenChange')} {...extra} />;
}

const wrap = (name: string, ui: (M: Mona, log: Log) => ReactNode, steps?: Case['steps']): Case => ({ name, ui: (M, log) => <>{ui(M, log)}</>, steps });

export const overlay: Record<string, Case[]> = {
  Dialog: [
    ...combos({ open: [false, true], extra: [{}, { size: 'wide' }, { tone: 'danger' }, { persistent: true }, { className: 'k', lang: 'fr' }, { lang: 'ro', noClose: true }, { noFooter: true }] }).map((p) =>
      wrap(label(p), (M, log) => <ModalHarness M={M} log={log} kind="Dialog" extra={{ ...p.extra, startOpen: p.open }} />),
    ),
    wrap('open, tab cycle, escape restores focus', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" extra={{ tone: 'danger' }} />, async ({ user, screen, snap, log }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      snap();
      for (let i = 0; i < 5; i++) {
        await user.tab();
        snap();
      }
      await user.tab({ shift: true });
      snap();
      await user.keyboard('{Escape}');
      snap();
      void log;
    }),
    wrap('close button', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      await user.click(screen.getByRole('button', { name: 'Close' }));
      snap();
    }),
    wrap('scrim click closes, inner click does not', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" />, async ({ user, screen, snap, fireEvent }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      const dlg = screen.getByRole('dialog');
      fireEvent.mouseDown(dlg);
      snap();
      fireEvent.mouseDown(dlg.parentElement!);
      snap();
    }),
    wrap('persistent ignores scrim but honours escape', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" extra={{ persistent: true }} />, async ({ user, screen, snap, fireEvent }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      fireEvent.mouseDown(screen.getByRole('dialog').parentElement!);
      snap();
      await user.keyboard('{Escape}');
    }),
    wrap('data-autofocus wins', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" persistentScrim />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      snap();
    }),
    wrap('no onClose: escape inert', (M, log) => <ModalHarness M={M} log={log} kind="Dialog" extra={{ noClose: true }} />, async ({ user, screen }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      await user.keyboard('{Escape}');
    }),
  ],
  Drawer: [
    ...combos({ open: [false, true], extra: [{}, { side: 'bottom' }, { side: 'right', className: 'k' }, { lang: 'fr' }, { noClose: true }, { noFooter: true }] }).map((p) =>
      wrap(label(p), (M, log) => <ModalHarness M={M} log={log} kind="Drawer" extra={{ ...p.extra, startOpen: p.open }} />),
    ),
    wrap('open, tab, escape', (M, log) => <ModalHarness M={M} log={log} kind="Drawer" />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      snap();
      await user.tab();
      await user.tab();
      await user.tab();
      snap();
      await user.keyboard('{Escape}');
      snap();
    }),
    wrap('scrim click closes drawer even if persistent prop', (M, log) => <ModalHarness M={M} log={log} kind="Drawer" extra={{ persistent: true }} />, async ({ user, screen, snap, fireEvent }) => {
      await user.click(screen.getByRole('button', { name: 'Open' }));
      fireEvent.mouseDown(screen.getByRole('dialog').parentElement!);
      snap();
    }),
  ],
  Tooltip: [
    wrap('closed', (M) => <TooltipHarness M={M} />),
    wrap('defaultOpen', (M) => <TooltipHarness M={M} extra={{ defaultOpen: true }} />),
    wrap('bottom side open', (M) => <TooltipHarness M={M} extra={{ side: 'bottom', defaultOpen: true }} />),
    wrap('hover shows and hides', (M) => <TooltipHarness M={M} extra={{ side: 'bottom' }} />, async ({ user, screen, snap }) => {
      await user.hover(screen.getByRole('button'));
      snap();
      await user.unhover(screen.getByRole('button'));
      snap();
    }),
    wrap('focus shows, escape hides, blur', (M) => <TooltipHarness M={M} />, async ({ user, snap }) => {
      await user.tab();
      snap();
      await user.keyboard('{Escape}');
      snap();
      await user.tab();
      snap();
    }),
    wrap('defaultOpen survives leave and blur', (M) => <TooltipHarness M={M} extra={{ defaultOpen: true }} />, async ({ user, screen, snap }) => {
      await user.hover(screen.getByRole('button'));
      await user.unhover(screen.getByRole('button'));
      snap();
      await user.keyboard('{Escape}');
    }),
  ],
  Popover: [
    ...combos({ render: ['element', 'function'], extra: [{}, { placement: 'bottom-end' }, { placement: 'top-start' }, { placement: 'top-end', width: 240, className: 'k' }, { matchWidth: true }] }).map((p) =>
      wrap(label(p), (M, log) => <PopoverHarness M={M} log={log} render={p.render as 'element' | 'function'} extra={p.extra} />, async ({ user, screen, snap }) => {
        await user.click(screen.getByRole('button', { name: 'Trigger' }));
        snap();
      }),
    ),
    wrap('closed initially', (M, log) => <PopoverHarness M={M} log={log} render="element" />),
    wrap('toggle, inside close', (M, log) => <PopoverHarness M={M} log={log} render="element" />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      await user.click(screen.getByRole('button', { name: 'Inside' }));
      snap();
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      snap();
    }),
    wrap('outside click closes', (M, log) => <PopoverHarness M={M} log={log} render="function" />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      await user.click(document.body);
      snap();
    }),
    wrap('escape closes and refocuses trigger', (M, log) => <PopoverHarness M={M} log={log} render="element" />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      await user.click(screen.getByRole('button', { name: 'Inside' }));
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      await user.keyboard('{Escape}');
      snap();
    }),
    wrap('controlled open via outside toggle', (M, log) => <ControlledPopover M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Outside toggle' }));
      snap();
      await user.click(screen.getByRole('button', { name: 'Trigger' }));
      snap();
      await user.click(document.body);
      snap();
    }),
  ],
  Menu: [
    ...combos({ extra: [{}, { placement: 'bottom-end' }, { placement: 'top-start' }, { label: undefined }] }).map((p) =>
      wrap(label(p.extra), (M, log) => <MenuHarness M={M} log={log} extra={p.extra} />, async ({ user, screen, snap }) => {
        await user.click(screen.getByRole('button', { name: 'Actions' }));
        snap();
      }),
    ),
    wrap('closed', (M, log) => <MenuHarness M={M} log={log} />),
    wrap('arrow navigation wraps', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      for (const k of ['{ArrowDown}', '{ArrowDown}', '{ArrowDown}', '{ArrowUp}', '{End}', '{Home}', '{ArrowUp}']) {
        await user.keyboard(k);
        snap();
      }
    }),
    wrap('typeahead', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.keyboard('c');
      snap();
      await user.keyboard('d');
      snap();
      await user.keyboard('o');
      snap();
      await user.keyboard('z');
      snap();
    }),
    wrap('click item selects and closes', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.click(screen.getByRole('menuitem', { name: 'Copy name' }));
      snap();
    }),
    wrap('disabled item ignored', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.click(screen.getByRole('menuitem', { name: /Move/ }));
      snap();
    }),
    wrap('enter and space select', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.keyboard('{Enter}');
      snap();
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.keyboard('{ArrowDown}{ }');
      snap();
    }),
    wrap('tab closes', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.keyboard('{Tab}');
      snap();
    }),
    wrap('escape closes', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.keyboard('{Escape}');
      snap();
    }),
    wrap('outside click closes', (M, log) => <MenuHarness M={M} log={log} />, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Actions' }));
      await user.click(document.body);
      snap();
    }),
  ],
};

