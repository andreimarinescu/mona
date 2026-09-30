/* @ds-bundle: {"format":4,"namespace":"Mona","components":[{"name":"Button"},{"name":"Input"},{"name":"Select"},{"name":"Tabs"},{"name":"StatusPill"},{"name":"ConfidenceMeter"},{"name":"Card"},{"name":"Table"},{"name":"Toast"},{"name":"ToastStack"},{"name":"Dialog"},{"name":"Drawer"},{"name":"Tooltip"},{"name":"MonaAvatar"},{"name":"LanguageSwitch"},{"name":"ThemeToggle"},{"name":"Citation"},{"name":"SourceList"},{"name":"EmptyState"},{"name":"Icon"},{"name":"CategoryIcon"},{"name":"FormField"},{"name":"Checkbox"},{"name":"RadioGroup"},{"name":"Switch"},{"name":"Textarea"},{"name":"SegmentedControl"},{"name":"Combobox"},{"name":"SearchField"},{"name":"FileInput"},{"name":"Link"},{"name":"Popover"},{"name":"Menu"},{"name":"Banner"},{"name":"Progress"},{"name":"Spinner"},{"name":"Skeleton"},{"name":"Badge"},{"name":"Tag"},{"name":"Breadcrumbs"},{"name":"Pagination"},{"name":"Accordion"},{"name":"Avatar"},{"name":"AvatarGroup"},{"name":"DescriptionList"},{"name":"List"},{"name":"ListItem"},{"name":"Stack"},{"name":"Inline"},{"name":"Grid"},{"name":"Container"}]} */
/* Mona components. Plain React 18 (window.React / window.ReactDOM), no JSX, no build step.
   Styles: components/bundle.css. Tokens: tokens.css. Icons: Lucide (ISC licence) subset + Mona category set. */
(function () {
  'use strict';
  var React = window.React;
  var h = React.createElement;
  var useState = React.useState, useEffect = React.useEffect, useRef = React.useRef, useId = React.useId || function () { var r = useRef('mona-' + Math.random().toString(36).slice(2, 8)); return r.current; };

  function cx() { return Array.prototype.filter.call(arguments, Boolean).join(' '); }
  function pick(dict, lang) { return dict[lang] || dict.en; }

  /* ---------------- i18n ---------------- */
  var STATUS = {
    en: { filed: 'Filed by Mona', review: 'Needs review', processing: 'Processing', unreadable: 'Unreadable' },
    fr: { filed: 'Classé par Mona', review: 'À vérifier', processing: 'En cours', unreadable: 'Illisible' },
    ro: { filed: 'Arhivat de Mona', review: 'De verificat', processing: 'În lucru', unreadable: 'Ilizibil' }
  };
  var CONF = {
    en: { label: 'Confidence', high: 'high', mid: 'medium', low: 'low' },
    fr: { label: 'Confiance', high: 'élevée', mid: 'moyenne', low: 'faible' },
    ro: { label: 'Încredere', high: 'ridicată', mid: 'medie', low: 'scăzută' }
  };
  var CLOSE = { en: 'Close', fr: 'Fermer', ro: 'Închideți' };
  var LANGS = [
    { id: 'en', short: 'EN', name: 'English' },
    { id: 'fr', short: 'FR', name: 'Français' },
    { id: 'ro', short: 'RO', name: 'Română' }
  ];
  var THEME_LABELS = {
    en: { group: 'Theme', light: 'Light', dark: 'Dark', system: 'Match system' },
    fr: { group: 'Thème', light: 'Clair', dark: 'Sombre', system: 'Selon le système' },
    ro: { group: 'Temă', light: 'Luminoasă', dark: 'Întunecată', system: 'Ca sistemul' }
  };

  /* ---------------- Icon ---------------- */
  var I = {
    check: [['path', { d: 'M20 6 9 17l-5-5' }]],
    'circle-check': [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'm9 12 2 2 4-4' }]],
    help: [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3' }], ['path', { d: 'M12 17h.01' }]],
    loader: [['path', { d: 'M21 12a9 9 0 1 1-6.219-8.56' }]],
    'file-x': [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }], ['path', { d: 'm14.5 12.5-5 5' }], ['path', { d: 'm9.5 12.5 5 5' }]],
    file: [['path', { d: 'M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z' }], ['path', { d: 'M14 2v4a2 2 0 0 0 2 2h4' }]],
    folder: [['path', { d: 'M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z' }]],
    x: [['path', { d: 'M18 6 6 18' }], ['path', { d: 'm6 6 12 12' }]],
    'chevron-down': [['path', { d: 'm6 9 6 6 6-6' }]],
    'chevron-left': [['path', { d: 'm15 18-6-6 6-6' }]],
    'chevron-right': [['path', { d: 'm9 18 6-6-6-6' }]],
    more: [['circle', { cx: 12, cy: 12, r: 1 }], ['circle', { cx: 19, cy: 12, r: 1 }], ['circle', { cx: 5, cy: 12, r: 1 }]],
    pencil: [['path', { d: 'M21.17 6.81a1 1 0 0 0-3.99-3.99L3.84 16.17a2 2 0 0 0-.5.83l-1.32 4.35a.5.5 0 0 0 .62.62l4.35-1.32a2 2 0 0 0 .83-.5zM15 5l4 4' }]],
    copy: [['rect', { x: 8, y: 8, width: 14, height: 14, rx: 2 }], ['path', { d: 'M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2' }]],
    download: [['path', { d: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3' }]],
    filter: [['path', { d: 'M22 3H2l8 9.46V19l4 2v-8.54z' }]],
    undo: [['path', { d: 'M9 14 4 9l5-5' }], ['path', { d: 'M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5a5.5 5.5 0 0 1-5.5 5.5H11' }]],
    sun: [['circle', { cx: 12, cy: 12, r: 4 }], ['path', { d: 'M12 2v2M12 20v2m-7.07-17.07 1.41 1.41m11.32 11.32 1.41 1.41M2 12h2m16 0h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41' }]],
    moon: [['path', { d: 'M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z' }]],
    monitor: [['rect', { x: 2, y: 3, width: 20, height: 14, rx: 2 }], ['path', { d: 'M8 21h8M12 17v4' }]],
    info: [['circle', { cx: 12, cy: 12, r: 10 }], ['path', { d: 'M12 16v-4M12 8h.01' }]],
    alert: [['path', { d: 'm21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3' }], ['path', { d: 'M12 9v4M12 17h.01' }]],
    bell: [['path', { d: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9' }], ['path', { d: 'M10.3 21a1.94 1.94 0 0 0 3.4 0' }]],
    search: [['circle', { cx: 11, cy: 11, r: 8 }], ['path', { d: 'm21 21-4.3-4.3' }]],
    'arrow-right': [['path', { d: 'M5 12h14m-7-7 7 7-7 7' }]],
    trash: [['path', { d: 'M3 6h18M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2' }]],
    calendar: [['rect', { x: 3, y: 4, width: 18, height: 18, rx: 2 }], ['path', { d: 'M16 2v4M8 2v4M3 10h18' }]],
    lock: [['rect', { x: 3, y: 11, width: 18, height: 11, rx: 2 }], ['path', { d: 'M7 11V7a5 5 0 0 1 10 0v4' }]],
    external: [['path', { d: 'M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6' }]],
    send: [['path', { d: 'M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z' }], ['path', { d: 'm21.854 2.147-10.94 10.939' }]],
    /* Mona document categories (arch motif) */
    bank: [['path', { d: 'M3 9.5 12 4l9 5.5M4 9.5h16M6 12.5v5M18 12.5v5M10 17.5v-3a2 2 0 0 1 4 0v3M3 20.5h18' }]],
    invoice: [['path', { d: 'M6 3h12v18l-2-1.4-2 1.4-2-1.4-2 1.4-2-1.4L6 21zM9 8h6M9 12h6M9 16h3.5' }]],
    tax: [['path', { d: 'M14 3H6.5A1.5 1.5 0 0 0 5 4.5v15A1.5 1.5 0 0 0 6.5 21h11a1.5 1.5 0 0 0 1.5-1.5V8zM14 3v5h5m-4 4-6 6' }], ['circle', { cx: 9.5, cy: 12.5, r: 1 }], ['circle', { cx: 14.5, cy: 17.5, r: 1 }]],
    insurance: [['path', { d: 'M12 3 5 6v5.5c0 4.3 2.9 7.7 7 9.5 4.1-1.8 7-5.2 7-9.5V6zM9.5 15.5v-2.5a2.5 2.5 0 0 1 5 0v2.5' }]],
    payroll: [['rect', { x: 5, y: 3, width: 14, height: 18, rx: 1.5 }], ['circle', { cx: 12, cy: 9, r: 2.3 }], ['path', { d: 'M8.5 15a3.5 3.5 0 0 1 7 0M8.5 18h7' }]],
    training: [['path', { d: 'm2.5 9 9.5-4.5L21.5 9 12 13.5zM6.5 11v4.8c0 1.6 2.5 3.2 5.5 3.2s5.5-1.6 5.5-3.2V11M21.5 9v5.5' }]],
    travel: [['rect', { x: 3.5, y: 7, width: 17, height: 13, rx: 2 }], ['path', { d: 'M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M8 11v5M16 11v5' }]],
    personal: [['path', { d: 'm3.5 11 8.5-7 8.5 7M5.5 9.5V20h13V9.5M10 20v-4a2 2 0 0 1 4 0v4' }]]
  };
  var CATEGORY_NAMES = {
    en: { bank: 'Bank', invoice: 'Invoice', tax: 'Tax', insurance: 'Insurance', payroll: 'Payroll', training: 'Training', travel: 'Travel', personal: 'Personal' },
    fr: { bank: 'Banque', invoice: 'Facture', tax: 'Impôts', insurance: 'Assurance', payroll: 'Paie', training: 'Formation', travel: 'Déplacements', personal: 'Personnel' },
    ro: { bank: 'Bancă', invoice: 'Factură', tax: 'Taxe', insurance: 'Asigurare', payroll: 'Salarii', training: 'Formare', travel: 'Deplasări', personal: 'Personal' }
  };

  function Icon(props) {
    var name = props.name, size = props.size || 16, sw = props.strokeWidth || 2, label = props.label;
    var parts = I[name] || I.file;
    return h('svg', {
      className: cx('mona-icon', props.spin && 'mona-spin', props.className), width: size, height: size, viewBox: '0 0 24 24',
      fill: 'none', stroke: 'currentColor', strokeWidth: sw, strokeLinecap: 'round', strokeLinejoin: 'round',
      role: label ? 'img' : undefined, 'aria-label': label, 'aria-hidden': label ? undefined : true, focusable: 'false'
    }, parts.map(function (p, i) { return h(p[0], Object.assign({ key: i }, p[1])); }));
  }

  function CategoryIcon(props) {
    var size = props.size || 40, lang = props.lang || 'en';
    var label = props.label || pick(CATEGORY_NAMES, lang)[props.category];
    return h('span', { className: 'mona-cat', style: { width: size, height: size }, role: 'img', 'aria-label': label, title: props.showTitle ? label : undefined },
      h(Icon, { name: props.category, size: props.iconSize || Math.round(size / 2), strokeWidth: 1.9 }));
  }

  /* ---------------- Button ---------------- */
  function Button(props) {
    var variant = props.variant || 'secondary', size = props.size || 'md';
    var rest = Object.assign({}, props);
    ['variant', 'size', 'icon', 'iconEnd', 'loading', 'iconOnly', 'children', 'className'].forEach(function (k) { delete rest[k]; });
    var iconSize = size === 'sm' ? 16 : 18;
    return h('button', Object.assign({ type: 'button' }, rest, {
      className: cx('mona-btn', 'mona-btn--' + variant, size === 'sm' && 'mona-btn--sm', props.iconOnly && 'mona-btn--icon', props.className),
      'aria-busy': props.loading ? true : undefined,
      disabled: props.disabled || props.loading
    }),
      props.loading ? h(Icon, { name: 'loader', size: iconSize, spin: true }) : (props.icon ? h(Icon, { name: props.icon, size: iconSize }) : null),
      props.iconOnly ? null : props.children,
      props.iconEnd ? h(Icon, { name: props.iconEnd, size: iconSize }) : null);
  }

  /* ---------------- Input / Select ---------------- */
  function Field(props, control) {
    var hintId = props.id + '-hint';
    return h('div', { className: cx('mona-field', props.error && 'mona-field--error', props.className) },
      props.label ? h('label', { className: 'mona-field__label', htmlFor: props.id }, props.label,
        props.optional ? h('span', { className: 'mona-field__opt' }, ' · ' + props.optional) : null) : null,
      control(props.error || props.hint ? hintId : undefined),
      props.error ? h('div', { className: 'mona-field__hint', id: hintId }, h(Icon, { name: 'alert', size: 16, label: undefined }), h('span', null, props.error))
        : props.hint ? h('div', { className: 'mona-field__hint', id: hintId }, props.hint) : null);
  }
  function Input(props) {
    var autoId = useId(); var id = props.id || autoId;
    var rest = Object.assign({}, props);
    ['label', 'hint', 'error', 'optional', 'icon', 'className', 'id'].forEach(function (k) { delete rest[k]; });
    return Field(Object.assign({}, props, { id: id }), function (describedBy) {
      return h('div', { className: 'mona-field__wrap' },
        props.icon ? h('span', { className: 'mona-field__lead' }, h(Icon, { name: props.icon, size: 18 })) : null,
        h('input', Object.assign({ type: 'text' }, rest, {
          id: id, className: cx('mona-field__control', props.icon && 'mona-field__control--with-lead'),
          'aria-invalid': props.error ? true : undefined, 'aria-describedby': describedBy
        })));
    });
  }
  function Select(props) {
    var autoId = useId(); var id = props.id || autoId;
    var rest = Object.assign({}, props);
    ['label', 'hint', 'error', 'optional', 'options', 'placeholder', 'className', 'id'].forEach(function (k) { delete rest[k]; });
    return Field(Object.assign({}, props, { id: id }), function (describedBy) {
      return h('div', { className: 'mona-field__wrap' },
        h('select', Object.assign({}, rest, { id: id, className: 'mona-field__control', 'aria-invalid': props.error ? true : undefined, 'aria-describedby': describedBy }),
          props.placeholder ? h('option', { value: '', disabled: true }, props.placeholder) : null,
          (props.options || []).map(function (o) {
            return o.options
              ? h('optgroup', { key: o.label, label: o.label }, o.options.map(function (c) { return h('option', { key: c.value, value: c.value }, c.label); }))
              : h('option', { key: o.value, value: o.value }, o.label);
          })),
        h('span', { className: 'mona-field__chev' }, h(Icon, { name: 'chevron-down', size: 18 })));
    });
  }

  /* ---------------- Tabs ---------------- */
  function Tabs(props) {
    var tabs = props.tabs || [];
    var controlled = props.value !== undefined;
    var st = useState(props.defaultValue || (tabs[0] && tabs[0].id)); var inner = st[0], setInner = st[1];
    var value = controlled ? props.value : inner;
    var refs = useRef({});
    function select(id) { if (!controlled) setInner(id); if (props.onChange) props.onChange(id); }
    function onKey(e) {
      var i = tabs.findIndex(function (t) { return t.id === value; }); var n = null;
      if (e.key === 'ArrowRight') n = (i + 1) % tabs.length;
      if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
      if (e.key === 'Home') n = 0; if (e.key === 'End') n = tabs.length - 1;
      if (n !== null) { e.preventDefault(); select(tabs[n].id); var el = refs.current[tabs[n].id]; if (el) el.focus(); }
    }
    return h('div', { className: cx('mona-tabs', props.className), role: 'tablist', 'aria-label': props.label, onKeyDown: onKey },
      tabs.map(function (t) {
        var on = t.id === value;
        return h('button', {
          key: t.id, ref: function (el) { refs.current[t.id] = el; }, type: 'button', role: 'tab', id: 'tab-' + t.id,
          'aria-selected': on, 'aria-controls': t.panelId, tabIndex: on ? 0 : -1, className: 'mona-tab', onClick: function () { select(t.id); }
        }, t.label, t.count != null ? h('span', { className: 'mona-tab__count' }, t.count) : null);
      }));
  }

  /* ---------------- StatusPill ---------------- */
  var STATUS_ICON = { filed: 'check', review: 'help', processing: 'loader', unreadable: 'file-x' };
  function StatusPill(props) {
    var status = props.status || 'processing', lang = props.lang || 'en';
    var label = props.label || pick(STATUS, lang)[status];
    var sm = props.size === 'sm';
    var icon = h(Icon, { name: STATUS_ICON[status], size: sm ? 12 : 14, strokeWidth: status === 'filed' ? 2.8 : 2.4, spin: status === 'processing' });
    var cls = cx('mona-pill', 'mona-pill--' + status, sm && 'mona-pill--sm', props.compact && 'mona-pill--compact', props.className);
    if (props.compact) return h(Tooltip, { content: label }, h('span', { className: cls, role: 'img', 'aria-label': label, tabIndex: 0 }, icon));
    return h('span', { className: cls, role: status === 'processing' ? 'status' : undefined }, icon, h('span', null, label));
  }

  /* ---------------- ConfidenceMeter ---------------- */
  function ConfidenceMeter(props) {
    var lang = props.lang || 'en';
    var v = props.value > 1 ? props.value / 100 : (props.value || 0);
    var level = v >= 0.85 ? 'high' : v >= 0.6 ? 'mid' : 'low';
    var on = v > 0 ? Math.max(1, Math.round(v * 5)) : 0;
    var t = pick(CONF, lang);
    var pct = format.percent(v, lang);
    var text = t.label + ' ' + pct + ', ' + t[level];
    return h('span', { className: cx('mona-meter', 'mona-meter--' + level, props.className), role: 'meter', 'aria-valuemin': 0, 'aria-valuemax': 100, 'aria-valuenow': Math.round(v * 100), 'aria-valuetext': text, 'aria-label': t.label },
      props.hideLabel ? null : h('span', null, t.label),
      h('span', { className: 'mona-meter__segs', 'aria-hidden': true }, [0, 1, 2, 3, 4].map(function (i) { return h('span', { key: i, className: 'mona-meter__seg', 'data-on': i < on ? '' : undefined }); })),
      h('span', { className: 'mona-meter__value' }, pct),
      props.hideWord ? null : h('span', null, t[level]));
  }

  /* ---------------- MonaAvatar ---------------- */
  function MonaAvatar(props) {
    var size = props.size || 40, state = props.state || 'idle';
    var sw = size <= 24 ? 3.6 : size <= 32 ? 3.1 : 2.8;
    var label = props.label || 'Mona';
    return h('span', { className: cx('mona-avatar', 'mona-avatar--' + state, props.className), style: { width: size, height: size }, role: 'img', 'aria-label': state === 'idle' ? label : label + ' · ' + state },
      h('svg', { width: size, height: size, viewBox: '0 0 40 40', 'aria-hidden': true },
        h('path', { d: 'M11.5 27.5V17a4.25 4.25 0 0 1 8.5 0v10.5M20 17a4.25 4.25 0 0 1 8.5 0v10.5', fill: 'none', stroke: 'currentColor', strokeWidth: sw })),
      state === 'offline' ? h('span', { className: 'mona-avatar__badge', 'aria-hidden': true }, h(Icon, { name: 'moon', size: Math.max(8, Math.round(size * 0.22)), strokeWidth: 2.6 })) : null);
  }

  /* ---------------- Card ---------------- */
  function Card(props) {
    var interactive = !!props.onClick;
    var Tag = props.as || (props.title ? 'article' : 'section');
    var head = null;
    if (props.from === 'mona' || props.status || props.meta) {
      head = h('div', { className: 'mona-card__head' },
        props.from === 'mona' ? h(MonaAvatar, { size: 40, state: props.avatarState }) : null,
        h('div', { className: 'mona-card__who' },
          props.from === 'mona' ? h('span', { className: 'mona-card__name' }, 'Mona') : (props.eyebrow ? h('span', { className: 'mona-card__eyebrow' }, props.eyebrow) : null),
          props.meta ? h('span', { className: 'mona-card__meta' }, props.meta) : null),
        props.status ? (typeof props.status === 'string' ? h(StatusPill, { status: props.status, lang: props.lang }) : props.status) : null);
    }
    return h(Tag, { className: cx('mona-card', props.variant === 'flat' && 'mona-card--flat', interactive && 'mona-card--interactive', props.className), onClick: props.onClick, style: props.style },
      head,
      !head && props.eyebrow ? h('span', { className: 'mona-card__eyebrow' }, props.eyebrow) : null,
      props.title ? h('h3', { className: 'mona-card__title' }, props.title) : null,
      props.voice ? h('p', { className: 'mona-card__voice', lang: props.lang }, props.voice) : null,
      props.children ? h('div', { className: 'mona-card__body' }, props.children) : null,
      props.actions ? h('div', { className: 'mona-card__actions' }, props.actions) : null,
      props.footer ? h('div', { className: 'mona-card__foot' }, props.footer) : null);
  }

  /* ---------------- Table (ledger) ---------------- */
  function Table(props) {
    var cols = props.columns || [], rows = props.rows || [];
    function cell(c, r, isFoot) {
      var v = c.render && !isFoot ? c.render(r) : r[c.key];
      return h('td', { key: c.key, 'data-numeric': c.numeric ? '' : undefined, 'data-align': c.align === 'end' ? 'end' : undefined }, v);
    }
    return h('div', { className: cx('mona-table-wrap', props.className), style: props.maxHeight ? { maxHeight: props.maxHeight } : undefined },
      h('table', { className: 'mona-table' },
        props.caption ? h('caption', null, props.caption) : null,
        h('thead', null, h('tr', null, cols.map(function (c) { return h('th', { key: c.key, scope: 'col', 'data-numeric': c.numeric ? '' : undefined, 'data-align': c.align === 'end' ? 'end' : undefined }, c.label); }))),
        h('tbody', null, rows.map(function (r, i) { return h('tr', { key: props.rowKey ? r[props.rowKey] : i }, cols.map(function (c) { return cell(c, r); })); })),
        props.footer ? h('tfoot', null, h('tr', null, cols.map(function (c) { return cell(c, props.footer, true); }))) : null));
  }

  /* ---------------- Toast ---------------- */
  var TOAST_ICON = { neutral: 'info', info: 'info', success: 'circle-check', warning: 'alert', danger: 'alert' };
  function Toast(props) {
    var tone = props.tone || 'neutral', lang = props.lang || 'en';
    return h('div', { className: cx('mona-toast', 'mona-toast--' + tone, props.className), role: tone === 'danger' ? 'alert' : 'status' },
      h('span', { className: 'mona-toast__icon' }, props.from === 'mona' ? h(MonaAvatar, { size: 20 }) : h(Icon, { name: TOAST_ICON[tone], size: 20 })),
      h('div', { className: 'mona-toast__text' },
        h('div', { className: 'mona-toast__title' }, props.title),
        props.message ? h('div', { className: 'mona-toast__msg' }, props.message) : null),
      props.action ? h(Button, { variant: 'ghost', size: 'sm', className: 'mona-toast__action', icon: props.action.icon, onClick: props.action.onClick }, props.action.label) : null,
      props.onClose ? h('button', { type: 'button', className: 'mona-toast__close', 'aria-label': pick(CLOSE, lang), onClick: props.onClose }, h(Icon, { name: 'x', size: 18 })) : null);
  }
  function ToastStack(props) {
    return h('div', { className: cx('mona-toasts', props.inline && 'mona-toasts--inline'), 'aria-live': 'polite' }, props.children);
  }

  /* ---------------- focus trap for Dialog / Drawer ---------------- */
  var FOCUSABLE = 'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';
  function useModal(open, onClose, ref) {
    useEffect(function () {
      if (!open) return;
      var prev = document.activeElement;
      var el = ref.current;
      var first = el && (el.querySelector('[data-autofocus]') || el.querySelector(FOCUSABLE));
      if (first) first.focus(); else if (el) el.focus();
      function key(e) {
        if (e.key === 'Escape' && onClose) { e.stopPropagation(); onClose(); }
        if (e.key === 'Tab' && el) {
          var f = el.querySelectorAll(FOCUSABLE); if (!f.length) return;
          var a = f[0], z = f[f.length - 1];
          if (e.shiftKey && document.activeElement === a) { e.preventDefault(); z.focus(); }
          else if (!e.shiftKey && document.activeElement === z) { e.preventDefault(); a.focus(); }
        }
      }
      document.addEventListener('keydown', key);
      return function () { document.removeEventListener('keydown', key); if (prev && prev.focus) prev.focus(); };
    }, [open]);
  }

  /* ---------------- Dialog ---------------- */
  function Dialog(props) {
    var ref = useRef(null); var titleId = useId(); var lang = props.lang || 'en';
    useModal(props.open, props.onClose, ref);
    if (!props.open) return null;
    return h('div', { className: 'mona-scrim', onMouseDown: function (e) { if (e.target === e.currentTarget && props.onClose && !props.persistent) props.onClose(); } },
      h('div', { ref: ref, className: cx('mona-dialog', props.size === 'wide' && 'mona-dialog--wide', props.className), role: props.tone === 'danger' ? 'alertdialog' : 'dialog', 'aria-modal': true, 'aria-labelledby': titleId, tabIndex: -1 },
        h('div', { className: 'mona-dialog__head' },
          h('h2', { className: 'mona-dialog__title', id: titleId }, props.title),
          props.onClose ? h('button', { type: 'button', className: 'mona-dialog__close', 'aria-label': pick(CLOSE, lang), onClick: props.onClose }, h(Icon, { name: 'x', size: 20 })) : null),
        h('div', { className: 'mona-dialog__body' }, props.children),
        props.footer ? h('div', { className: 'mona-dialog__foot' }, props.footer) : null));
  }

  /* ---------------- Drawer ---------------- */
  function Drawer(props) {
    var ref = useRef(null); var titleId = useId(); var lang = props.lang || 'en'; var bottom = props.side === 'bottom';
    useModal(props.open, props.onClose, ref);
    if (!props.open) return null;
    return h('div', { className: cx('mona-scrim', 'mona-scrim--drawer', bottom && 'mona-scrim--bottom'), onMouseDown: function (e) { if (e.target === e.currentTarget && props.onClose) props.onClose(); } },
      h('aside', { ref: ref, className: cx('mona-drawer', bottom && 'mona-drawer--bottom', props.className), role: 'dialog', 'aria-modal': true, 'aria-labelledby': titleId, tabIndex: -1 },
        h('div', { className: 'mona-dialog__head' },
          h('h2', { className: 'mona-dialog__title', id: titleId }, props.title),
          props.onClose ? h('button', { type: 'button', className: 'mona-dialog__close', 'aria-label': pick(CLOSE, lang), onClick: props.onClose }, h(Icon, { name: 'x', size: 20 })) : null),
        h('div', { className: 'mona-drawer__body' }, props.children),
        props.footer ? h('div', { className: 'mona-drawer__foot' }, props.footer) : null));
  }

  /* ---------------- Tooltip ---------------- */
  function Tooltip(props) {
    var st = useState(!!props.defaultOpen); var open = st[0], setOpen = st[1]; var id = useId();
    var child = React.Children.only(props.children);
    var trigger = React.cloneElement(child, {
      'aria-describedby': open ? id : undefined,
      onMouseEnter: function () { setOpen(true); }, onMouseLeave: function () { if (!props.defaultOpen) setOpen(false); },
      onFocus: function () { setOpen(true); }, onBlur: function () { if (!props.defaultOpen) setOpen(false); },
      onKeyDown: function (e) { if (e.key === 'Escape') setOpen(false); }
    });
    return h('span', { className: 'mona-tip' }, trigger,
      open ? h('span', { className: cx('mona-tip__bubble', props.side === 'bottom' && 'mona-tip__bubble--bottom'), role: 'tooltip', id: id }, props.content) : null);
  }

  /* ---------------- Segmented radio group (LanguageSwitch, ThemeToggle) ---------------- */
  function Segmented(props) {
    var refs = useRef({}); var opts = props.options;
    function onKey(e) {
      var i = opts.findIndex(function (o) { return o.id === props.value; }); var n = null;
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') n = (i + 1) % opts.length;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') n = (i - 1 + opts.length) % opts.length;
      if (n !== null) { e.preventDefault(); props.onChange && props.onChange(opts[n].id); var el = refs.current[opts[n].id]; if (el) el.focus(); }
    }
    return h('div', { className: cx('mona-seg', props.icons && 'mona-seg--icons', props.className), role: 'radiogroup', 'aria-label': props.label, onKeyDown: onKey },
      opts.map(function (o) {
        var on = o.id === props.value;
        return h('button', { key: o.id, ref: function (el) { refs.current[o.id] = el; }, type: 'button', role: 'radio', 'aria-checked': on, tabIndex: on ? 0 : -1,
          className: 'mona-seg__opt', lang: o.lang, 'aria-label': o.aria, title: o.title, onClick: function () { props.onChange && props.onChange(o.id); } }, o.content);
      }));
  }
  function LanguageSwitch(props) {
    var st = useState(props.defaultValue || 'en'); var value = props.value !== undefined ? props.value : st[0];
    var set = function (v) { st[1](v); props.onChange && props.onChange(v); };
    return h(Segmented, { label: props.label || 'Language · Langue · Limbă', value: value, onChange: set, className: props.className,
      options: LANGS.map(function (l) { return { id: l.id, lang: l.id, aria: l.name, title: l.name, content: l.short }; }) });
  }
  function ThemeToggle(props) {
    var lang = props.lang || 'en'; var t = pick(THEME_LABELS, lang);
    var st = useState(props.defaultValue || 'system'); var value = props.value !== undefined ? props.value : st[0];
    var set = function (v) { st[1](v); props.onChange && props.onChange(v); };
    var withSystem = props.system !== false;
    var opts = [{ id: 'light', icon: 'sun' }, { id: 'dark', icon: 'moon' }].concat(withSystem ? [{ id: 'system', icon: 'monitor' }] : []);
    return h(Segmented, { label: t.group, value: value, onChange: set, icons: !props.showLabels, className: props.className,
      options: opts.map(function (o) { return { id: o.id, aria: t[o.id], title: t[o.id], content: [h(Icon, { key: 'i', name: o.icon, size: 16 }), props.showLabels ? h('span', { key: 'l' }, t[o.id]) : null] }; }) });
  }

  /* ---------------- Citation / SourceList ---------------- */
  function Citation(props) {
    var label = props.label || ('Source ' + props.n);
    return props.href
      ? h('a', { className: 'mona-cite', href: props.href, 'aria-label': label }, props.n)
      : h('button', { type: 'button', className: 'mona-cite', 'aria-label': label, onClick: props.onClick }, props.n);
  }
  function SourceList(props) {
    return h('ol', { className: cx('mona-sources', props.className), 'aria-label': props.label || 'Sources' },
      (props.sources || []).map(function (s, i) {
        var n = s.n || i + 1;
        return h('li', { key: n, id: s.id },
          h('span', { className: 'mona-sources__n', 'aria-hidden': true }, n),
          s.href ? h('a', { className: 'mona-sources__title', href: s.href }, s.title) : h('span', { className: 'mona-sources__title' }, s.title),
          s.detail ? h('span', { className: 'mona-sources__detail' }, s.detail) : null);
      }));
  }

  /* ---------------- EmptyState ---------------- */
  function EmptyState(props) {
    return h('div', { className: cx('mona-empty', props.className) },
      props.art ? (typeof props.art === 'string' ? h('img', { className: 'mona-empty__art', src: props.art, alt: '' }) : props.art) : null,
      h('h3', { className: 'mona-empty__title' }, props.title),
      props.children ? h('p', { className: 'mona-empty__body' }, props.children) : null,
      props.action ? h('div', { className: 'mona-empty__action' }, props.action) : null);
  }

  /* ======================================================================
     Batch 2 — shared primitives
     ====================================================================== */

  var T2 = {
    en: { noMatch: 'No matches', clear: 'Clear', remove: 'Remove', loading: 'Loading', prev: 'Previous page', next: 'Next page', page: 'Page {p} of {n}', range: '{a}–{b} of {n}', crumbs: 'Breadcrumb', fullPath: 'Show full path', drop: 'Drop files here, or', choose: 'choose files', selected: '{n} selected', optional: 'optional', search: 'Search', more: 'more' },
    fr: { noMatch: 'Aucun résultat', clear: 'Effacer', remove: 'Retirer', loading: 'Chargement', prev: 'Page précédente', next: 'Page suivante', page: 'Page {p} sur {n}', range: '{a}–{b} sur {n}', crumbs: 'Fil d’Ariane', fullPath: 'Afficher le chemin complet', drop: 'Déposez vos fichiers ici, ou', choose: 'choisissez-les', selected: '{n} sélectionnés', optional: 'facultatif', search: 'Rechercher', more: 'de plus' },
    ro: { noMatch: 'Niciun rezultat', clear: 'Ștergeți', remove: 'Eliminați', loading: 'Se încarcă', prev: 'Pagina anterioară', next: 'Pagina următoare', page: 'Pagina {p} din {n}', range: '{a}–{b} din {n}', crumbs: 'Navigare', fullPath: 'Afișați calea completă', drop: 'Trageți fișierele aici sau', choose: 'alegeți-le', selected: '{n} selectate', optional: 'opțional', search: 'Căutați', more: 'în plus' }
  };
  function t2(lang, key, vars) {
    var s = pick(T2, lang)[key];
    if (vars) Object.keys(vars).forEach(function (k) { s = s.replace('{' + k + '}', vars[k]); });
    return s;
  }

  /* ---------------- format: locale helpers (EN / FR / RO) ---------------- */
  var NBSP = '\u00a0';
  function loc(lang) { return lang === 'fr' ? 'fr-FR' : lang === 'ro' ? 'ro-RO' : 'en-GB'; }
  function fixSpaces(s) { return s.replace(/[\u202f]/g, NBSP); }
  var format = {
    number: function (n, lang, opts) { return fixSpaces(new Intl.NumberFormat(loc(lang), opts).format(n)); },
    /** Money: EUR → "€1,284.60" / "1 284,60 €" / "1.284,60 €"; RON → "1,284.60 lei" / "1 284,60 lei" / "1.284,60 lei". */
    money: function (amount, currency, lang) {
      currency = currency || 'EUR';
      var num = format.number(amount, lang, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      if (currency === 'RON') return num + NBSP + 'lei';
      if (currency === 'EUR' && lang !== 'en') return num + NBSP + '€';
      return fixSpaces(new Intl.NumberFormat(loc(lang), { style: 'currency', currency: currency }).format(amount));
    },
    /** Percent from 0–1: "62%" / "62 %" (FR only takes the space). */
    percent: function (v, lang, digits) {
      var n = format.number(v * 100, lang, { maximumFractionDigits: digits || 0 });
      return lang === 'fr' ? n + NBSP + '%' : n + '%';
    },
    /** style: 'long' (14 March 2026), 'medium' (14 Mar 2026), 'short' (14/03/2026 · 14.03.2026), 'dayMonth' (14 March). */
    date: function (d, lang, style) {
      d = d instanceof Date ? d : new Date(d);
      var o = style === 'short' ? { day: '2-digit', month: '2-digit', year: 'numeric' }
        : style === 'medium' ? { day: 'numeric', month: 'short', year: 'numeric' }
        : style === 'dayMonth' ? { day: 'numeric', month: 'long' }
        : { day: 'numeric', month: 'long', year: 'numeric' };
      return fixSpaces(new Intl.DateTimeFormat(loc(lang), o).format(d));
    },
    time: function (d, lang) { d = d instanceof Date ? d : new Date(d); return new Intl.DateTimeFormat(loc(lang), { hour: '2-digit', minute: '2-digit', hour12: false }).format(d); },
    /** "2 minutes ago" / "il y a 2 minutes" / "acum 2 minute"; "yesterday" / "hier" / "ieri". */
    relative: function (d, lang, now) {
      d = d instanceof Date ? d : new Date(d); now = now || new Date();
      var s = (d - now) / 1000, a = Math.abs(s), rtf = new Intl.RelativeTimeFormat(loc(lang), { numeric: 'auto' });
      if (a < 45) return rtf.format(0, 'second');
      if (a < 2700) return rtf.format(Math.round(s / 60), 'minute');
      if (a < 72000) return rtf.format(Math.round(s / 3600), 'hour');
      if (a < 518400) return rtf.format(Math.round(s / 86400), 'day');
      return format.date(d, lang, 'medium');
    },
    fileSize: function (bytes, lang) {
      var u = lang === 'fr' ? ['o', 'Ko', 'Mo', 'Go'] : ['B', 'KB', 'MB', 'GB'], i = 0;
      while (bytes >= 1024 && i < u.length - 1) { bytes /= 1024; i++; }
      return format.number(bytes, lang, { maximumFractionDigits: i ? 1 : 0 }) + NBSP + u[i];
    }
  };

  /* ---------------- Layout: Stack, Inline, Grid, Container ---------------- */
  function sp(n) { return n == null ? undefined : (typeof n === 'number' ? 'var(--space-' + n + ')' : n); }
  var ALIGN = { start: 'flex-start', center: 'center', end: 'flex-end', stretch: 'stretch', baseline: 'baseline', between: 'space-between' };
  function layoutProps(props, base) {
    var rest = Object.assign({}, props);
    ['as', 'gap', 'align', 'justify', 'wrap', 'columns', 'minItemWidth', 'size', 'padded', 'className', 'style', 'children'].forEach(function (k) { delete rest[k]; });
    return Object.assign(rest, { className: cx(base, props.className) });
  }
  function Stack(props) {
    return h(props.as || 'div', Object.assign(layoutProps(props, 'mona-stack'), {
      style: Object.assign({ gap: sp(props.gap != null ? props.gap : 4), alignItems: ALIGN[props.align], justifyContent: ALIGN[props.justify] }, props.style) }), props.children);
  }
  function Inline(props) {
    return h(props.as || 'div', Object.assign(layoutProps(props, 'mona-inline'), {
      style: Object.assign({ gap: sp(props.gap != null ? props.gap : 2), alignItems: ALIGN[props.align || 'center'], justifyContent: ALIGN[props.justify], flexWrap: props.wrap === false ? 'nowrap' : 'wrap' }, props.style) }), props.children);
  }
  function Grid(props) {
    var cols = props.minItemWidth ? 'repeat(auto-fill, minmax(min(' + (typeof props.minItemWidth === 'number' ? props.minItemWidth + 'px' : props.minItemWidth) + ', 100%), 1fr))'
      : 'repeat(' + (props.columns || 2) + ', minmax(0, 1fr))';
    return h(props.as || 'div', Object.assign(layoutProps(props, 'mona-grid'), {
      style: Object.assign({ gap: sp(props.gap != null ? props.gap : 4), gridTemplateColumns: cols, alignItems: ALIGN[props.align] }, props.style) }), props.children);
  }
  function Container(props) {
    return h(props.as || 'div', Object.assign(layoutProps(props, cx('mona-container', 'mona-container--' + (props.size || 'lg'), props.padded === false && 'mona-container--flush')), { style: props.style }), props.children);
  }

  /* ---------------- FormField (exported wrapper) ---------------- */
  function FormField(props) {
    var autoId = useId(); var id = props.id || autoId; var hintId = id + '-hint'; var lang = props.lang || 'en';
    var described = props.error || props.hint ? hintId : undefined;
    var child = props.children;
    var control = typeof child === 'function' ? child({ id: id, 'aria-describedby': described, 'aria-invalid': props.error ? true : undefined })
      : React.isValidElement(child) ? React.cloneElement(child, { id: child.props.id || id, 'aria-describedby': described, 'aria-invalid': props.error ? true : undefined }) : child;
    var opt = props.optional === true ? t2(lang, 'optional') : props.optional;
    return h('div', { className: cx('mona-field', props.error && 'mona-field--error', props.className) },
      props.label ? h('label', { className: 'mona-field__label', htmlFor: id }, props.label, opt ? h('span', { className: 'mona-field__opt' }, ' · ' + opt) : null) : null,
      control,
      props.error ? h('div', { className: 'mona-field__hint', id: hintId }, h(Icon, { name: 'alert', size: 16 }), h('span', null, props.error))
        : props.hint ? h('div', { className: 'mona-field__hint', id: hintId }, props.hint) : null);
  }

  /* ---------------- Checkbox ---------------- */
  function Checkbox(props) {
    var autoId = useId(); var id = props.id || autoId; var ref = useRef(null);
    useEffect(function () { if (ref.current) ref.current.indeterminate = !!props.indeterminate; }, [props.indeterminate]);
    var rest = Object.assign({}, props);
    ['label', 'description', 'indeterminate', 'error', 'className', 'id'].forEach(function (k) { delete rest[k]; });
    return h('div', { className: cx('mona-check', props.error && 'mona-check--error', props.disabled && 'mona-check--disabled', props.className) },
      h('span', { className: 'mona-check__box-wrap' },
        h('input', Object.assign({ type: 'checkbox' }, rest, { id: id, ref: ref, className: 'mona-check__input', 'aria-describedby': props.description ? id + '-d' : undefined, 'aria-invalid': props.error ? true : undefined })),
        h('span', { className: 'mona-check__box', 'aria-hidden': true },
          h('svg', { className: 'mona-check__tick', viewBox: '0 0 16 16', width: 14, height: 14 }, h('path', { d: 'M3.5 8.5l3 3 6-7', fill: 'none', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round', strokeLinejoin: 'round' })),
          h('svg', { className: 'mona-check__dash', viewBox: '0 0 16 16', width: 14, height: 14 }, h('path', { d: 'M4 8h8', stroke: 'currentColor', strokeWidth: 2.2, strokeLinecap: 'round' })))),
      props.label ? h('span', { className: 'mona-check__text' },
        h('label', { htmlFor: id, className: 'mona-check__label' }, props.label),
        props.description ? h('span', { className: 'mona-check__desc', id: id + '-d' }, props.description) : null) : null);
  }

  /* ---------------- RadioGroup ---------------- */
  function RadioGroup(props) {
    var name = useId(); var controlled = props.value !== undefined;
    var st = useState(props.defaultValue); var value = controlled ? props.value : st[0];
    function set(v) { if (!controlled) st[1](v); if (props.onChange) props.onChange(v); }
    var cards = props.variant === 'cards';
    return h('fieldset', { className: cx('mona-radios', cards && 'mona-radios--cards', props.orientation === 'horizontal' && 'mona-radios--row', props.error && 'mona-radios--error', props.className) },
      props.legend ? h('legend', { className: 'mona-field__label' }, props.legend) : null,
      h('div', { className: 'mona-radios__list' },
        (props.options || []).map(function (o) {
          var id = name + '-' + o.value; var on = value === o.value;
          return h('label', { key: o.value, htmlFor: id, className: cx('mona-radio', on && 'mona-radio--on', o.disabled && 'mona-check--disabled') },
            h('input', { type: 'radio', id: id, name: props.name || name, value: o.value, checked: on, disabled: o.disabled, className: 'mona-radio__input', onChange: function () { set(o.value); } }),
            h('span', { className: 'mona-radio__dot', 'aria-hidden': true }),
            h('span', { className: 'mona-check__text' },
              h('span', { className: 'mona-check__label' }, o.label),
              o.description ? h('span', { className: 'mona-check__desc' }, o.description) : null),
            cards && o.meta ? h('span', { className: 'mona-radio__meta' }, o.meta) : null);
        })),
      props.error ? h('div', { className: 'mona-field__hint' }, h(Icon, { name: 'alert', size: 16 }), h('span', null, props.error))
        : props.hint ? h('div', { className: 'mona-field__hint' }, props.hint) : null);
  }

  /* ---------------- Switch ---------------- */
  function Switch(props) {
    var autoId = useId(); var id = props.id || autoId;
    var controlled = props.checked !== undefined; var st = useState(!!props.defaultChecked);
    var on = controlled ? props.checked : st[0];
    function toggle() { if (props.disabled) return; if (!controlled) st[1](!on); if (props.onChange) props.onChange(!on); }
    return h('div', { className: cx('mona-switch', props.disabled && 'mona-check--disabled', props.className) },
      h('span', { className: 'mona-check__text' },
        h('label', { htmlFor: id, className: 'mona-check__label' }, props.label),
        props.description ? h('span', { className: 'mona-check__desc', id: id + '-d' }, props.description) : null),
      h('button', { type: 'button', role: 'switch', id: id, 'aria-checked': on, disabled: props.disabled, 'aria-describedby': props.description ? id + '-d' : undefined, className: 'mona-switch__track', onClick: toggle },
        h('span', { className: 'mona-switch__thumb' }, on ? h(Icon, { name: 'check', size: 12, strokeWidth: 3 }) : null)));
  }

  /* ---------------- Textarea ---------------- */
  function Textarea(props) {
    var lang = props.lang || 'en'; var ref = useRef(null);
    var controlled = props.value !== undefined; var st = useState(props.defaultValue || '');
    var val = controlled ? props.value : st[0];
    useEffect(function () { if (props.autoResize && ref.current) { ref.current.style.height = 'auto'; ref.current.style.height = ref.current.scrollHeight + 'px'; } }, [val, props.autoResize]);
    var rest = Object.assign({}, props);
    ['label', 'hint', 'error', 'optional', 'autoResize', 'className', 'lang', 'value', 'defaultValue', 'onChange', 'showCount'].forEach(function (k) { delete rest[k]; });
    var count = props.maxLength && props.showCount !== false ? format.number(val.length, lang) + ' / ' + format.number(props.maxLength, lang) : null;
    return h(FormField, { label: props.label, error: props.error, optional: props.optional, lang: lang, id: props.id, className: props.className,
      hint: count ? h('span', { className: 'mona-field__hint-row' }, h('span', null, props.hint), h('span', { className: 'mona-num', 'aria-live': 'polite' }, count)) : props.hint },
      h('textarea', Object.assign({ rows: 4 }, rest, { ref: ref, value: val, className: 'mona-field__control mona-field__control--area',
        onChange: function (e) { if (!controlled) st[1](e.target.value); if (props.onChange) props.onChange(e); } })));
  }

  /* ---------------- SearchField ---------------- */
  function SearchField(props) {
    var lang = props.lang || 'en'; var ref = useRef(null);
    var controlled = props.value !== undefined; var st = useState(props.defaultValue || '');
    var val = controlled ? props.value : st[0];
    function set(v) { if (!controlled) st[1](v); if (props.onChange) props.onChange(v); }
    var label = props.label || t2(lang, 'search');
    return h('div', { className: cx('mona-search', props.size === 'sm' && 'mona-search--sm', props.className), role: 'search' },
      h('span', { className: 'mona-field__lead' }, h(Icon, { name: 'search', size: 18 })),
      h('input', { ref: ref, type: 'search', className: 'mona-field__control mona-field__control--with-lead mona-search__input', 'aria-label': label, placeholder: props.placeholder || label,
        value: val, onChange: function (e) { set(e.target.value); },
        onKeyDown: function (e) { if (e.key === 'Enter' && props.onSearch) props.onSearch(val); if (e.key === 'Escape' && val) { e.preventDefault(); set(''); } } }),
      val ? h('button', { type: 'button', className: 'mona-search__clear', 'aria-label': t2(lang, 'clear'), onClick: function () { set(''); if (ref.current) ref.current.focus(); } }, h(Icon, { name: 'x', size: 16 })) : null);
  }

  /* ---------------- Popover (fixed-position, flips, closes on outside click / Esc) ---------------- */
  function usePosition(open, triggerRef, panelRef, placement) {
    var st = useState(null); var pos = st[0], setPos = st[1];
    useEffect(function () {
      if (!open) return;
      function place() {
        var t = triggerRef.current, p = panelRef.current; if (!t || !p) return;
        var r = t.getBoundingClientRect(), pw = p.offsetWidth, ph = p.offsetHeight, vw = window.innerWidth, vh = window.innerHeight, gap = 6;
        var top = (placement || '').indexOf('top') === 0 ? r.top - ph - gap : r.bottom + gap;
        if (top + ph > vh - 8 && r.top - ph - gap > 8) top = r.top - ph - gap;
        if (top < 8 && r.bottom + gap + ph < vh) top = r.bottom + gap;
        var left = /end$/.test(placement || '') ? r.right - pw : r.left;
        left = Math.max(8, Math.min(left, vw - pw - 8));
        setPos({ top: Math.round(top), left: Math.round(left), minWidth: props_matchWidth ? r.width : undefined });
      }
      var props_matchWidth = panelRef.current && panelRef.current.dataset.matchWidth === 'true';
      place();
      window.addEventListener('resize', place); window.addEventListener('scroll', place, true);
      return function () { window.removeEventListener('resize', place); window.removeEventListener('scroll', place, true); };
    }, [open]);
    return pos;
  }
  function Popover(props) {
    var controlled = props.open !== undefined; var st = useState(false);
    var open = controlled ? props.open : st[0];
    function setOpen(v) { if (!controlled) st[1](v); if (props.onOpenChange) props.onOpenChange(v); }
    var tRef = useRef(null), pRef = useRef(null); var id = useId();
    var pos = usePosition(open, tRef, pRef, props.placement);
    useEffect(function () {
      if (!open) return;
      function down(e) { if (pRef.current && !pRef.current.contains(e.target) && tRef.current && !tRef.current.contains(e.target)) setOpen(false); }
      function key(e) { if (e.key === 'Escape') { setOpen(false); var b = tRef.current && tRef.current.querySelector('button,[tabindex],a,input'); (b || tRef.current).focus && (b || tRef.current).focus(); } }
      document.addEventListener('mousedown', down); document.addEventListener('keydown', key);
      return function () { document.removeEventListener('mousedown', down); document.removeEventListener('keydown', key); };
    }, [open]);
    var trigger = typeof props.trigger === 'function' ? props.trigger({ open: open, toggle: function () { setOpen(!open); }, id: id })
      : React.cloneElement(props.trigger, { 'aria-expanded': open, 'aria-controls': id, 'aria-haspopup': props.role === 'menu' ? 'menu' : 'dialog', onClick: function () { setOpen(!open); } });
    return h('span', { className: 'mona-pop', ref: tRef }, trigger,
      open ? h('div', { ref: pRef, id: id, role: props.role === 'menu' ? undefined : 'dialog', 'aria-label': props.label, className: cx('mona-pop__panel', props.className), 'data-match-width': props.matchWidth ? 'true' : undefined,
        style: { top: pos ? pos.top : -9999, left: pos ? pos.left : -9999, minWidth: pos && pos.minWidth, width: props.width } },
        typeof props.children === 'function' ? props.children({ close: function () { setOpen(false); } }) : props.children) : null);
  }

  /* ---------------- Menu ---------------- */
  function MenuList(props) {
    var ref = useRef(null);
    var items = props.items || [];
    useEffect(function () { var f = ref.current && ref.current.querySelector('[role="menuitem"]:not([aria-disabled="true"])'); if (f) f.focus(); }, []);
    function onKey(e) {
      var list = Array.prototype.slice.call(ref.current.querySelectorAll('[role="menuitem"]:not([aria-disabled="true"])'));
      var i = list.indexOf(document.activeElement), n = null;
      if (e.key === 'ArrowDown') n = (i + 1) % list.length;
      if (e.key === 'ArrowUp') n = (i - 1 + list.length) % list.length;
      if (e.key === 'Home') n = 0; if (e.key === 'End') n = list.length - 1;
      if (e.key === 'Tab') { props.close(); return; }
      if (e.key.length === 1 && /\S/.test(e.key)) { var k = e.key.toLowerCase(); var j = list.findIndex(function (el, idx) { return idx > i && el.textContent.trim().toLowerCase().indexOf(k) === 0; }); if (j < 0) j = list.findIndex(function (el) { return el.textContent.trim().toLowerCase().indexOf(k) === 0; }); if (j >= 0) n = j; }
      if (n !== null) { e.preventDefault(); list[n].focus(); }
    }
    return h('div', { ref: ref, role: 'menu', 'aria-label': props.label, className: 'mona-menu', onKeyDown: onKey },
      items.map(function (it, i) {
        if (it.type === 'separator') return h('div', { key: 's' + i, role: 'separator', className: 'mona-menu__sep' });
        if (it.type === 'label') return h('div', { key: 'l' + i, className: 'mona-menu__label', role: 'presentation' }, it.label);
        return h('div', { key: it.id || i, role: 'menuitem', tabIndex: -1, 'aria-disabled': it.disabled ? true : undefined,
          className: cx('mona-menu__item', it.danger && 'mona-menu__item--danger'),
          onClick: function () { if (it.disabled) return; props.close(); if (it.onSelect) it.onSelect(it.id); },
          onKeyDown: function (e) { if ((e.key === 'Enter' || e.key === ' ') && !it.disabled) { e.preventDefault(); props.close(); if (it.onSelect) it.onSelect(it.id); } } },
          it.icon ? h(Icon, { name: it.icon, size: 16 }) : h('span', { className: 'mona-menu__noicon' }),
          h('span', { className: 'mona-menu__text' }, it.label),
          it.shortcut ? h('kbd', { className: 'mona-kbd' }, it.shortcut) : null);
      }));
  }
  function Menu(props) {
    return h(Popover, { role: 'menu', placement: props.placement || 'bottom-start', trigger: props.trigger, open: props.open, onOpenChange: props.onOpenChange },
      function (api) { return h(MenuList, { items: props.items, label: props.label, close: api.close }); });
  }

  /* ---------------- Combobox (single or multiple, filterable) ---------------- */
  function norm(s) { return String(s).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase(); }
  function Combobox(props) {
    var lang = props.lang || 'en'; var autoId = useId(); var id = props.id || autoId; var listId = id + '-list';
    var multiple = !!props.multiple;
    var controlled = props.value !== undefined; var st = useState(props.defaultValue != null ? props.defaultValue : (multiple ? [] : null));
    var value = controlled ? props.value : st[0];
    function setValue(v) { if (!controlled) st[1](v); if (props.onChange) props.onChange(v); }
    var opts = props.options || [];
    var byVal = {}; opts.forEach(function (o) { byVal[o.value] = o; });
    var q = useState(''), query = q[0], setQuery = q[1];
    var o = useState(false), open = o[0], setOpen = o[1];
    var a = useState(0), active = a[0], setActive = a[1];
    var wrapRef = useRef(null), inputRef = useRef(null);
    var shown = !multiple && !open && value != null && byVal[value] ? byVal[value].label : query;
    var filtered = opts.filter(function (op) { return !query || norm(op.label + ' ' + (op.group || '') + ' ' + (op.description || '')).indexOf(norm(query)) >= 0; });
    useEffect(function () {
      function down(e) { if (wrapRef.current && !wrapRef.current.contains(e.target)) { setOpen(false); setQuery(''); } }
      document.addEventListener('mousedown', down); return function () { document.removeEventListener('mousedown', down); };
    }, []);
    function isSel(v) { return multiple ? value.indexOf(v) >= 0 : value === v; }
    function choose(op) {
      if (!op || op.disabled) return;
      if (multiple) { setValue(isSel(op.value) ? value.filter(function (v) { return v !== op.value; }) : value.concat([op.value])); setQuery(''); }
      else { setValue(op.value); setQuery(''); setOpen(false); }
    }
    function onKey(e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); if (!open) setOpen(true); else setActive(Math.min(active + 1, filtered.length - 1)); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); setActive(Math.max(active - 1, 0)); }
      else if (e.key === 'Enter' && open) { e.preventDefault(); choose(filtered[active]); }
      else if (e.key === 'Escape') { if (open) { e.preventDefault(); setOpen(false); setQuery(''); } }
      else if (e.key === 'Backspace' && multiple && !query && value.length) setValue(value.slice(0, -1));
    }
    var describedBy = props.label && (props.error || props.hint) ? id + '-hint' : props['aria-describedby'];
    var lastGroup = null;
    var control = h('div', { ref: wrapRef, className: cx('mona-combo', open && 'mona-combo--open', !props.label && props.className) },
      h('div', { className: cx('mona-field__control', 'mona-combo__box'), onClick: function () { inputRef.current && inputRef.current.focus(); setOpen(true); } },
        multiple ? value.map(function (v) { return byVal[v] ? h(Tag, { key: v, size: 'sm', lang: lang, onRemove: function () { setValue(value.filter(function (x) { return x !== v; })); } }, byVal[v].label) : null; }) : null,
        h('input', { ref: inputRef, id: id, className: 'mona-combo__input', role: 'combobox', 'aria-expanded': open, 'aria-controls': listId, 'aria-autocomplete': 'list',
          'aria-activedescendant': open && filtered[active] ? listId + '-' + active : undefined, 'aria-describedby': describedBy, 'aria-invalid': props.error ? true : undefined,
          'aria-label': props.label ? undefined : props['aria-label'],
          placeholder: multiple && value.length ? '' : props.placeholder, value: shown, disabled: props.disabled, autoComplete: 'off',
          onChange: function (e) { setQuery(e.target.value); setOpen(true); setActive(0); }, onFocus: function () { setOpen(true); }, onKeyDown: onKey }),
        h('span', { className: 'mona-field__chev' }, h(Icon, { name: 'chevron-down', size: 18 }))),
      open ? h('ul', { id: listId, role: 'listbox', 'aria-multiselectable': multiple || undefined, className: 'mona-combo__list' },
        filtered.length ? filtered.map(function (op, i) {
          var groupHead = op.group && op.group !== lastGroup ? (lastGroup = op.group, h('li', { key: 'g' + op.group, role: 'presentation', className: 'mona-menu__label' }, op.group)) : null;
          return [groupHead, h('li', { key: op.value, id: listId + '-' + i, role: 'option', 'aria-selected': isSel(op.value), 'aria-disabled': op.disabled || undefined,
            className: cx('mona-combo__opt', i === active && 'mona-combo__opt--active'), onMouseDown: function (e) { e.preventDefault(); choose(op); }, onMouseEnter: function () { setActive(i); } },
            h('span', { className: 'mona-combo__check' }, isSel(op.value) ? h(Icon, { name: 'check', size: 16, strokeWidth: 2.6 }) : null),
            h('span', { className: 'mona-combo__text' }, h('span', null, op.label), op.description ? h('span', { className: 'mona-check__desc' }, op.description) : null))];
        }) : h('li', { className: 'mona-combo__empty', role: 'presentation' }, props.emptyText || t2(lang, 'noMatch'))) : null);
    if (!props.label) return control;
    return h(FormField, { id: id, label: props.label, hint: props.hint, error: props.error, optional: props.optional, lang: lang, className: props.className },
      function () { return control; });
  }

  /* ---------------- FileInput ---------------- */
  function FileInput(props) {
    var lang = props.lang || 'en'; var id = useId(); var inputRef = useRef(null);
    var d = useState(false), drag = d[0], setDrag = d[1];
    var f = useState([]), files = f[0], setFiles = f[1];
    function take(list) { var arr = Array.prototype.slice.call(list || []); var next = props.multiple ? files.concat(arr) : arr.slice(0, 1); setFiles(next); if (props.onFiles) props.onFiles(next); }
    function removeAt(i) { var next = files.filter(function (_, j) { return j !== i; }); setFiles(next); if (props.onFiles) props.onFiles(next); }
    return h(FormField, { id: id, label: props.label, hint: props.hint, error: props.error, optional: props.optional, lang: lang, className: props.className },
      h('div', { className: 'mona-file' },
        h('label', { htmlFor: id, className: cx('mona-file__drop', drag && 'mona-file__drop--over'),
          onDragOver: function (e) { e.preventDefault(); setDrag(true); }, onDragLeave: function () { setDrag(false); },
          onDrop: function (e) { e.preventDefault(); setDrag(false); take(e.dataTransfer.files); } },
          h(Icon, { name: 'file', size: 24 }),
          h('span', null, t2(lang, 'drop') + ' ', h('span', { className: 'mona-file__choose' }, t2(lang, 'choose'))),
          props.accept ? h('span', { className: 'mona-check__desc' }, props.acceptLabel || props.accept) : null,
          h('input', { ref: inputRef, id: id, type: 'file', className: 'mona-sr', accept: props.accept, multiple: props.multiple, onChange: function (e) { take(e.target.files); e.target.value = ''; } })),
        files.length ? h('ul', { className: 'mona-file__list' }, files.map(function (file, i) {
          return h('li', { key: i + file.name },
            h(Icon, { name: 'file', size: 16 }), h('span', { className: 'mona-file__name' }, file.name),
            h('span', { className: 'mona-sources__detail' }, format.fileSize(file.size, lang)),
            h('button', { type: 'button', className: 'mona-toast__close', 'aria-label': t2(lang, 'remove') + ' ' + file.name, onClick: function () { removeAt(i); } }, h(Icon, { name: 'x', size: 16 })));
        })) : null));
  }

  /* ---------------- Link ---------------- */
  function Link(props) {
    var rest = Object.assign({}, props); ['variant', 'external', 'className', 'children'].forEach(function (k) { delete rest[k]; });
    var ext = props.external ? { target: '_blank', rel: 'noopener noreferrer' } : {};
    return h('a', Object.assign(ext, rest, { className: cx('mona-link', props.variant && 'mona-link--' + props.variant, props.className) }),
      props.children, props.external ? h(Icon, { name: 'external', size: 14, className: 'mona-link__ext' }) : null);
  }

  /* ---------------- Banner ---------------- */
  var BANNER_ICON = { neutral: 'info', info: 'info', success: 'circle-check', warning: 'alert', danger: 'alert' };
  function Banner(props) {
    var tone = props.tone || 'info', lang = props.lang || 'en';
    return h('div', { className: cx('mona-banner', 'mona-banner--' + tone, props.variant === 'page' && 'mona-banner--page', props.className), role: tone === 'danger' || tone === 'warning' ? 'alert' : 'status' },
      h('span', { className: 'mona-banner__icon' }, props.from === 'mona' ? h(MonaAvatar, { size: 20 }) : h(Icon, { name: props.icon || BANNER_ICON[tone], size: 20 })),
      h('div', { className: 'mona-banner__text' },
        props.title ? h('div', { className: 'mona-banner__title' }, props.title) : null,
        props.children ? h('div', { className: 'mona-banner__msg' }, props.children) : null),
      props.actions ? h('div', { className: 'mona-banner__actions' }, props.actions) : null,
      props.onDismiss ? h('button', { type: 'button', className: 'mona-toast__close', 'aria-label': pick(CLOSE, lang), onClick: props.onDismiss }, h(Icon, { name: 'x', size: 18 })) : null);
  }

  /* ---------------- Progress, Spinner, Skeleton ---------------- */
  function Progress(props) {
    var lang = props.lang || 'en'; var max = props.max || 100; var ind = props.value == null;
    var pct = ind ? null : Math.max(0, Math.min(1, props.value / max));
    return h('div', { className: cx('mona-progress', props.size === 'sm' && 'mona-progress--sm', props.className) },
      props.label || !ind && props.showValue !== false ? h('div', { className: 'mona-progress__head' },
        h('span', null, props.label), !ind && props.showValue !== false ? h('span', { className: 'mona-num' }, props.valueText || format.percent(pct, lang)) : null) : null,
      h('div', { className: 'mona-progress__track', role: 'progressbar', 'aria-label': typeof props.label === 'string' ? props.label : t2(lang, 'loading'),
        'aria-valuemin': ind ? undefined : 0, 'aria-valuemax': ind ? undefined : max, 'aria-valuenow': ind ? undefined : props.value, 'aria-valuetext': props.valueText },
        h('div', { className: cx('mona-progress__bar', ind && 'mona-progress__bar--ind'), style: ind ? undefined : { width: (pct * 100) + '%' } })));
  }
  function Spinner(props) {
    var lang = props.lang || 'en'; var size = props.size || 20;
    return h('span', { className: cx('mona-spinner', props.className), role: 'status' },
      h(Icon, { name: 'loader', size: size, spin: true, strokeWidth: size <= 16 ? 2.4 : 2 }),
      props.label ? h('span', { className: 'mona-spinner__label' }, props.label) : h('span', { className: 'mona-sr' }, t2(lang, 'loading')));
  }
  function Skeleton(props) {
    var v = props.variant || 'text';
    if (v === 'text') {
      var lines = props.lines || 1;
      return h('div', { className: cx('mona-skel-lines', props.className), 'aria-hidden': true },
        Array.apply(null, Array(lines)).map(function (_, i) { return h('span', { key: i, className: 'mona-skel mona-skel--text', style: { width: i === lines - 1 && lines > 1 ? '62%' : props.width || '100%' } }); }));
    }
    return h('span', { className: cx('mona-skel', 'mona-skel--' + v, props.className), 'aria-hidden': true,
      style: { width: props.width || (v === 'circle' ? 40 : '100%'), height: props.height || (v === 'circle' ? props.width || 40 : 80) } });
  }

  /* ---------------- Badge, Tag ---------------- */
  function Badge(props) {
    var tone = props.tone || 'neutral';
    var content = props.count != null ? (props.count > (props.max || 99) ? (props.max || 99) + '+' : props.count) : props.children;
    return h('span', { className: cx('mona-badge', 'mona-badge--' + tone, props.count != null && 'mona-badge--count', props.className), 'aria-label': props.label }, content);
  }
  function Tag(props) {
    var lang = props.lang || 'en';
    var cls = cx('mona-tag', props.size === 'sm' && 'mona-tag--sm', props.selected && 'mona-tag--selected', props.className);
    var inner = [props.icon ? h(Icon, { key: 'i', name: props.selected ? 'check' : props.icon, size: props.size === 'sm' ? 12 : 14 }) : (props.selected ? h(Icon, { key: 'i', name: 'check', size: props.size === 'sm' ? 12 : 14, strokeWidth: 2.6 }) : null),
      h('span', { key: 't', className: 'mona-tag__text' }, props.children)];
    if (props.onToggle) return h('button', { type: 'button', className: cx(cls, 'mona-tag--toggle'), 'aria-pressed': !!props.selected, onClick: function () { props.onToggle(!props.selected); } }, inner);
    return h('span', { className: cls }, inner,
      props.onRemove ? h('button', { type: 'button', className: 'mona-tag__remove', 'aria-label': t2(lang, 'remove') + ' ' + (typeof props.children === 'string' ? props.children : ''), onClick: function (e) { e.stopPropagation(); props.onRemove(); } }, h(Icon, { name: 'x', size: 12, strokeWidth: 2.6 })) : null);
  }

  /* ---------------- Breadcrumbs ---------------- */
  function Breadcrumbs(props) {
    var lang = props.lang || 'en'; var items = props.items || []; var max = props.maxItems || 4;
    var e = useState(false), expanded = e[0], setExpanded = e[1];
    var collapse = !expanded && items.length > max;
    var shown = collapse ? [items[0], { ellipsis: true }].concat(items.slice(items.length - (max - 2))) : items;
    return h('nav', { className: cx('mona-crumbs', props.className), 'aria-label': props.label || t2(lang, 'crumbs') },
      h('ol', null, shown.map(function (it, i) {
        var last = i === shown.length - 1;
        return h('li', { key: i },
          it.ellipsis ? h('button', { type: 'button', className: 'mona-crumbs__more', 'aria-label': t2(lang, 'fullPath'), onClick: function () { setExpanded(true); } }, '…')
            : last ? h('span', { 'aria-current': 'page', className: 'mona-crumbs__current' }, it.label)
            : h('a', { href: it.href || '#', onClick: it.onClick, className: 'mona-crumbs__link' }, it.label),
          last ? null : h('span', { className: 'mona-crumbs__sep', 'aria-hidden': true }, '/'));
      })));
  }

  /* ---------------- Pagination ---------------- */
  function pageList(p, n) {
    if (n <= 7) return Array.apply(null, Array(n)).map(function (_, i) { return i + 1; });
    var out = [1]; var s = Math.max(2, p - 1), e = Math.min(n - 1, p + 1);
    if (p <= 3) { s = 2; e = 4; } if (p >= n - 2) { s = n - 3; e = n - 1; }
    if (s > 2) out.push('…'); for (var i = s; i <= e; i++) out.push(i); if (e < n - 1) out.push('…'); out.push(n);
    return out;
  }
  function Pagination(props) {
    var lang = props.lang || 'en'; var p = props.page || 1, n = props.pageCount || 1;
    function go(x) { if (x >= 1 && x <= n && x !== p && props.onChange) props.onChange(x); }
    var range = props.total != null && props.pageSize ? t2(lang, 'range', { a: format.number((p - 1) * props.pageSize + 1, lang), b: format.number(Math.min(p * props.pageSize, props.total), lang), n: format.number(props.total, lang) }) : null;
    return h('nav', { className: cx('mona-pages', props.className), 'aria-label': props.label || t2(lang, 'page', { p: p, n: n }) },
      range ? h('span', { className: 'mona-pages__range mona-num' }, range) : null,
      h('div', { className: 'mona-pages__ctrls' },
        h(Button, { variant: 'quiet', size: 'sm', iconOnly: true, icon: 'chevron-left', 'aria-label': t2(lang, 'prev'), disabled: p <= 1, onClick: function () { go(p - 1); } }),
        props.variant === 'compact' ? h('span', { className: 'mona-pages__of mona-num' }, t2(lang, 'page', { p: p, n: n }))
          : pageList(p, n).map(function (x, i) {
            return x === '…' ? h('span', { key: 'e' + i, className: 'mona-pages__gap', 'aria-hidden': true }, '…')
              : h('button', { key: x, type: 'button', className: cx('mona-pages__num', x === p && 'mona-pages__num--on'), 'aria-current': x === p ? 'page' : undefined, 'aria-label': t2(lang, 'page', { p: x, n: n }), onClick: function () { go(x); } }, format.number(x, lang));
          }),
        h(Button, { variant: 'quiet', size: 'sm', iconOnly: true, icon: 'chevron-right', 'aria-label': t2(lang, 'next'), disabled: p >= n, onClick: function () { go(p + 1); } })));
  }

  /* ---------------- Accordion ---------------- */
  function Accordion(props) {
    var base = useId(); var multiple = !!props.multiple;
    var st = useState(props.defaultOpen || []); var open = props.open || st[0];
    function toggle(id) {
      var isOpen = open.indexOf(id) >= 0;
      var next = isOpen ? open.filter(function (x) { return x !== id; }) : (multiple ? open.concat([id]) : [id]);
      if (!props.open) st[1](next); if (props.onChange) props.onChange(next);
    }
    var H = 'h' + (props.headingLevel || 3);
    return h('div', { className: cx('mona-accordion', props.variant === 'card' && 'mona-accordion--card', props.className) },
      (props.items || []).map(function (it) {
        var on = open.indexOf(it.id) >= 0; var bid = base + '-b-' + it.id, pid = base + '-p-' + it.id;
        return h('div', { key: it.id, className: cx('mona-accordion__item', on && 'mona-accordion__item--open') },
          h(H, { className: 'mona-accordion__h' },
            h('button', { type: 'button', id: bid, className: 'mona-accordion__btn', 'aria-expanded': on, 'aria-controls': pid, onClick: function () { toggle(it.id); } },
              h('span', { className: 'mona-accordion__title' }, it.title),
              it.meta ? h('span', { className: 'mona-accordion__meta' }, it.meta) : null,
              h(Icon, { name: 'chevron-down', size: 18, className: 'mona-accordion__chev' }))),
          h('div', { id: pid, role: 'region', 'aria-labelledby': bid, hidden: !on, className: 'mona-accordion__panel' }, it.content));
      }));
  }

  /* ---------------- Avatar, AvatarGroup (people; Mona uses MonaAvatar) ---------------- */
  var AV_TONES = ['sea', 'olive', 'saffron', 'sand', 'umber'];
  function initials(name) {
    var parts = String(name || '').replace(/^(dr\.?|docteur|doctor|doamna|domnul|mme|m\.)\s+/i, '').trim().split(/\s+/);
    return ((parts[0] || '')[0] || '').concat(parts.length > 1 ? parts[parts.length - 1][0] : '').toUpperCase();
  }
  function hashTone(s) { var x = 0; for (var i = 0; i < s.length; i++) x = (x * 31 + s.charCodeAt(i)) >>> 0; return AV_TONES[x % AV_TONES.length]; }
  function Avatar(props) {
    var size = props.size || 32; var e = useState(false), broken = e[0], setBroken = e[1];
    var tone = props.tone || hashTone(props.name || '');
    return h('span', { className: cx('mona-person', 'mona-person--' + tone, props.className), style: { width: size, height: size, fontSize: Math.round(size * 0.38) }, role: 'img', 'aria-label': props.name, title: props.showTitle ? props.name : undefined },
      props.src && !broken ? h('img', { src: props.src, alt: '', onError: function () { setBroken(true); } }) : h('span', { 'aria-hidden': true }, initials(props.name)));
  }
  function AvatarGroup(props) {
    var lang = props.lang || 'en'; var people = props.people || []; var max = props.max || 4; var size = props.size || 32;
    var shown = people.slice(0, max), rest = people.length - shown.length;
    return h('span', { className: cx('mona-avatars', props.className), role: 'group', 'aria-label': props.label },
      shown.map(function (p, i) { return h(Avatar, { key: i, name: p.name, src: p.src, size: size, showTitle: true }); }),
      rest > 0 ? h('span', { className: 'mona-person mona-person--more', style: { width: size, height: size, fontSize: Math.round(size * 0.36) }, role: 'img', 'aria-label': '+' + rest + ' ' + t2(lang, 'more') }, '+' + rest) : null);
  }

  /* ---------------- DescriptionList ---------------- */
  function DescriptionList(props) {
    var layout = props.layout || 'rows';
    return h('dl', { className: cx('mona-dl', 'mona-dl--' + layout, props.className), style: layout === 'grid' ? { gridTemplateColumns: 'repeat(' + (props.columns || 2) + ', minmax(0, 1fr))' } : undefined },
      (props.items || []).map(function (it, i) {
        return h('div', { key: i, className: 'mona-dl__row' },
          h('dt', null, it.term),
          h('dd', { className: cx(it.numeric && 'mona-num', it.mono && 'mona-dl__mono') }, it.detail));
      }));
  }

  /* ---------------- List, ListItem ---------------- */
  function List(props) {
    return h(props.ordered ? 'ol' : 'ul', { className: cx('mona-list', props.variant === 'card' && 'mona-list--card', props.dividers === false && 'mona-list--plain', props.className), 'aria-label': props.label }, props.children);
  }
  function ListItem(props) {
    var interactive = props.href || props.onClick;
    var inner = [
      props.leading ? h('span', { key: 'l', className: 'mona-li__lead' }, props.leading) : null,
      h('span', { key: 't', className: 'mona-li__text' },
        h('span', { className: 'mona-li__title' }, props.title),
        props.description ? h('span', { className: 'mona-li__desc' }, props.description) : null),
      props.meta ? h('span', { key: 'm', className: 'mona-li__meta' }, props.meta) : null,
      interactive && !props.action ? h(Icon, { key: 'c', name: 'chevron-right', size: 16, className: 'mona-li__chev' }) : null
    ];
    return h('li', { className: cx('mona-li', props.selected && 'mona-li--selected', props.className) },
      props.href ? h('a', { href: props.href, className: 'mona-li__hit', 'aria-current': props.selected ? 'page' : undefined }, inner)
        : props.onClick ? h('button', { type: 'button', className: 'mona-li__hit', onClick: props.onClick, 'aria-pressed': props.selected != null ? !!props.selected : undefined }, inner)
        : h('div', { className: 'mona-li__hit mona-li__hit--static' }, inner),
      props.action ? h('span', { className: 'mona-li__action' }, props.action) : null);
  }

  /* ---------------- SegmentedControl (public face of the Segmented primitive) ---------------- */
  function SegmentedControl(props) {
    var controlled = props.value !== undefined; var st = useState(props.defaultValue || (props.options[0] && props.options[0].value));
    var value = controlled ? props.value : st[0];
    return h(Segmented, { label: props.label, value: value, className: props.className, icons: props.iconOnly,
      onChange: function (v) { if (!controlled) st[1](v); if (props.onChange) props.onChange(v); },
      options: props.options.map(function (o) {
        return { id: o.value, aria: props.iconOnly ? o.label : undefined, title: props.iconOnly ? o.label : undefined,
          content: [o.icon ? h(Icon, { key: 'i', name: o.icon, size: 16 }) : null, props.iconOnly ? null : h('span', { key: 'l' }, o.label)] };
      }) });
  }

  var api = {
    Button: Button, Input: Input, Select: Select, Tabs: Tabs, StatusPill: StatusPill, ConfidenceMeter: ConfidenceMeter,
    Card: Card, Table: Table, Toast: Toast, ToastStack: ToastStack, Dialog: Dialog, Drawer: Drawer, Tooltip: Tooltip,
    MonaAvatar: MonaAvatar, LanguageSwitch: LanguageSwitch, ThemeToggle: ThemeToggle, Citation: Citation, SourceList: SourceList,
    EmptyState: EmptyState, Icon: Icon, CategoryIcon: CategoryIcon,
    FormField: FormField, Checkbox: Checkbox, RadioGroup: RadioGroup, Switch: Switch, Textarea: Textarea, SegmentedControl: SegmentedControl,
    Combobox: Combobox, SearchField: SearchField, FileInput: FileInput, Link: Link, Popover: Popover, Menu: Menu,
    Banner: Banner, Progress: Progress, Spinner: Spinner, Skeleton: Skeleton, Badge: Badge, Tag: Tag,
    Breadcrumbs: Breadcrumbs, Pagination: Pagination, Accordion: Accordion, Avatar: Avatar, AvatarGroup: AvatarGroup,
    DescriptionList: DescriptionList, List: List, ListItem: ListItem, Stack: Stack, Inline: Inline, Grid: Grid, Container: Container,
    format: format,
    i18n: { STATUS: STATUS, CONFIDENCE: CONF, CATEGORY: CATEGORY_NAMES, LANGS: LANGS, UI: T2 }
  };
  window.Mona = Object.assign(window.Mona || {}, api);
})();
