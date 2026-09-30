import { combos, label, simple, type Case } from './harness';

const LANGS = ['en', 'fr', 'ro'] as const;
const OPTIONS = [
  { value: 'tax', label: 'Tax' },
  { value: 'bank', label: 'Bank' },
  { value: 'pay', label: 'Payroll' },
];
const GROUPED = [{ label: 'Practice', options: OPTIONS.slice(0, 2) }, { label: 'Personal', options: OPTIONS.slice(2) }, { value: 'x', label: 'Other' }];
const COMBO = [
  { value: 'a', label: 'Alpha', group: 'Greek' },
  { value: 'b', label: 'Bêta', group: 'Greek', description: 'second letter' },
  { value: 'c', label: 'Charlie', group: 'Phonetic' },
  { value: 'd', label: 'Delta', disabled: true },
  { value: 'e', label: 'Écho' },
];

export const forms: Record<string, Case[]> = {
  Input: [
    ...combos({
      extra: [{}, { label: 'Supplier' }, { label: 'Supplier', hint: 'As printed' }, { label: 'Supplier', error: 'Required' }, { label: 'Supplier', optional: 'optional' }, { icon: 'search', placeholder: 'Find' }],
      more: [{}, { defaultValue: 'URSSAF', className: 'wide', id: 'fixed-id' }, { disabled: true, type: 'email', 'data-x': '1' }],
    }).map((p) => simple(label({ ...p.extra, ...p.more }), 'Input', { ...p.extra, ...p.more })),
    simple('typing uncontrolled', 'Input', { label: 'Name', onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.type(screen.getByLabelText('Name'), 'abc');
      snap();
    }),
    simple('controlled readonly', 'Input', { label: 'Name', value: 'fixed', readOnly: true, onChange: '$fn' }),
  ],
  Select: [
    ...combos({
      extra: [{}, { label: 'Category' }, { label: 'Category', hint: 'Pick' }, { label: 'Category', error: 'Invalid', optional: 'optional' }, { placeholder: 'Choose', defaultValue: '' }],
      options: [OPTIONS, GROUPED],
    }).map((p) => simple(label({ ...p.extra, n: p.options.length }), 'Select', { ...p.extra, options: p.options })),
    simple('select option', 'Select', { label: 'Category', options: OPTIONS, onChange: '$fn' }, async ({ user, screen }) => {
      await user.selectOptions(screen.getByLabelText('Category'), 'bank');
    }),
  ],
  FormField: [
    simple('element child', 'FormField', { label: 'L', hint: 'h', children: <input /> }),
    simple('element child with id', 'FormField', { label: 'L', error: 'bad', optional: true, lang: 'fr', children: <input id="mine" /> }),
    simple('optional string', 'FormField', { label: 'L', optional: 'maybe', className: 'c', id: 'ff', children: <input /> }),
    simple('optional ro', 'FormField', { label: 'L', optional: true, lang: 'ro', children: <input /> }),
    simple('no label', 'FormField', { hint: 'only hint', children: <input /> }),
    {
      name: 'function child',
      ui: (M) => {
        const F = M.FormField!;
        return <F label="L" error="bad">{(a: Record<string, unknown>) => <input data-a={JSON.stringify(a)} {...a} />}</F>;
      },
    },
  ],
  Checkbox: [
    ...combos({
      extra: [{}, { label: 'Agree' }, { label: 'Agree', description: 'Details' }, { label: 'Agree', error: true }, { label: 'Agree', disabled: true }, { label: 'Agree', indeterminate: true }, { label: 'Agree', defaultChecked: true, className: 'k', id: 'cb' }],
    }).map((p) => simple(label(p.extra), 'Checkbox', p.extra)),
    simple('click toggles', 'Checkbox', { label: 'Agree', onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByLabelText('Agree'));
      snap();
      await user.click(screen.getByLabelText('Agree'));
    }),
    simple('indeterminate then controlled', 'Checkbox', { label: 'Agree', indeterminate: true, checked: true, onChange: '$fn' }),
  ],
  RadioGroup: [
    ...combos({
      variant: ['default', 'cards'],
      orientation: ['vertical', 'horizontal'],
      extra: [{}, { legend: 'Scope', hint: 'Pick one' }, { legend: 'Scope', error: 'Required', defaultValue: 'b' }],
    }).map((p) =>
      simple(label(p), 'RadioGroup', {
        ...p.extra,
        variant: p.variant,
        orientation: p.orientation,
        options: [
          { value: 'a', label: 'Just this one', description: 'One document', meta: '1' },
          { value: 'b', label: 'Every document', meta: '12' },
          { value: 'c', label: 'Nothing', disabled: true },
        ],
      }),
    ),
    simple('click changes', 'RadioGroup', { legend: 'Scope', name: 'scope', options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }], onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByLabelText('B'));
      snap();
      await user.click(screen.getByLabelText('A'));
    }),
    simple('controlled ignores clicks', 'RadioGroup', { value: 'a', options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }], onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByLabelText('B'));
    }),
    simple('keyboard arrows', 'RadioGroup', { options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }, { value: 'c', label: 'C' }], defaultValue: 'a', onChange: '$fn' }, async ({ user, screen, snap }) => {
      screen.getByLabelText('A').focus();
      await user.keyboard('{ArrowDown}');
      snap();
      await user.keyboard('{ArrowDown}');
    }),
  ],
  Switch: [
    ...combos({ extra: [{}, { description: 'Explained' }, { disabled: true }, { defaultChecked: true }, { checked: true, onChange: '$fn' }, { className: 'k', id: 'sw' }] }).map((p) =>
      simple(label(p.extra), 'Switch', { label: 'Notify me', ...p.extra }),
    ),
    simple('toggle twice', 'Switch', { label: 'Notify me', onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('switch'));
      snap();
      await user.click(screen.getByRole('switch'));
    }),
    simple('disabled click', 'Switch', { label: 'Notify me', disabled: true, onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('switch'));
    }),
    simple('controlled click', 'Switch', { label: 'Notify me', checked: false, onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('switch'));
    }),
  ],
  Textarea: [
    ...combos({
      extra: [{}, { label: 'Note' }, { label: 'Note', hint: 'Short', maxLength: 50 }, { label: 'Note', maxLength: 50, showCount: false }, { label: 'Note', error: 'Too long', optional: true }, { defaultValue: 'hello', rows: 2, autoResize: true }],
      lang: LANGS,
    }).map((p) => simple(label(p), 'Textarea', { ...p.extra, lang: p.lang })),
    simple('typing with count', 'Textarea', { label: 'Note', maxLength: 20, onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.type(screen.getByLabelText('Note'), 'hello');
      snap();
    }),
    simple('controlled', 'Textarea', { label: 'Note', value: 'fixed', maxLength: 20, onChange: '$fn' }, async ({ user, screen }) => {
      await user.type(screen.getByLabelText('Note'), 'x');
    }),
  ],
  SearchField: [
    ...combos({ extra: [{}, { label: 'Find docs', placeholder: 'Type' }, { size: 'sm', defaultValue: 'abc' }, { className: 'k', value: 'ctl', onChange: '$fn' }], lang: LANGS }).map((p) =>
      simple(label(p), 'SearchField', { ...p.extra, lang: p.lang }),
    ),
    simple('type enter escape clear', 'SearchField', { onChange: '$fn', onSearch: '$fn' }, async ({ user, screen, snap }) => {
      const box = screen.getByRole('searchbox');
      await user.type(box, 'tax');
      snap();
      await user.keyboard('{Enter}');
      await user.keyboard('{Escape}');
      snap();
      await user.type(box, 'bank');
      await user.click(screen.getByRole('button'));
      snap();
    }),
  ],
  FileInput: [
    ...combos({ extra: [{}, { label: 'Documents', hint: 'PDF', accept: '.pdf', acceptLabel: 'PDF only' }, { label: 'Doc', error: 'Too big', optional: true, multiple: true }], lang: LANGS }).map((p) =>
      simple(label(p), 'FileInput', { ...p.extra, lang: p.lang }),
    ),
    simple('upload two files multiple, remove one', 'FileInput', { label: 'Docs', multiple: true, onFiles: '$fn', lang: 'fr' }, async ({ user, screen, snap }) => {
      const input = document.querySelector<HTMLInputElement>('input[type=file]')!;
      await user.upload(input, [new File(['a'], 'a.pdf'), new File(['bb'], 'b.pdf')]);
      snap();
      await user.click(screen.getAllByRole('button')[0]!);
      snap();
    }),
    simple('single file replaces', 'FileInput', { label: 'Doc', onFiles: '$fn' }, async ({ user, snap }) => {
      const input = document.querySelector<HTMLInputElement>('input[type=file]')!;
      await user.upload(input, new File(['a'], 'a.pdf'));
      snap();
      await user.upload(input, new File(['bbbb'], 'b.pdf'));
    }),
    simple('drag and drop', 'FileInput', { label: 'Doc', multiple: true, onFiles: '$fn' }, async ({ fireEvent, screen, snap }) => {
      const drop = screen.getByText(/Drop files here/).closest('label')!;
      fireEvent.dragOver(drop);
      snap();
      fireEvent.drop(drop, { dataTransfer: { files: [new File(['xyz'], 'dropped.pdf')] } });
      snap();
      fireEvent.dragOver(drop);
      fireEvent.dragLeave(drop);
    }),
  ],
  Combobox: [
    ...combos({
      extra: [{}, { label: 'Category', hint: 'Pick' }, { label: 'Category', error: 'Nope', optional: true }, { 'aria-label': 'cat', placeholder: 'Type…', className: 'k' }, { disabled: true, 'aria-label': 'cat' }, { defaultValue: 'b', 'aria-label': 'cat' }],
      multiple: [false, true],
    }).map((p) => simple(label(p), 'Combobox', { ...p.extra, multiple: p.multiple, options: COMBO, defaultValue: p.multiple ? ['a', 'c'] : (p.extra as { defaultValue?: string }).defaultValue })),
    simple('single: open, arrows, enter', 'Combobox', { 'aria-label': 'cat', options: COMBO, onChange: '$fn' }, async ({ user, screen, snap }) => {
      const box = screen.getByRole('combobox');
      await user.click(box);
      snap();
      await user.keyboard('{ArrowDown}{ArrowDown}');
      snap();
      await user.keyboard('{Enter}');
      snap();
      await user.keyboard('{ArrowDown}');
      snap();
      await user.keyboard('{Escape}');
    }),
    simple('single: filter with accents, empty', 'Combobox', { 'aria-label': 'cat', options: COMBO, emptyText: 'Nothing', lang: 'fr' }, async ({ user, screen, snap }) => {
      const box = screen.getByRole('combobox');
      await user.type(box, 'echo');
      snap();
      await user.clear(box);
      await user.type(box, 'zzz');
      snap();
    }),
    simple('single: click option and outside', 'Combobox', { label: 'Category', options: COMBO, onChange: '$fn' }, async ({ user, screen, snap }) => {
      await user.click(screen.getByRole('combobox'));
      await user.click(screen.getByRole('option', { name: /Charlie/ }));
      snap();
      await user.click(screen.getByRole('combobox'));
      await user.click(document.body);
      snap();
      await user.click(screen.getByRole('combobox'));
      await user.click(screen.getByRole('option', { name: /Delta/ }));
    }),
    simple('multiple: choose, toggle off, backspace', 'Combobox', { 'aria-label': 'cat', multiple: true, options: COMBO, onChange: '$fn' }, async ({ user, screen, snap }) => {
      const box = screen.getByRole('combobox');
      await user.click(box);
      await user.click(screen.getByRole('option', { name: /Alpha/ }));
      snap();
      await user.click(screen.getByRole('option', { name: /Charlie/ }));
      snap();
      await user.click(screen.getByRole('option', { name: /Alpha/ }));
      snap();
      await user.keyboard('{Backspace}');
      snap();
    }),
    simple('multiple: remove tag', 'Combobox', { 'aria-label': 'cat', multiple: true, defaultValue: ['a', 'b'], options: COMBO, onChange: '$fn', lang: 'ro' }, async ({ user, screen, snap }) => {
      await user.click(screen.getAllByRole('button')[0]!);
      snap();
    }),
    simple('controlled single', 'Combobox', { 'aria-label': 'cat', value: 'a', options: COMBO, onChange: '$fn' }, async ({ user, screen }) => {
      await user.click(screen.getByRole('combobox'));
      await user.click(screen.getByRole('option', { name: /Charlie/ }));
    }),
  ],
};

