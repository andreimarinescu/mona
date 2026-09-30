import { combos, label, simple, type Case } from './harness';

const LANGS = ['en', 'fr', 'ro'] as const;
const TONES = ['neutral', 'info', 'success', 'warning', 'danger'] as const;
const CATEGORIES = ['bank', 'invoice', 'tax', 'insurance', 'payroll', 'training', 'travel', 'personal'] as const;
export const BUNDLE_ICONS = [
  'chevron-left', 'chevron-right', 'more', 'pencil', 'copy', 'download', 'filter', 'check', 'circle-check', 'help', 'loader', 'file-x', 'file', 'folder', 'x',
  'chevron-down', 'undo', 'sun', 'moon', 'monitor', 'info', 'alert', 'bell', 'search', 'arrow-right', 'trash', 'calendar', 'lock', 'external', 'send', ...CATEGORIES,
] as const;

const SOURCES = [
  { title: 'URSSAF notice', detail: 'p. 2', href: '#s1', id: 'src-1' },
  { title: 'Bank statement', detail: 'March' },
  { n: 7, title: 'Invoice 42' },
];

export const core: Record<string, Case[]> = {
  Button: [
    ...combos({
      variant: ['primary', 'secondary', 'ghost', 'quiet', 'danger'],
      size: ['md', 'sm'],
      extra: [{}, { icon: 'check' }, { iconEnd: 'chevron-down' }, { icon: 'send', iconEnd: 'arrow-right' }, { loading: true }, { disabled: true }, { iconOnly: true, icon: 'more', 'aria-label': 'More' }, { className: 'extra', type: 'submit', 'data-k': 'v', title: 't' }],
    }).map((p) => simple(label(p), 'Button', { ...p.extra, variant: p.variant, size: p.size, children: 'Save' })),
    simple('no variant given', 'Button', { children: 'Plain' }),
    simple('click logs', 'Button', { onClick: '$fn', children: 'Go' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
    simple('loading blocks click', 'Button', { onClick: '$fn', loading: true, children: 'Go' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
    simple('disabled blocks click', 'Button', { onClick: '$fn', disabled: true, children: 'Go' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
  ],
  Tabs: [
    ...combos({ extra: [{}, { defaultValue: 'b' }, { value: 'c', onChange: '$fn' }, { label: 'Sections', className: 'k' }] }).map((p) =>
      simple(label(p.extra), 'Tabs', { ...p.extra, tabs: [{ id: 'a', label: 'All', count: 12, panelId: 'pa' }, { id: 'b', label: 'Review', count: 0 }, { id: 'c', label: 'Filed' }] }),
    ),
    simple('keyboard navigation', 'Tabs', { label: 'S', tabs: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }, { id: 'c', label: 'C' }], onChange: '$fn' }, async ({ user, screen, snap }) => {
      screen.getByRole('tab', { name: 'A' }).focus();
      for (const k of ['{ArrowRight}', '{ArrowRight}', '{ArrowRight}', '{ArrowLeft}', '{End}', '{Home}', '{ArrowLeft}']) {
        await user.keyboard(k);
        snap();
      }
    }),
    simple('click selects', 'Tabs', { tabs: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('tab', { name: 'B' }));
    }),
    simple('controlled click keeps value', 'Tabs', { value: 'a', tabs: [{ id: 'a', label: 'A' }, { id: 'b', label: 'B' }], onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('tab', { name: 'B' }));
    }),
  ],
  StatusPill: [
    ...combos({ status: ['filed', 'review', 'processing', 'unreadable'], lang: LANGS, extra: [{}, { size: 'sm' }, { label: 'Custom', className: 'k' }, { compact: true }, { compact: true, size: 'sm' }] }).map((p) =>
      simple(label(p), 'StatusPill', { ...p.extra, status: p.status, lang: p.lang }),
    ),
    simple('default status', 'StatusPill', {}),
    simple('compact tooltip on hover', 'StatusPill', { status: 'review', compact: true, lang: 'fr' }, async ({ user, screen, snap }) => {
      await user.hover(screen.getByRole('img'));
      snap();
      await user.unhover(screen.getByRole('img'));
    }),
    simple('compact tooltip on focus and escape', 'StatusPill', { status: 'filed', compact: true }, async ({ user, snap }) => {
      await user.tab();
      snap();
      await user.keyboard('{Escape}');
      snap();
      await user.tab();
    }),
  ],
  ConfidenceMeter: [
    ...combos({ value: [0, 0.04, 0.1, 0.3, 0.59, 0.6, 0.61, 0.84, 0.85, 0.9, 1, 4, 42, 59, 60, 84, 85, 100, 150], lang: LANGS, extra: [{}, { hideLabel: true }, { hideWord: true, className: 'k' }] }).map((p) =>
      simple(label(p), 'ConfidenceMeter', { ...p.extra, value: p.value, lang: p.lang }),
    ),
    simple('no value', 'ConfidenceMeter', { value: undefined }),
  ],
  Card: [
    ...combos({
      extra: [
        {},
        { title: 'Three documents filed' },
        { title: 'T', voice: 'I filed it.', lang: 'fr' },
        { from: 'mona', title: 'T', eyebrow: 'Today', meta: '09:14' },
        { from: 'mona', avatarState: 'thinking', status: 'review', title: 'T' },
        { eyebrow: 'Eyebrow', meta: 'meta', status: 'filed', lang: 'ro' },
        { eyebrow: 'Eyebrow only' },
        { title: 'T', actions: <button>Do</button>, footer: <span>Foot</span> },
        { variant: 'flat', className: 'k', style: { width: 200 } },
        { as: 'div', title: 'T' },
        { status: <span>custom</span> },
      ],
      kids: [null, 'Body text'],
    }).map((p) => simple(label({ ...p.extra, kids: p.kids }), 'Card', { ...p.extra, children: p.kids })),
    simple('interactive click', 'Card', { title: 'T', onClick: '$fn', children: 'B' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('heading'));
    }),
  ],
  Table: [
    simple('basic', 'Table', { columns: [{ key: 'a', label: 'A' }, { key: 'b', label: 'B', numeric: true }], rows: [{ a: 'x', b: 1 }, { a: 'y', b: 2 }] }),
    simple('render, align, caption, footer, rowKey, maxHeight, className', 'Table', {
      columns: [{ key: 'name', label: 'Name', render: (r: { name: string }) => <b>{r.name}</b> }, { key: 'amt', label: 'Amount', numeric: true, align: 'end' }],
      rows: [{ id: 'r1', name: 'One', amt: '1,00' }, { id: 'r2', name: 'Two', amt: '2,00' }],
      caption: 'Ledger',
      footer: { name: 'Total', amt: '3,00' },
      rowKey: 'id',
      maxHeight: 120,
      className: 'k',
    }),
    simple('maxHeight string', 'Table', { columns: [{ key: 'a', label: 'A' }], rows: [{ a: 1 }], maxHeight: '10rem' }),
    simple('empty rows', 'Table', { columns: [{ key: 'a', label: 'A' }], rows: [] }),
    simple('footer partial', 'Table', { columns: [{ key: 'a', label: 'A' }, { key: 'b', label: 'B' }], rows: [{ a: 1, b: 2 }], footer: { b: 'sum' } }),
  ],
  Toast: [
    ...combos({ tone: TONES, extra: [{}, { from: 'mona' }, { message: 'Details here', className: 'k' }, { action: { label: 'Undo', icon: 'undo', onClick: () => {} }, onClose: () => {} }], lang: LANGS }).map((p) =>
      simple(label({ ...p, extra: Object.keys(p.extra).join('+') }), 'Toast', { ...p.extra, tone: p.tone, lang: p.lang, title: 'Filed 12 documents' }),
    ),
    simple('no tone', 'Toast', { title: 'Plain' }),
    simple('action and close click', 'Toast', { title: 'T', action: { label: 'Undo', onClick: '$fn' }, onClose: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'Undo' }));
      await user.click(screen.getByRole('button', { name: 'Close' }));
      snap();
    }),
  ],
  ToastStack: [
    simple('plain', 'ToastStack', { children: <div>child</div> }),
    simple('inline', 'ToastStack', { inline: true }),
  ],
  MonaAvatar: combos({ size: [20, 28, 32, 40, 56, 18, 100, undefined], state: ['idle', 'thinking', 'offline', undefined], extra: [{}, { label: 'Assistant', className: 'k' }] }).map((p) =>
    simple(label(p), 'MonaAvatar', { ...p.extra, size: p.size, state: p.state }),
  ),
  Avatar: [
    ...combos({ name: ['Léa Marchand', 'Dr. Jean Dupont', 'Madonna', 'mme Ana Popescu', '', 'Ionescu Dent SRL'], extra: [{}, { size: 24 }, { size: 56, showTitle: true }, { tone: 'umber', className: 'k' }, { src: 'x.png' }] }).map((p) =>
      simple(label(p), 'Avatar', { ...p.extra, name: p.name }),
    ),
    simple('image error falls back', 'Avatar', { name: 'Léa Marchand', src: 'broken.png' }, async ({ screen, fireEvent, snap }) => {
      fireEvent.error(document.querySelector('img')!);
      snap();
      void screen;
    }),
  ],
  AvatarGroup: [
    ...combos({ n: [0, 1, 3, 4, 7], extra: [{}, { max: 2 }, { size: 40, label: 'People', className: 'k' }], lang: LANGS }).map((p) =>
      simple(label(p), 'AvatarGroup', { ...p.extra, lang: p.lang, people: Array.from({ length: p.n }, (_, i) => ({ name: `Person Number${i}`, src: i === 1 ? 'x.png' : undefined })) }),
    ),
  ],
  Citation: [
    simple('button', 'Citation', { n: 3, onClick: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
    simple('link', 'Citation', { n: 3, href: '#s' }),
    simple('labelled', 'Citation', { n: 1, label: 'Source: URSSAF' }),
  ],
  SourceList: [
    simple('sources', 'SourceList', { sources: SOURCES }),
    simple('labelled', 'SourceList', { sources: SOURCES, label: 'Sources utilisées', className: 'k' }),
    simple('empty', 'SourceList', { sources: [] }),
  ],
  EmptyState: [
    simple('title only', 'EmptyState', { title: 'Nothing here' }),
    simple('with art string, body, action', 'EmptyState', { art: '/art.svg', title: 'T', children: 'Body', action: <button>Go</button>, className: 'k' }),
    simple('with art node', 'EmptyState', { art: <svg data-art="1" />, title: 'T' }),
  ],
  Icon: [
    ...BUNDLE_ICONS.map((name) => simple(name, 'Icon', { name })),
    ...combos({ extra: [{ size: 24 }, { strokeWidth: 1.5 }, { label: 'Search' }, { spin: true, className: 'k' }, { size: 0 }] }).map((p) => simple(label(p.extra), 'Icon', { name: 'search', ...p.extra })),
    simple('unknown name falls back to file', 'Icon', { name: 'nope' }),
  ],
  CategoryIcon: [
    ...combos({ category: CATEGORIES, lang: LANGS }).map((p) => simple(label(p), 'CategoryIcon', p)),
    ...combos({ extra: [{ size: 56 }, { iconSize: 30 }, { label: 'Custom' }, { showTitle: true }] }).map((p) => simple(label(p.extra), 'CategoryIcon', { category: 'tax', ...p.extra })),
  ],
  Link: [
    ...combos({ variant: ['inline', 'standalone', 'muted', undefined], extra: [{}, { external: true }, { className: 'k', target: '_self' }] }).map((p) =>
      simple(label(p), 'Link', { ...p.extra, variant: p.variant, href: '#x', children: 'Open' }),
    ),
  ],
  Banner: [
    ...combos({ tone: [...TONES, undefined], extra: [{}, { title: 'Offline' }, { title: 'T', actions: <button>Retry</button>, onDismiss: () => {} }, { from: 'mona', variant: 'page' }, { icon: 'bell', className: 'k' }], lang: ['en', 'fr'] }).map((p) =>
      simple(label({ ...p, extra: Object.keys(p.extra).join('+') }), 'Banner', { ...p.extra, tone: p.tone, lang: p.lang, children: 'Message body' }),
    ),
    simple('dismiss', 'Banner', { title: 'T', onDismiss: '$fn', lang: 'ro' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
  ],
  Progress: [
    ...combos({ value: [undefined, 0, 25, 100, 150, -5], extra: [{}, { label: 'Reading' }, { label: <b>Node</b>, valueText: '3 of 12' }, { showValue: false, label: 'L' }, { size: 'sm', max: 10, className: 'k' }], lang: LANGS }).map((p) =>
      simple(label({ ...p, extra: JSON.stringify(p.extra) }), 'Progress', { ...p.extra, value: p.value, lang: p.lang }),
    ),
  ],
  Spinner: combos({ size: [16, 20, 24, 32, undefined], extra: [{}, { label: 'Loading docs' }, { className: 'k' }], lang: LANGS }).map((p) => simple(label(p), 'Spinner', { ...p.extra, size: p.size, lang: p.lang })),
  Skeleton: [
    ...combos({ variant: ['text', 'rect', 'circle', undefined], extra: [{}, { lines: 3 }, { width: 120, height: 30 }, { width: '50%', className: 'k' }] }).map((p) => simple(label(p), 'Skeleton', { ...p.extra, variant: p.variant })),
  ],
  Badge: [
    ...combos({ tone: [...TONES, 'accent', undefined], extra: [{ children: 'New' }, { count: 3 }, { count: 120 }, { count: 120, max: 9, label: 'Lots' }, { count: 0 }, { children: 'X', className: 'k' }] }).map((p) =>
      simple(label(p), 'Badge', { ...p.extra, tone: p.tone }),
    ),
  ],
  Tag: [
    ...combos({ extra: [{}, { icon: 'calendar' }, { selected: true }, { selected: true, icon: 'calendar' }, { size: 'sm', className: 'k' }, { onRemove: () => {} }, { onRemove: () => {}, size: 'sm', lang: 'fr' }, { onToggle: () => {} }, { onToggle: () => {}, selected: true, icon: 'tag' }] }).map((p) =>
      simple(label({ ...p.extra, hasFn: 1 }), 'Tag', { ...p.extra, children: 'URSSAF' }),
    ),
    simple('remove click', 'Tag', { children: 'URSSAF', onRemove: '$fn', lang: 'ro' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
    simple('remove with node child', 'Tag', { children: <i>x</i>, onRemove: '$fn' }),
    simple('toggle click', 'Tag', { children: 'FY', onToggle: '$fn', selected: false }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
  ],
  Breadcrumbs: [
    ...combos({ n: [1, 2, 4, 5, 8], extra: [{}, { maxItems: 3 }, { maxItems: 6, label: 'Path', className: 'k' }], lang: LANGS }).map((p) =>
      simple(label(p), 'Breadcrumbs', { ...p.extra, lang: p.lang, items: Array.from({ length: p.n }, (_, i) => ({ label: `Level ${i}`, href: i % 2 ? `#l${i}` : undefined })) }),
    ),
    simple('expand ellipsis', 'Breadcrumbs', { items: Array.from({ length: 7 }, (_, i) => ({ label: `L${i}`, onClick: () => {} })) }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button'));
      snap();
    }),
  ],
  Pagination: [
    ...combos({ page: [1, 2, 3, 4, 5, 7, 9, 10], pageCount: [1, 7, 10], extra: [{}, { total: 195, pageSize: 20 }, { variant: 'compact' }, { label: 'Pages', className: 'k' }], lang: LANGS }).map((p) =>
      simple(label(p), 'Pagination', { ...p.extra, page: p.page, pageCount: p.pageCount, lang: p.lang }),
    ),
    simple('next prev and number clicks', 'Pagination', { page: 3, pageCount: 9, onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button', { name: 'Next page' }));
      await user.click(screen.getByRole('button', { name: 'Previous page' }));
      await user.click(screen.getByRole('button', { name: 'Page 4 of 9' }));
      await user.click(screen.getByRole('button', { name: 'Page 3 of 9' }));
    }),
    simple('first page prev disabled', 'Pagination', { page: 1, pageCount: 3, onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button', { name: 'Previous page' }));
    }),
    simple('defaults', 'Pagination', {}),
  ],
  Accordion: [
    ...combos({ extra: [{}, { multiple: true, defaultOpen: ['a', 'b'] }, { defaultOpen: ['a'], variant: 'card' }, { headingLevel: 2, className: 'k' }, { open: ['b'], onChange: '$fn' }, { headingLevel: 6 }] }).map((p) =>
      simple(label(p.extra), 'Accordion', { ...p.extra, items: [{ id: 'a', title: 'First', content: 'Alpha', meta: '2' }, { id: 'b', title: 'Second', content: <p>Beta</p> }] }),
    ),
    simple('single mode click', 'Accordion', { items: [{ id: 'a', title: 'First', content: 'A' }, { id: 'b', title: 'Second', content: 'B' }], onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'First' }));
      snap();
      await user.click(screen.getByRole('button', { name: 'Second' }));
      snap();
      await user.click(screen.getByRole('button', { name: 'Second' }));
    }),
    simple('multiple mode click', 'Accordion', { multiple: true, items: [{ id: 'a', title: 'First', content: 'A' }, { id: 'b', title: 'Second', content: 'B' }], onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('button', { name: 'First' }));
      await user.click(screen.getByRole('button', { name: 'Second' }));
      snap();
    }),
    simple('controlled click keeps state', 'Accordion', { open: [], items: [{ id: 'a', title: 'First', content: 'A' }], onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button', { name: 'First' }));
    }),
  ],
  DescriptionList: [
    ...combos({ layout: ['rows', 'stacked', 'grid', undefined], extra: [{}, { columns: 3 }, { className: 'k' }] }).map((p) =>
      simple(label(p), 'DescriptionList', { ...p.extra, layout: p.layout, items: [{ term: 'Amount', detail: '1 284,00 €', numeric: true }, { term: 'IBAN', detail: 'FR76 0000', mono: true }, { term: 'Note', detail: <i>hi</i> }] }),
    ),
  ],
  List: [
    ...combos({ extra: [{}, { variant: 'card' }, { dividers: false }, { ordered: true, label: 'Steps' }, { className: 'k' }] }).map((p) => simple(label(p.extra), 'List', { ...p.extra, children: [<li key="a">One</li>, <li key="b">Two</li>] })),
  ],
  ListItem: [
    ...combos({ extra: [{ title: 'Plain' }, { title: 'T', description: 'D', leading: <i>L</i>, meta: 'M' }, { title: 'Link', href: '#x' }, { title: 'Link sel', href: '#x', selected: true }, { title: 'Btn', onClick: () => {} }, { title: 'Btn sel', onClick: () => {}, selected: true }, { title: 'Btn unsel', onClick: () => {}, selected: false }, { title: 'Act', href: '#', action: <button>x</button> }, { title: 'Cls', className: 'k', selected: true }] }).map((p) =>
      simple(label({ ...p.extra, hasFn: 1 }), 'ListItem', p.extra),
    ),
    simple('button click', 'ListItem', { title: 'Btn', onClick: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('button'));
    }),
  ],
  Stack: [
    ...combos({ extra: [{}, { gap: 2 }, { gap: '1.5rem' }, { gap: 0 }, { align: 'center', justify: 'between' }, { align: 'start' }, { as: 'section', className: 'k', style: { color: 'red', gap: '3px' }, id: 'st' }, { 'aria-label': 'x', 'data-q': '1' }] }).map((p) =>
      simple(label(p.extra), 'Stack', { ...p.extra, children: [<span key="a">a</span>, <span key="b">b</span>] }),
    ),
  ],
  Inline: [
    ...combos({ extra: [{}, { gap: 4 }, { align: 'baseline', justify: 'end' }, { wrap: false }, { wrap: true, as: 'nav' }, { className: 'k', style: { padding: 1 } }] }).map((p) =>
      simple(label(p.extra), 'Inline', { ...p.extra, children: [<span key="a">a</span>, <span key="b">b</span>] }),
    ),
  ],
  Grid: [
    ...combos({ extra: [{}, { columns: 3 }, { minItemWidth: 200 }, { minItemWidth: '12rem', gap: 6 }, { align: 'stretch', className: 'k', as: 'ul' }, { minItemWidth: 0, columns: 4 }] }).map((p) =>
      simple(label(p.extra), 'Grid', { ...p.extra, children: [<span key="a">a</span>, <span key="b">b</span>] }),
    ),
  ],
  Container: [
    ...combos({ size: ['sm', 'md', 'lg', 'xl', 'full', undefined], extra: [{}, { padded: false }, { as: 'main', className: 'k', style: { color: 'red' }, id: 'c' }] }).map((p) =>
      simple(label(p), 'Container', { ...p.extra, size: p.size, children: 'body' }),
    ),
  ],
  LanguageSwitch: [
    simple('default', 'LanguageSwitch', {}),
    simple('value and label and class', 'LanguageSwitch', { value: 'fr', label: 'Lang', className: 'k' }),
    simple('defaultValue', 'LanguageSwitch', { defaultValue: 'ro' }),
    simple('click changes', 'LanguageSwitch', { onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('radio', { name: 'Français' }));
      snap();
      await user.click(screen.getByRole('radio', { name: 'Română' }));
    }),
    simple('arrows', 'LanguageSwitch', { onChange: '$fn' }, async ({ user, screen, snap }) => {
      screen.getByRole('radio', { name: 'English' }).focus();
      for (const k of ['{ArrowRight}', '{ArrowDown}', '{ArrowRight}', '{ArrowLeft}', '{ArrowUp}']) {
        await user.keyboard(k);
        snap();
      }
    }),
    simple('controlled click keeps value', 'LanguageSwitch', { value: 'en', onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('radio', { name: 'Français' }));
      snap();
    }),
  ],
  ThemeToggle: [
    ...combos({ extra: [{}, { showLabels: true }, { system: false }, { value: 'dark' }, { defaultValue: 'light', className: 'k' }], lang: LANGS }).map((p) => simple(label(p), 'ThemeToggle', { ...p.extra, lang: p.lang })),
    simple('click and arrows', 'ThemeToggle', { onChange: '$fn', lang: 'fr' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('radio', { name: 'Clair' }));
      snap();
      await user.keyboard('{ArrowRight}');
      snap();
      await user.keyboard('{ArrowRight}');
    }),
  ],
  SegmentedControl: [
    ...combos({ extra: [{}, { value: 'b' }, { defaultValue: 'c', className: 'k' }, { iconOnly: true }] }).map((p) =>
      simple(label(p.extra), 'SegmentedControl', { label: 'View', options: [{ value: 'a', label: 'List', icon: 'folder' }, { value: 'b', label: 'Grid', icon: 'file' }, { value: 'c', label: 'Table' }], ...p.extra }),
    ),
    simple('click and arrows', 'SegmentedControl', { label: 'View', options: [{ value: 'a', label: 'List' }, { value: 'b', label: 'Grid' }], onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('radio', { name: 'Grid' }));
      snap();
      await user.keyboard('{ArrowRight}');
      snap();
    }),
    simple('controlled click', 'SegmentedControl', { label: 'View', value: 'a', options: [{ value: 'a', label: 'List' }, { value: 'b', label: 'Grid' }], onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('radio', { name: 'Grid' }));
    }),
  ],
};
