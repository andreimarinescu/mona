# Mona web app — build handoff

This is the companion to the design canvas "Mona web app" and to `README.md` (brand and tokens). It maps artboards to routes, gives every app-level component the name it should keep in code, and writes down the behaviour a static picture can't show. The Mona design system's React components (`window.Mona.*`, see its README) are the building blocks; nothing here restyles them.

## 1. Reading the canvas

The canvas has six pages. **Desktop · hi-fi** is the source of truth at 1440 wide. **States** holds first run, loading, offline, errors, empty states and toasts. **Mobile** has Home, Review queue and Chat at 390. **Languages & themes** shows Home, Chat and Review queue in French, Romanian and dark; those artboards import the same screens with a different language or theme, so they never drift from the originals. **Parts** has the shared sidebar, the mobile tab bar, the component sheet and the icon addendum. **Wireframes** has the first low-fidelity pass.

Some artboards have Tweaks for language and theme. Those are review levers for the design, not product features: in the app, the language is chosen at first run and changed in Settings, and nowhere else.

All names, companies, amounts, SIRENs and IBAN fragments are fictional. The URSSAF letter drawn in the document viewer is marked as a mock-up.

## 2. Routes and the shell

| Route | Screen (artboard) |
|---|---|
| `/unlock` | 1 · Login (unlock the one profile) |
| `/` | 2 · Home |
| `/chat`, `/chat/:conversationId` | 3 · Chat (full page) |
| any route + chat panel open | 3 · Chat — slide-over panel |
| `/intake` | 4 · Intake |
| `/review`, `/review/:documentId` | 5 · Review queue, and the correction state |
| `/archive`, `/archive/folders/*path` | 6 · Archive, search and folder tree |
| `/documents/:documentId` | 7 · Document viewer (v1 first, see §7) |
| `/rules`, `/rules/:ruleId` | 8 · Rules |
| `/entities`, `/entities/categories/:categoryId` | 9 · Entities & taxonomy |
| `/activity` | 10 · Activity log |
| `/reports` | 11 · Reports |
| `/settings#profile` … `#about` | 12 · Settings, one page with anchored sections |
| dialog over `/archive` | 13 · Accountant export |

`AppShell` is `Sidebar` (248px) plus the routed page, plus the `ChatPanel` and the toast region on top. Below 1024px the sidebar becomes `MobileTabBar` (Home, Review, Chat, Archive, More); Rules, Entities, Activity, Reports and Settings live under More because they're desk work.

The chat panel is non-modal: it sits over the right 460px of the page, the page stays scrollable and clickable, and the panel knows what the page is showing ("Mona can see: Archive, search 'URSSAF', 14 results"). Opening it doesn't change the route; keep its open state and conversation id in app state so it survives navigation.

Keyboard:

- `/` focuses Ask Mona from anywhere, unless focus is already in a text field. On Home it focuses the chat entry; elsewhere it opens the panel.
- `Esc` closes the panel and returns focus to whatever opened it.
- In the review queue, `Enter` confirms, `J` and `K` move between documents.
- On an interview card, `1`, `2` and `3` pick the answers.
- The first tab stop on every page is a "Skip to content" link.

## 3. Component names

These are the names used on the canvas component sheet and in this document; keep them in code. "Built from" names the Mona design-system components to compose, not reimplement.

### Shell

| Component | What it is | Built from |
|---|---|---|
| `AppShell` | Sidebar, page, chat panel, toast region | Container |
| `Sidebar` | Logo, `EntityScopeSwitcher`, nav, `AskMonaButton`, `UserMenu`, `SystemStatusLine` | Badge, MonaAvatar, Avatar, Icon |
| `EntityScopeSwitcher` | "Showing: All entities". Filters every screen. | Select or Menu |
| `UserMenu` | The profile row: name, "Profile · lock", opens Settings › Profile or locks the screen | Avatar, Menu |
| `AskMonaButton` | Always-visible chat entry in the sidebar, shows the `/` shortcut | MonaAvatar |
| `SystemStatusLine` | "On this computer · queue 0", or "Mona is offline" with an alert icon; links to Settings › System status | Icon |
| `MobileTabBar` | Five tabs, a pill behind the active one, review count badge | Badge |
| `ChatPanel` | Slide-over chat, 460px, shadow-3, `role="complementary"` | everything in Chat |
| `ToastRegion` | Bottom-right, left of the chat panel when it's open | ToastStack, Toast |

### Home

| Component | What it is | Built from |
|---|---|---|
| `MonaBrief` | The morning sentence in Fraunces, with inline links to its sources, plus the primary action and a "written at 07:02 from N journal entries" caption | MonaAvatar, Button |
| `ActionCard` | Card with a heading, optional count, a "see all" link and up to three rows. Variants: `ReviewQueueCard`, `DueCard`, `ActivityCard`, `IngestionCard` | Card, Badge |
| `DateTile` | Weekday and day number; urgent (≤ 3 days) on accent-soft, otherwise sunken. The "in 2 days" text carries the urgency. | none |
| `Sparkline` | Fourteen daily bars, today in accent, with an `aria-label` sentence | none |
| `ChatEntry` | The pill composer pinned to the bottom of Home. Same component as `ChatComposer`, larger. | MonaAvatar, Button |

### Chat

| Component | What it is | Built from |
|---|---|---|
| `ConversationList` | Left column of past conversations with search | SearchField |
| `ChatThread` | Messages, bottom-anchored, `aria-live="polite"` on the newest Mona message | |
| `UserMessage` | Bubble on accent-soft, right-aligned; can carry `AttachmentChip`s | |
| `MonaMessage` | Avatar and body-lg text with `Citation`s, followed by a `SourceList` when there are sources | MonaAvatar, Citation, SourceList |
| `StreamingText` | Mona text while streaming, with a blinking caret (static under reduced motion) and `aria-busy` | |
| `ThinkingBlock` | Native `<details>`: live ("Mona is thinking…", dashed, spinner) or done ("Thought for 6 seconds"), reasoning inside | Spinner, Icon |
| `ToolActivityChip` | "Searching archive…" (live, dashed, spinner) → "Searched the archive · 6 found" (done, solid, check) | Icon |
| `DocCard` | Thumbnail, title, entity, category, date, amount, path, confidence, status, Open | StatusPill, ConfidenceMeter, Button |
| `DeadlineCard` | `DateTile`, label, entity and paying account, amount, a due badge, Open letter, Remind me | Badge, Button |
| `InterviewCard` | Mona's question in `voice`, "affects N documents", 2–3 `EvidenceSnippet`s, three answers with the suggested one as primary plus the word "Suggested", keys 1/2/3 | MonaAvatar, Badge, Button |
| `EvidenceSnippet` | File name and page, a verbatim quote with the matched term marked; opens the document at that quote | |
| `RulePreviewCard` | Rule title, source badge, "N move · M stay", `PathDiff` rows, Apply and Adjust | Badge, Button |
| `PathDiff` | Before → after path, only the changed segments marked (struck through / bold); the arrow is read as "becomes" | |
| `DraftCard` | Reply draft on a sunken ground, unknowns left as [BRACKETS], Copy and Download .docx, "Mona never sends anything". It has no Send action, ever. | Badge, Button, Icon |
| `LanguageDivider` | "Continuing in French · Keep English", inserted when Mona follows the user into another language | |
| `ChatComposer` | States: idle, typing, drag-over ("Drop to attach…"), sending (Stop), disabled (offline) | Button |
| `AttachmentChip` | File icon, name in mono, type · size · pages | CategoryIcon |

### Intake and review

| Component | What it is | Built from |
|---|---|---|
| `DropZone` | Large target, also a real button ("Choose files…"), keyboard-operable | Button |
| `BatchProgress` | Batch title, time left, progress, a count per status | Progress, StatusPill |
| `PipelineRow` / `PipelineStepper` | Queued → Reading → OCR → Classifying → Result, with a step label in words and an `aria-label` "Step 3 of 5: OCR" | StatusPill, Icon |
| `BatchQuestionsBanner` | "Mona has 5 questions about this batch" → opens the interview flow in chat | Banner, Button |
| `ReviewList` / `ReviewListItem` | Checkbox, thumbnail, title, `ReasonChip`, arrival meta; selected item on accent-soft with an accent outline | |
| `ReasonChip` | `low` · `entity` · `conflict` · `unreadable`. Icon, word, outline pattern (solid, dashed, double, hatched) and tint. Propose upstream. | Icon |
| `ReviewDetail` | Header with position and prev/next, `PageThumbnail` with numbered highlights, `SuggestionPanel`, pickers, actions | |
| `SuggestionPanel` | Mona's sentence, `ConfidenceMeter`, numbered `EvidenceList` matching the page markers | ConfidenceMeter |
| `CorrectionScopePrompt` | Appears after a correction: "Just this one" or "Every document like this", then a `RulePreviewCard` | RadioGroup (cards) |

### Archive and documents

| Component | What it is | Built from |
|---|---|---|
| `FacetPanel` | Entity, year, category, counterparty, amount range, status | Checkbox, Tag, Select, Combobox, Input, StatusPill |
| `ActiveFilters` | Removable tags above the results | Tag |
| `ResultsTable` | Ledger table, tabular figures, status per row | Table or a plain table with tokens |
| `FolderTree` | ARIA tree (`role="tree"`, `treeitem`, `aria-level`, `aria-expanded`) mirroring the disk, counts per folder | Icon |
| `FolderContents` | The folder's files with their on-disk path, "Show in Explorer" | Breadcrumbs, Banner |
| `DocumentViewer` | See §7. v1 = `PdfFrame` + `DocumentSidePanel`; v2 adds `PdfPageOverlay` and `EvidenceHighlight` | |
| `DocumentSidePanel` | `ExtractedFields`, Filed (path, name, rule that fired), `JournalTimeline`, reminder | ConfidenceMeter, Button |
| `JournalTimeline` | Entries with time, journal number, Undo where the change is reversible | Button |
| `AccountantExportDialog` | Entity and fiscal year → zip and CSV; what's included; destination | Dialog, Select, Checkbox, Button |

### Rules, entities, activity, reports, settings

| Component | What it is | Built from |
|---|---|---|
| `RulesTable` / `RuleRow` | Name and destination, source chip (interview, correction, seed), fired, last fired, corrections since (flagged in words above 2), on/off | Switch |
| `RuleVersionHistory` | Versions with a condition diff and Roll back | Button |
| `LearnedPanel` | "What Mona learned this week", in her voice, with what each lesson moved | MonaAvatar |
| `EntityCard` | Monogram arch tile, name, legal form, SIREN, masked IBANs, fiscal-year end, sub-units, people, visibility (practice or personal; personal entities stay out of Telegram notifications and accountant exports) | AvatarGroup, Icon |
| `CategoryTree` | ARIA tree with category icons and counts | CategoryIcon |
| `CategoryEditor` | Labels per language, `TemplateField` for path and file name, preview, "used by" entities | Input, Checkbox |
| `TemplateField` | Literal text plus token chips (`{entity}`, `{year}`, `{date:YYYY-MM-DD}`, `{issuer}`, `{reference}`) | |
| `ActivityFilters` | Actor (all, by Mona, by you), entity, kind of change, search | SegmentedControl, Select, SearchField |
| `ActivityBatch` / `ActivityItem` | Batch with "Undo whole batch" and expandable children; single items with Undo or Redo | StatusPill, Button, Badge |
| `KpiTile`, `StackedBarChart`, `LineChart`, `BarList` | Reports. Two series told apart by lightness as well as hue, a legend in words, and an `aria-label` sentence on every chart | |
| `SettingsSection`, `ProfileSection`, `StatusTile`, `DataFlowDiagram` | Settings. Profile & lock is the name, password, recovery key and auto-lock; the data-flow diagram is the Privacy section: this computer, Telegram, exports | Switch, LanguageSwitch, Button |

### States

`FirstRunChecklist` (language, entities, archive folder, first documents, Telegram), `OfflineState`, and Mona's `EmptyState` with the four illustrations. Loading uses `Skeleton` in the shape of the final layout, with Mona's avatar in its `thinking` state and a sentence saying what she's doing.

## 4. Behaviour the pictures can't show

**One profile.** Mona has a single user profile for now. The agent underneath (Hermes) runs on the same profile, and Telegram messages act as that profile too, so there are no roles, no per-person permissions and no user switching. The login screen only unlocks the screen after it auto-locks; Mona keeps working while it's locked. The UI says "you" for the person and "Mona" for the agent, and the journal has exactly those two actors.

**Every change goes through the journal.** Filing, renaming, moving, applying a rule, adding a deadline: each writes a journal entry with a number, the actor (Mona or you), before and after, and whether it can be undone. Undo is available from the toast for at least 8 seconds, from the activity log, and from the document's history, forever. A batch undoes as one action. Undo of an undo is Redo. Deleting is the only action that's never done by Mona and the only one that asks for confirmation (danger dialog).

**Toasts** confirm what just happened, in the past tense, with Undo. Group them: "Filed 12 documents", not twelve toasts. Show at most three. Danger toasts use `role="alert"` and stay until dismissed.

**Confidence thresholds.** At 85% and above Mona files on her own. Between 60% and 84% she files and marks it in the journal. Below 60%, when the entity is unknown, when two rules disagree or when the page is unreadable, the document goes to the review queue with the matching `ReasonChip`. Keep the thresholds in settings, not in code.

**Interviews become rules.** Answering an `InterviewCard` or choosing "Every document like this" creates a rule with `source: interview | correction`, shows a `RulePreviewCard` with every document that would move, and moves nothing until Apply. Adjust opens the rule in Rules. "It depends; let me explain" puts the cursor in the composer with the question quoted.

**Nothing is sent.** `DraftCard` has Copy and Download only. Accountant exports write to a folder the person picks. Telegram is the one channel that leaves the machine, and Settings › Privacy says so.

**Language.** The interface language (EN, FR, RO) is asked once in the first-run checklist and changed in Settings; it isn't in the chrome anywhere else. In conversation Mona replies in the language the person writes in and inserts a `LanguageDivider` when that changes; the interface stays in its language. Folder names on disk stay in French with accents; generated file names drop diacritics (`2026-09-22_URSSAF_Appel_T3.pdf`) so accounting tools can read them.

**Formatting.** Every number, amount, date and relative time goes through `Mona.format` with the page language: `€1,284.00` / `1 284,00 €` / `1.284,00 €`, `62%` / `62 %`. French no-break spaces are U+00A0. Romanian uses comma-below ș ț. Expect French and Romanian strings to run about 30% longer: nothing on the canvas has a fixed height where text wraps, and the Home brief grows from two lines to three.

**Theme.** Light by default, dark on `data-theme="dark"`, the OS preference when unset. The dark theme is on the Languages & themes page for Home, Chat and Review queue; every other artboard has a theme Tweak.

## 5. Accessibility checklist

- Real elements only: `button`, `a href`, `input` with `label`, native `details` for reasoning, `table` for tables, ARIA `tree` for the two trees. No clickable divs.
- Focus is always visible (2px `--focus`, 2px offset) and never removed; the dialog traps focus and returns it on close (Mona's `Dialog` already does).
- Status is never colour alone: `StatusPill`, `ReasonChip`, `ConfidenceMeter`, `PipelineStepper` and the corrections-since flag all carry a word.
- Text contrast is 4.5:1 on every ground in both themes when you stay on the semantic tokens. Charts label series in words and carry an `aria-label` sentence.
- Live regions: the newest Mona message and the thinking state (`polite`), toasts (`polite`, danger `alert`), batch progress (`progressbar` with a value text).
- Icon-only buttons have an `aria-label` and a tooltip. Touch targets are at least 44px.
- `lang` on `<html>`, and on any quoted passage in another language (the French evidence quotes in the English UI are marked `lang="fr"`).

## 6. Data the UI expects

Shapes, not a schema; adapt names to the backend.

```ts
type Lang = 'en' | 'fr' | 'ro';
type DocStatus = 'filed' | 'review' | 'processing' | 'unreadable';
type Reason = 'low' | 'entity' | 'conflict' | 'unreadable';

interface Evidence {            // one per extracted field or per interview clue
  documentId: string;
  page: number;                 // 1-based
  quote: string;                // verbatim text from the page's text layer
  verified: boolean;            // the quote was found on that page (see §7)
  boxes?: { x: number; y: number; w: number; h: number }[]; // v2 only, in PDF points
}

interface ExtractedField { key: 'issuer' | 'account' | 'period' | 'amount' | 'dueDate' | string; value: string; evidence: Evidence; confidence: number }

interface DocumentSummary {
  id: string; title: string; originalName: string; fileName: string; path: string[];
  entityId: string; categoryId: string; date: string; amount?: { value: number; currency: 'EUR' | 'RON' };
  status: DocStatus; reasons?: Reason[]; confidence?: number; arrivedAt: string; source: 'scanner' | 'email' | 'telegram' | 'drop';
}

interface Suggestion { entityId: string; categoryId: string; fileName: string; path: string[]; confidence: number; sentence: string; evidence: Evidence[] }

interface Rule {
  id: string; name: string; condition: string; destination: string[]; enabled: boolean;
  source: 'interview' | 'correction' | 'seed'; version: number;
  firedCount: number; lastFiredAt?: string; correctionsSince: number;
}

interface JournalEntry {
  id: number; at: string; actor: 'mona' | 'user';  // one profile; Telegram actions by the owner count as 'user'
  action: 'file' | 'rename' | 'move' | 'rule.apply' | 'rule.change' | 'deadline.add' | 'mark.unreadable' | string;
  documentIds: string[]; before?: unknown; after?: unknown; batchId?: string; undoable: boolean; undoneBy?: number;
}

interface Deadline { id: string; documentId: string; label: string; entityId: string; dueDate: string; amount?: { value: number; currency: 'EUR' | 'RON' }; paidBy?: string }

interface Interview { id: string; question: string; affects: string[]; evidence: Evidence[]; options: { id: string; label: string; suggested?: boolean }[]; suggestionConfidence: number }

type ChatItem =
  | { kind: 'user'; text: string; attachments?: string[] }
  | { kind: 'mona'; text: string; citations?: Evidence[]; streaming?: boolean }
  | { kind: 'thinking'; live: boolean; seconds?: number; reasoning?: string }
  | { kind: 'tool'; label: string; live: boolean; result?: string }
  | { kind: 'doc'; document: DocumentSummary }
  | { kind: 'deadline'; deadline: Deadline }
  | { kind: 'interview'; interview: Interview }
  | { kind: 'rulePreview'; rule: Rule; moves: { documentId: string; from: string[]; to: string[] }[]; stays: string[] }
  | { kind: 'draft'; title: string; body: string; lang: Lang }
  | { kind: 'languageChange'; to: Lang };
```

## 7. Document viewer: ship v1, keep v2 for later

The v2 design (highlight boxes drawn over the page, numbered to match the fields) is the hard part of the whole app. It needs word-level coordinates for every extracted value, a PDF renderer you control, and overlay geometry that survives zoom, rotation, multi-page documents and skewed scans. v1 gets most of the value with none of that, and the side panel is the same in both, so nothing is thrown away.

**v1 (artboard "7 · Document viewer — v1, ships first").**

1. At intake, give every scanned PDF a text layer. OCRmyPDF (Tesseract underneath) does it in one call and runs fine on the practice machine. Write the OCR'd copy to Mona's cache, not into the archive, so the archive keeps the original bytes and still mirrors the disk exactly.
2. Show the cached PDF in the stock pdf.js viewer (`pdfjs-dist`'s prebuilt `web/viewer.html`), served locally and embedded same-origin in an iframe. Don't restyle it in v1; the canvas draws it as-is on purpose.
3. Ask the model to return every extracted field as `{ value, quote, page }`, where the quote is copied verbatim from the page text. After extraction, check that the quote really is on that page: normalise whitespace (including U+00A0 and U+202F), case and diacritics, then look for a substring. If it isn't there, set `verified: false` and drop the field's confidence. This doubles as a hallucination guard for amounts and dates, which is worth having anyway.
4. "Show on page" drives pdf.js's own find. Either set the iframe hash, `#page=1&search=1%20284%2C00&phrase=true`, or, since it's same-origin, dispatch `PDFViewerApplication.eventBus.dispatch('find', { source: null, type: '', query, caseSensitive: false, entireWord: false, highlightAll: false, findPrevious: false, matchDiacritics: false })`. In current pdf.js a string `query` is a phrase search and an array is a set of words (older releases used a `phraseSearch` flag instead), so pin the pdf.js version. pdf.js scrolls to the match and highlights it. If a long quote doesn't match because OCR split it, fall back to the value on its own ("1 284,00").
5. The side panel shows each field with its quote in a `EvidenceSnippet`-style row. The quote is readable on its own, so the panel is useful even if find fails.

Cost: the iframe, one extraction contract change, a verification function, and about ten lines of glue for the find call.

**v2 (artboard "7 · Document viewer — v2, evidence overlay (later)").**

1. Replace the iframe with `pdfjs-dist`'s `PDFViewer` component so you own the page layers.
2. Get word boxes. For scans, take the hOCR or ALTO output from the OCR step. For born-digital PDFs, use `page.getTextContent()`: each item has a transform and a width, which gives its rectangle in PDF points.
3. Map each verified quote to the run of words it matched and take the union of their rectangles. Store them in `Evidence.boxes` at intake, so the viewer never has to search.
4. Draw an absolutely positioned overlay per page, converting PDF points to screen with `viewport.convertToViewportRectangle`, and redraw on zoom and rotation. Each highlight gets the numbered marker from the side panel; hovering either one highlights the other, and both are focusable.
5. Reuse the overlay for `PageThumbnail` in the review queue, which in v1 can be a plain rendered page image without markers.

## 8. Suggested build order

1. Tokens, fonts, `AppShell`, `Sidebar`, routing, theme and language plumbing, `Mona.format` everywhere.
2. The journal, and Undo through toasts and the activity log. Everything else writes to it, so it comes before the screens that use it.
3. Intake and the review queue (the daily loop), with `ReasonChip`, `SuggestionPanel` and `CorrectionScopePrompt`.
4. Archive (search, facets, folder tree) and Document viewer v1.
5. Chat: thread, composer, streaming, thinking and tool chips, then the cards (`DocCard`, `DeadlineCard`, `InterviewCard`, `RulePreviewCard`, `DraftCard`), then the slide-over panel.
6. Home (`MonaBrief` and the action cards), which only summarises what the steps above produce.
7. Rules, entities and taxonomy, activity log, reports, settings, the accountant export.
8. First run, loading, offline and error states, then Document viewer v2.

## 9. Open items

- The model is Qwen 3.6; the exact variant isn't chosen yet, so Settings › System status shows `Qwen 3.6 · [VARIANT]`. Read the name, quantisation and memory use from the runtime rather than hard-coding them.
- The app version is set at launch (About shows `[SET AT LAUNCH]`); read it from the build.
- Brand-owner check of the five derived one-colour or dark files (stacked mono black and white, wordmark mono black and white, small dark avatar).
- Add the sixteen icons in `assets/icons/` to Mona's `Icon` component, and propose `ReasonChip` and the eleven token extensions to the design system.
- Multi-user support is out of scope for now (see "One profile" in §4). If it comes back, it needs roles, per-entity visibility and a journal actor per person; the entity cards already record the people linked to each entity.
