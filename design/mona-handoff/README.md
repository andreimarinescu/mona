# Mona — brand and interface handoff

Mona is a local-first practice manager for dental practices in France and Romania. She reads the practice's paperwork, files it under a clean name, keeps a journal where every change can be undone, asks when she is unsure, reminds people about deadlines and answers questions with sources. Nothing leaves the building.

This package is what the web app needs from the brand: tokens as CSS custom properties, every logo, favicon, app icon and avatar as its own SVG, the fonts, and the rules for using them. The screens themselves are on the design canvas ("Mona web app"); `HANDOFF.md` maps them to routes and names every app-level component.

```
mona-handoff/
├── README.md            this file: rationale and usage rules
├── HANDOFF.md           screens, component names, behaviour, build notes
├── tokens.css           all tokens, light and dark
├── tokens.json          the design system's source tokens (tokens.css is generated from it)
├── fonts/               Fraunces (roman, italic) and Instrument Sans, variable woff2, with their OFL licences
└── assets/
    ├── mona-logo*.svg, mona-wordmark*.svg, mona-symbol*.svg
    ├── favicon*.svg, app-icon*.svg, avatar-round*.svg, telegram-avatar-512.svg
    ├── categories/      the eight document category icons
    ├── illustrations/   the four empty-state scenes
    └── icons/           sixteen Lucide icons the app needs beyond Mona's Icon set
```

## Why it looks like this

Dentists spend the day under clinical white light. Mona's space is meant to feel like the office down the corridor with the afternoon sun on the wall: sand, lime-washed plaster, terracotta and a deep sea blue. Warmth says there's a person here rather than software, and restraint says discretion. There is one loud colour, a lot of ground, and hairlines instead of boxes.

Mona's own voice is set in Fraunces, an editorial serif; everything that is interface is Instrument Sans. That split lets people tell at a glance when Mona is speaking (the morning brief, a question, a note in the margin) and when they are looking at controls.

The symbol is the arcade m: two arches that read as a lowercase m and as a colonnade, a place you walk into and find things in order. The arch comes back in the category icons, the empty-state scenes and the tab indicator's rounded cap.

A few habits come from the "private office" exploration: numbered citations under Mona's answers, ledger tables with a heavy rule above totals, oxblood for danger, and marks that lose detail as they get small rather than just shrinking.

Mona never looks like purple or blue gradients, sparkles, robots or brains, tooth clipart, stethoscopes, stock photos of doctors or glassmorphism, and Inter is never the display face.

## Tokens

Load `tokens.css` once, before any other stylesheet. It declares the three `@font-face` rules (paths are relative to the CSS file, so keep `fonts/` beside it), the primitives, and the semantic tokens for both themes.

v1 ships light only: put `data-theme="light"` on `<html>` so an operating system in dark mode doesn't switch it. The dark theme is kept for later. Put `data-theme="dark"` on `<html>` to switch; `data-theme` also works on any subtree, which is how a single preview can show both. With no `data-theme` anywhere, the page follows the operating system. Always set `lang` on `<html>` (`en`, `fr` or `ro`) so hyphenation and screen readers use the right language.

Build the UI from the semantic tokens (`--bg`, `--surface`, `--text`, `--accent`…). The `--brand-*` primitives are for the logo, print and illustration only, and they don't change in dark mode.

Type roles are font shorthands, so a heading is one line: `font: var(--type-heading);`. The Fraunces roles also carry an optical size (`--type-title-opsz`) and a tracking value; apply them with `font-variation-settings: "SOFT" 100, "WONK" 0, "opsz" 48; letter-spacing: var(--type-title-tracking);`.

Eleven tokens at the end of each theme block are app extensions that the design system doesn't have yet: the dialog scrim, two chart series and a gridline, the path-diff grounds, the evidence highlight, and the "paper" colours used to draw a document page (a page stays light in dark mode, like paper does). They are marked in the file and worth proposing upstream.

## Colour

Page ground is `--bg`. Cards, panels and inputs sit on `--surface`; anything floating (dialogs, drawers, menus, toasts, the chat panel) uses `--surface-raised`; wells, table headers and filename chips use `--surface-sunken`.

Text is `--text` and secondary text is `--text-muted`; both hold 4.5:1 on all four grounds in both themes. Body text is never in `--accent`.

Terracotta (`--accent`) is the one loud colour: the primary button, the selected navigation item, Mona's avatar. Use at most one primary button per view. Text on an accent fill is `--on-accent`, never literal white, because in the dark theme the accent lightens and its label turns dark. Small terracotta text (counts, citation numbers) uses `--accent-strong` on `--accent-soft` or a surface.

Links and information use `--info` (deep sea). Focus is always `--focus`: a solid 2px outline with a 2px offset, 3:1 or better on every ground. Success is olive, warning is saffron darkened for text, danger is oxblood; each has a `-soft` ground for tinted banners and pills.

The dark theme is warm umber night (`#1A1512`), not blue-black.

## Status is never colour alone

Part of the team has a colour-vision deficiency, and filed versus unreadable sits exactly on the red–green axis. Every document status carries three independent cues, and the app's reason chips follow the same principle with a fourth (the outline pattern).

| Status | Icon | Word (EN / FR / RO) | Shape |
|---|---|---|---|
| filed | check | Filed by Mona / Classé par Mona / Arhivat de Mona | solid tint |
| review | question in a circle | Needs review / À vérifier / De verificat | tint and 1px outline |
| processing | turning ring | Processing / En cours / În lucru | dashed outline, no fill |
| unreadable | crossed-out file | Unreadable / Illisible / Ilizibil | tint and diagonal hatch |

The confidence meter works the same way: filled segments, the percentage and a word ("62 %, moyenne"). Every toast has an icon. Success and danger also differ in lightness.

## Type

Fraunces is for Mona's voice: page titles (`display`), dialog and empty-state titles (`title`), the sentence at the top of a card where Mona speaks (`voice`) and her margin notes (`voice-italic`). Labels, buttons and table text are never set in Fraunces.

Instrument Sans does all the interface work: `heading`, `body-lg` for chat, `body` as the default, `body-strong`, `label`, `caption` (13px, the smallest text anywhere) and `overline` (uppercase and tracked, for labels only, never sentences). File names and journal IDs use the system mono.

Every amount and date in a column uses tabular figures (`font-variant-numeric: tabular-nums`).

Both fonts are subset to Latin and Latin Extended. Romanian ș ț Ș Ț are the true comma-below glyphs (U+0219, U+021B); never type the cedilla forms ş ţ. French punctuation takes a no-break space (U+00A0) before `; : ! ?` and inside « ». Use U+00A0 rather than the narrow U+202F, which neither font has.

## Space, shape, depth, motion

Spacing is a 4px scale from `--space-1` (4) to `--space-20` (80). Cards pad `--space-6`, dialogs `--space-8`, and cards sit `--space-8` apart; the desktop page margin is `--space-12`.

Buttons, pills, segmented controls and avatars are fully round (`--radius-pill`). Inputs, tables and toasts use `--radius-md`; cards and dialogs `--radius-xl`. Nothing has sharp corners except table cells.

Elevation is quiet. Most separation comes from ground colour and `--border` hairlines; `--shadow-1` is for resting cards, `--shadow-2` for menus, toasts and hovered cards, `--shadow-3` for dialogs and the chat panel.

Motion is calm and short: `--duration-quick` for state changes, `--duration-calm` for dialogs, drawers and toasts, `--ease-standard` by default. The one expressive moment is filing, when a document settles into its folder over `--duration-slow`. Under `prefers-reduced-motion` the durations drop to zero; spinners slow down but keep turning, because a stopped spinner reads as frozen.

Touch targets are at least 44px.

## Logo

| File | Use |
|---|---|
| `mona-logo.svg` | Primary lockup: terracotta symbol, umber wordmark. Light grounds. |
| `mona-logo-inverted.svg` | Lifted terracotta and plaster. Dark grounds. |
| `mona-logo-stacked.svg`, `mona-logo-stacked-inverted.svg` | Square spaces: splash, packaging, the About panel. |
| `mona-logo-mono-black.svg`, `mona-logo-mono-white.svg` | One colour: stamps, fax, letterhead, embossing. |
| `mona-logo-stacked-mono-black.svg`, `mona-logo-stacked-mono-white.svg` | One-colour stacked lockup. Derived for this package. |
| `mona-wordmark.svg`, `mona-wordmark-inverted.svg` | The name alone, when the symbol is already nearby (the app bar beside the avatar). |
| `mona-wordmark-mono-black.svg`, `mona-wordmark-mono-white.svg` | One-colour wordmark. Derived for this package. |
| `mona-symbol.svg`, `mona-symbol-inverted.svg`, `mona-symbol-mono-black.svg`, `mona-symbol-mono-white.svg` | The arcade m on its 32-unit grid. |

The wordmark is Fraunces converted to outlines, so the files render without the font. Keep clear space of one arch width on every side. The lockup is never narrower than 96px and the symbol never smaller than 16px; below 32px use the favicon or small-avatar drawings, which have a heavier stroke on their own grid, instead of scaling the symbol down.

The symbol is only ever terracotta, black, white or the lifted `#E08A6C` on dark. Never rotate it, outline it, put it in a gradient, or add a tooth, a sparkle or a speech bubble.

The four "derived" files are recolourings of the design system's originals (same paths, one colour). The design system didn't ship them; check them with whoever owns the brand before they go to print.

## App icons, favicons, avatars

| File | Size | Use |
|---|---|---|
| `favicon.svg` | 16 | Browser tab. Drawn for 16px with a heavier m. |
| `favicon-32.svg` | 32 | Tab at 2× and bookmarks. |
| `favicon-mono.svg` | 16 | Safari pinned-tab mask icon (black). |
| `app-icon.svg` | 512 | Rounded square: desktop shortcut, iOS home screen. |
| `app-icon-maskable.svg` | 512 | Full bleed, m inside the 80% safe zone: Android and PWA maskable. |
| `app-icon-dark.svg` | 512 | Umber night ground, lifted terracotta m. |
| `avatar-round.svg`, `avatar-round-dark.svg` | 40 | Mona's avatar in chat, cards and toasts. |
| `avatar-round-small.svg` | 20 | Mona's avatar at 20–28px, heavier stroke. |
| `avatar-round-small-dark.svg` | 20 | Dark-theme small avatar. Derived for this package. |
| `telegram-avatar-512.svg` | 512 | The Telegram bot. Full bleed; Telegram crops it to a circle and the m stays clear. |

In the page head:

```html
<link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" sizes="16x16">
<link rel="icon" href="/assets/favicon-32.svg" type="image/svg+xml" sizes="32x32">
<link rel="mask-icon" href="/assets/favicon-mono.svg" color="#A94F33">
```

and in the web manifest, `app-icon.svg` with `"purpose": "any"` and `app-icon-maskable.svg` with `"purpose": "maskable"`. iOS ignores SVG for `apple-touch-icon`, and Windows tiles want bitmaps too, so render those PNGs from `app-icon.svg` at build time (180 × 180 for iOS) rather than keeping bitmaps in the repo.

Only Mona gets the arcade avatar. People get initials on a tinted circle, never a photo.

## Category icons, illustrations, extra icons

`categories/` holds Mona's eight document categories (bank, invoice, tax, insurance, payroll, training, travel, personal), single-ink and drawn in `currentColor` on the same 24px grid as Lucide, with the arch where it's natural. In lists they sit on a `--surface-sunken` tile.

`illustrations/` holds the four empty-state scenes (all filed, inbox, no results, offline), 240 × 180, flat, no people, readable on both themes. Use them only for empty states, above a `title` headline and one sentence in Mona's voice.

`icons/` holds sixteen Lucide icons (ISC licence) that the screens use and Mona's `Icon` component doesn't carry yet: house, message-square, inbox, list-checks, archive, route, building-2, history, chart-column, settings, paperclip, globe, upload, clock, hard-drive, menu. They follow the same grammar (2px stroke, round caps and joins, `currentColor`) and should be added to the bundle under these Lucide names. `chart-column` is only for Reports, which isn't in v1. Icons never replace words for actions that change data, and an icon-only button always has an `aria-label` and a tooltip.

## Voice, briefly

Mona writes in the first person, briefly, with exact numbers and the source of every claim: "I filed 23 documents overnight." She uses the formal register (vous, dumneavoastră), no exclamation marks, no emoji and no hype, and allows herself at most one line of dry humour, never about money, errors or patients. She doesn't say AI, algorithm, cloud or upload. Buttons are verbs: imperative in English ("Undo"), infinitive in French ("Annuler"), formal imperative in Romanian ("Anulați"). The design system's Voice & tone page has the full guide with examples in all three languages.

## Licences

Fraunces and Instrument Sans are both Google Fonts families under the SIL Open Font License 1.1, with no Reserved Font Name, so the subset woff2 files here can keep their family names. The licence texts are in `fonts/OFL-Fraunces.txt` and `fonts/OFL-InstrumentSans.txt`, copied from the google/fonts repository; ship them next to the fonts, and list both in the About screen's licences.

Serve the fonts from the app itself, never from fonts.googleapis.com. Loading them from Google's servers would send the practice's IP address to Google on every page load, which contradicts "nothing leaves the building" and is what German courts have treated as a GDPR breach. The files here are identical in licence to Google's; if you ever need a fresh copy, take it from google/fonts on GitHub or from Fontsource and self-host it. Lucide icons, including the sixteen in `assets/icons/`, are under the ISC licence. The logo, symbol, category icons and illustrations are Mona's own.
