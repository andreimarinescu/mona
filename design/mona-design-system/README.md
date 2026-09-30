Mona is a local-first practice manager for dental practices in France and Romania. She reads the practice's paperwork, files it with a clean name, keeps a journal with one-click undo, asks when she is unsure, reminds people about deadlines, and answers questions with sources. Nothing leaves the building. The brand has to feel like a trusted colleague who has run the office for twenty years, so everything here is warm, unhurried and precise.

**Promise.** Your practice's paperwork, handled, privately, on your own machine.

| | Tagline | Private-by-design line |
|---|---|---|
| EN | Paperwork, handled — right here in the practice. | Everything stays on the practice's computer. |
| FR | Vos papiers, réglés — ici, au cabinet. | Tout reste sur l'ordinateur du cabinet. |
| RO | Actele, rezolvate — aici, în cabinet. | Totul rămâne pe calculatorul cabinetului. |

## Why it looks like this

The direction is *warm Mediterranean calm*: sand, lime-washed plaster, terracotta and a deep sea blue, with an editorial serif for Mona's own voice and a clean sans for everything that is interface. Dentists spend their day under clinical white light; Mona's space is the office down the corridor with the afternoon sun on the wall. Warmth signals a person rather than software, and the restraint (one loud colour, lots of ground, hairlines instead of boxes) signals discretion.

The symbol is the **arcade m**: two arches that read as a lowercase *m* and as a colonnade, a place you walk into and find things in order. The arch recurs as a motif in the category icons (bank, insurance, personal), the empty-state illustrations and the tab indicator's rounded cap. A few details come from the *private office* exploration: the numbered citations and source lists under Mona's answers, the ledger-style tables with a heavy rule above totals, oxblood as the danger colour, and the rule that marks lose detail as they get small.

Things Mona never looks like: purple or blue gradients, sparkles, robots or brains, tooth clipart, stethoscopes, stock photos of doctors, glassmorphism, Inter as a display face.

## Using this system

Load `tokens.css`, then `components/bundle.css`, then React 18 and `components/bundle.js`; components are on `window.Mona`. Set `data-theme="light"` or `"dark"` on `<html>`; with neither, the hand-off `tokens.css` follows the operating system. Always set `lang` on `<html>` (`en`, `fr`, `ro`) so hyphenation and screen readers use the right language, and pass the same `lang` to components that carry words (`StatusPill`, `ConfidenceMeter`, `Dialog`, `Toast`, `CategoryIcon`, `ThemeToggle`).

### Colour

- Page ground is `bg`; cards, panels and inputs sit on `surface`; anything floating (dialog, drawer, menu, toast) uses `surface-raised`; wells and table headers use `surface-sunken`.
- Text is `text`; secondary text is `text-muted`. Both hold 4.5:1 on all four grounds in both themes. Never put body text in `accent`.
- `accent` (terracotta) is the one loud colour: the primary button, the selected tab bar, Mona's avatar. At most one primary button per view. Text on an accent fill is `on-accent`, never literal white: in the dark theme the accent lightens and its label turns dark.
- Small terracotta text (citation numbers, selected counts) uses `accent-strong` on `accent-soft` or a surface.
- Links and informational messages use `info` (deep sea). Focus is always `focus`: a solid 2px outline with 2px offset, 3:1 or better on every ground.
- `success` (olive), `warning` (saffron, darkened for text), `danger` (oxblood). Each has a `-soft` ground for tinted banners and pills.
- Brand primitives (`brand-*`) are for the logo, print and illustration. Build UI from the semantic tokens so the dark theme works.
- The dark theme is warm umber night (`#1A1512`), not blue-black.

### Status is never colour alone

Part of the team has a colour-vision deficiency, and the red–green axis is exactly where filed/unreadable would collide. Every document status therefore carries three independent cues. Use `StatusPill`, never a coloured dot:

| Status | Icon | Word (EN / FR / RO) | Shape |
|---|---|---|---|
| `filed` | check | Filed by Mona / Classé par Mona / Arhivat de Mona | solid tint, no border |
| `review` | question in circle | Needs review / À vérifier / De verificat | tint + 1px outline |
| `processing` | turning ring | Processing / En cours / În lucru | dashed outline, no fill |
| `unreadable` | crossed-out file | Unreadable / Illisible / Ilizibil | tint + diagonal hatch |

The same applies to `ConfidenceMeter`: filled segments, the percentage and a word ("62 %, moyenne"), never just a green or red bar. Success and danger also differ in lightness, and every toast carries an icon.

### Type

- **Fraunces** (variable, SOFT 100, WONK 0) is Mona's voice and the editorial face: page titles (`display`), dialog and empty-state titles (`title`), and the sentence at the top of a card where Mona speaks (`voice`). `voice-italic` is for her margin notes ("vu, payé le 12/03 — M."). Never set labels, buttons or table text in Fraunces.
- **Instrument Sans** does all interface work: `heading`, `body-lg` (chat), `body` (default), `body-strong`, `label`, `caption` (13px, the minimum), `overline` (uppercase, tracked, labels only, never sentences).
- `filename` uses the system mono for original and new file names and journal IDs.
- Both fonts ship as variable woff2 files (SIL Open Font License) subset to Latin and Latin Extended. Romanian **ș ț Ș Ț are true comma-below glyphs** (U+0219/U+021B) in both; never type the cedilla forms ş ţ. French œ, ç and « » are all present.
- Use tabular figures (`font-variant-numeric: tabular-nums`, or the `mona-num` class) for every amount and date in a column.
- French punctuation takes a no-break space before `; : ! ?` and inside « ». Use U+00A0; neither font has the narrow U+202F, and it would fall back to a system face.

### Space, shape, depth, motion

- A 4px scale: `space-1` (4) to `space-20` (80). Cards pad `space-6`, dialogs `space-8`, cards sit `space-8` apart.
- Radii: `radius-pill` for buttons, pills, segmented controls and avatars; `radius-md` for inputs, tables and toasts; `radius-xl` for cards and dialogs. There are no sharp corners except table cells.
- Elevation is quiet. Most separation comes from ground colour and `border` hairlines. `shadow-1` for resting cards, `shadow-2` for menus, toasts and hovered cards, `shadow-3` for dialogs and drawers.
- Motion is calm and short: `duration-quick` (160ms) for state changes, `duration-calm` (240ms) for dialogs, drawers and toasts, `ease-standard` by default. The one expressive moment is filing: a document settles into its folder over `duration-slow`. Under `prefers-reduced-motion` durations drop to zero; spinners slow down but keep turning, because a stopped spinner reads as frozen.
- Touch targets are at least 44px (buttons, tabs, segmented options, inputs).

### Logo

- Use `mona-logo.svg` (terracotta symbol, umber wordmark) on light grounds and `mona-logo-inverted.svg` on dark grounds. The stacked lockup is for square spaces.
- One-colour black and white versions exist for stamps, faxes, letterhead and embossing. Never recolour the symbol in any colour other than terracotta, black, white or the lifted `#E08A6C` on dark.
- Clear space around the lockup is the width of one arch on every side. Minimum size: lockup 96px wide, symbol 16px.
- Below 32px the symbol is drawn on its own grid with a heavier stroke (`favicon.svg`, `avatar-round-small.svg`). Don't just scale the 32-unit symbol down.
- The symbol is always a lowercase m of two arches. Never rotate it, outline it, add a tooth, a sparkle or a speech bubble, or put it in a gradient.
- **Mona's avatar** is the terracotta circle with the plaster m (`avatar-round.svg`; `MonaAvatar` in code). Telegram gets `telegram-avatar-512.svg`, full-bleed and safe inside Telegram's circular crop. The favicon is `favicon.svg` (a 16-unit tile), plus `favicon-mono.svg` as the Safari mask icon.

### Iconography

- The interface set is **Lucide** (ISC licence): 24px grid, 2px stroke, round caps and joins, drawn in `currentColor`. `Icon` in the bundle carries the subset in use. Add more from Lucide as needed rather than mixing another set.
- The eight **document categories** are custom icons in the same grammar, with the arch as a signature: `bank`, `invoice`, `tax`, `insurance`, `payroll`, `training`, `travel`, `personal`. Use `CategoryIcon` (a `surface-sunken` tile with a 1.9 stroke) in lists and tables; the SVGs in `assets/category/` are single-ink `currentColor`.
- Icons never replace words for actions that change data (file, move, undo, delete). An icon-only button needs an `aria-label` and a `Tooltip`.
- No emoji in the interface or in Mona's messages.

### Illustration

Empty states use small flat scenes built from the brand shapes: an arch window, folders on a sill, a sun or a moon. There are no people, no faces, no gradients and no outlines except hairlines, and the palette is sand, terracotta, sea, olive and saffron at full value. Scenes are 240 × 180 and sit above a `title` headline and a single sentence in Mona's voice. They read on both themes: on dark the sand arch becomes a lit window. Four exist: `empty-all-filed`, `empty-inbox`, `empty-no-results` and `empty-offline`.

### Content in brief

Mona writes in the first person ("I filed…", "J'ai classé…", "Am arhivat…"), briefly, with exact numbers and the source of every claim. She uses the formal register by default (**vous**, **dumneavoastră**), has no exclamation marks, no emoji and no hype, and allows herself at most one line of dry humour, never about money, errors or patients. The full guide, with examples in all three languages, is the *Voice & tone* section.

### Components

Mona-specific: `StatusPill`, `ConfidenceMeter`, `MonaAvatar`, `Citation` / `SourceList`, `CategoryIcon`, `EmptyState`, `LanguageSwitch`, `ThemeToggle`.

Shared primitives, for any screen in any project:

| Role | Components |
|---|---|
| Forms | `FormField`, `Input`, `Textarea`, `Select`, `Combobox`, `SearchField`, `Checkbox`, `RadioGroup`, `Switch`, `SegmentedControl`, `FileInput` |
| Actions | `Button`, `Link`, `Menu` |
| Overlays | `Popover`, `Tooltip`, `Dialog`, `Drawer` |
| Feedback | `Banner`, `Toast` / `ToastStack`, `Progress`, `Spinner`, `Skeleton`, `Badge`, `Tag` |
| Navigation | `Tabs`, `Breadcrumbs`, `Pagination`, `Accordion` |
| Data display | `Card`, `Table`, `List` / `ListItem`, `DescriptionList`, `Avatar` / `AvatarGroup`, `Icon` |
| Layout | `Stack`, `Inline`, `Grid`, `Container` |

Build screens from these before writing new CSS: spacing comes from `Stack`/`Inline`/`Grid` gaps, page width from `Container`, and every number, amount and date goes through `Mona.format` (see *Formatting*). Choosing between near neighbours:

- **Choosing one value.** `SegmentedControl` for 2–5 visible options, `RadioGroup` when each option needs a sentence, `Select` for up to about 15, `Combobox` beyond that or when people search by name.
- **Messages.** `Toast` for something that just happened, `Banner` for a state that persists, `Dialog` only for decisions.
- **Labels.** `StatusPill` for document status only, `Badge` for counts and one-word labels, `Tag` for filters and removable values.
- **Overlays.** `Tooltip` names a control, `Popover` shows a little more, `Menu` lists actions, `Drawer` holds details, `Dialog` asks for a decision.
- **Waiting.** `Button loading` inside a button, `Skeleton` when you know the layout, `Spinner` for a short unknown wait, `Progress` when you know how much is left.

## What's in this package

```
tokens.css              CSS custom properties: light (default), dark via [data-theme="dark"] or the OS, type classes (.type-*), motion, breakpoints, containers, @font-face
tokens.json             The same tokens as data (list format)
source/tokens.py        Single source of truth; regenerates tokens.css/tokens.json and runs the WCAG audit (python3 tokens.py)
fonts/                  Fraunces (roman + italic) and Instrument Sans, variable woff2, Latin + Latin Extended, with OFL licences
assets/logo/            Lockups (colour, inverted, stacked, mono black/white), wordmark, symbol
assets/app/             favicon.svg (16), favicon-32.svg, favicon-mono.svg (mask icon), app-icon(-maskable|-dark).svg, avatar-round(-dark|-small).svg, telegram-avatar-512.svg
assets/category/        8 document-category icons + category-sprite.svg (<symbol id="mona-cat-…">)
assets/illustration/    4 empty-state scenes
components/             bundle.js (window.Mona, React 18, no build step), bundle.css, index.d.ts (props), lib/ (React 18.3.1 UMD)
voice-and-tone.md       How Mona writes, with EN / FR / RO examples
formatting.md           Mona.format: money, dates, percentages, relative time in EN / FR / RO
```

Minimal page:

```html
<html lang="fr" data-theme="light">
<link rel="icon" href="assets/app/favicon.svg" type="image/svg+xml">
<link rel="mask-icon" href="assets/app/favicon-mono.svg" color="#A94F33">
<link rel="stylesheet" href="tokens.css">
<link rel="stylesheet" href="components/bundle.css">
<script src="components/lib/react.production.min.js"></script>
<script src="components/lib/react-dom.production.min.js"></script>
<script src="components/bundle.js"></script>
```

Every text/ground pair named in the colour tokens' usage notes has been checked in both themes: 102 pairs, all at WCAG AA or better (4.5:1 for text, 3:1 for control edges, focus rings and meter segments). Run `python3 source/tokens.py -v` to see them.
