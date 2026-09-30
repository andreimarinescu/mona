# C2 · REST API and auth

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set B verdict: Andrei, 2026-10-01) |
| Freeze | 2026-10-01 |
| Change rule | Until the freeze, edits by the W1-B fold only. After it, amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L2 (implements every endpoint, auth and the OpenAPI export), L3 (web client, screens, cards), L4 (interview, draft and export endpoints read its jobs' rows), L5 (demo-reset leaves sessions alone), L6 (reverse proxy, TLS) |
| Depends on | C1 (tables, DTOs §11, `auth_sessions` reserved), C3 (`/api/chat`, notes, conversations), C4 (REST equivalents of the tools, visibility, reuse), C5 (corrections, templates, `review.sentence.*`), C6 (interview endpoints' semantics), C7 (file ops, undo, delete), C8 (locale, error strings), C9 (proxy, visibility, secrets in logs) |

Everything the web does goes through this API. It serves C1 §11 DTOs by name and adds the endpoint-specific DTOs below, which follow the same conventions (C1 §1.1: camelCase keys, enum values never re-cased). Every journal entry a web action writes itself is a direct action in the UI, so it is `actor='user'`, `via='ui'` (C1 §5, D5). The pipeline work an upload starts is not: the intake group and the pipeline's entries are `mona`/`pipeline` (C1 §4.1).

## 1. Conventions

### 1.1 Base
1. Every endpoint is under `/api`, JSON in and out (`application/json; charset=utf-8`), except the uploads (§5.1), file downloads (§4.3, §12) and `/api/chat` (C3). A JSON endpoint given another content type answers 415 `unsupported_media_type`.
2. Paths and query parameters use camelCase (`entityId`, `fiscalYear`). Timestamps, dates and money follow C1 §1.3.
3. An id in a path must match its C1 §1.2 prefix pattern; otherwise 404 `not_found` (the same answer as an unknown id). An id in a body or query with the wrong prefix is 400 `invalid_request` with `field`.
4. Soft-deleted documents (C1 §4.2, `deleted_at` set) are `not_found` on every read path except the journal endpoints (§9) and undo.
5. Rendered strings (`Suggestion.sentence`, `Rule.condition`) use the **request locale**: `profile.locale` at the time of the request (C8 §3.1). There is no per-request locale parameter. Interview text and option labels, the server-added "Ask me each time" included, are stored in the interview's language (C6 §4.5, C8 §3.3) and served as stored.
6. Same origin only: no CORS headers. In dev, Vite proxies `/api` to the api (D1); in prod, Caddy does (C9 §4.3).
7. `GET /api/health` (exists, W0) stays unauthenticated for the compose healthcheck and is outside everything below.

### 1.2 Errors
One envelope for every non-2xx JSON response, including FastAPI's own validation errors, 404s and 500s:
```ts
interface ApiError {
  error: {
    code: string;                 // below; the web maps it to i18n `errors.<code>` (C8 §5.3)
    message: string;              // one English sentence for logs and developers; never shown as is, never document text
    field?: string | null;        // dotted camelCase path of the offending input ("conditions.1.value")
    details?: Record<string, unknown> | null;
  }
}
```
| Status | `code` | When |
|---|---|---|
| 400 | `invalid_request` | the request fails schema validation (`details.errors`: the list, each `{field, message}`) |
| 401 | `unauthenticated` | no session, or an expired or revoked one (§2.2) |
| 401 | `invalid_password` | wrong password on unlock or password change |
| 403 | `csrf_failed` | a write without a valid CSRF token or with a foreign `Origin` (§2.4) |
| 403 | `not_allowed` | a domain refusal: Visitors as a correction target, export of a personal or Visitors entity, editing the Visitors entity's identity or deleting it, `purgeAfterHours` on any other entity (§§6, 8, 12) |
| 404 | `not_found` | unknown id, soft-deleted document, or wrong id prefix in a path |
| 404 | `not_ready` | a file that doesn't exist yet: thumbnail, viewer PDF of an image before OCR, `.docx`, export zip |
| 409 | `stale` | C7 §4.2 A.1: the document changed under the operation; re-read and retry |
| 409 | `conflict` | any other state conflict; `details.reason` is the C7 errno name, `collision_exhausted`, or a short slug |
| 409 | `turn_in_progress` | C3 §2 |
| 409 | `already_answered` | an interview question already has a different answer (C6 §6.4); `details.answer` carries it |
| 409 | `already_undone` | C7 §5.3 |
| 409 | `superseded` | C7 §5.2: the entry is no longer undoable because the document moved since |
| 409 | `in_use` | deleting a registry row that another row references (C1 §10, §8) |
| 413 | `too_large` | upload over the limits (§5.1) or a JSON body over 64 KiB, refused before the body is read (§2.7) |
| 415 | `unsupported_media_type` | §1.1 |
| 422 | `invalid_template` | C5 §8 parser rejects a template (C1 §2.7); `details: {template: 'path' \| 'file', offset, message}` |
| 422 | `invalid_rule` | C5 §4 validator rejects a rule; `field` points into `conditions`/`action`, `details.message` is the validator's |
| 422 | `invalid_value` | a domain constraint on one field: thresholds, auto-lock minutes, password length, fiscal-year end, slug format |
| 422 | `not_undoable` | C7 §5.1 |
| 422 | `not_renderable` | confirming a suggestion that has no entity or no renderable path (C5 §9.3 reason `entity`) |
| 423 | `locked` | the session is locked (§2.3) |
| 429 | `too_many_attempts` | unlock throttling (§2.5); `Retry-After` header set |
| 500 | `internal` | anything unexpected; details only in the server log |
| 503 | `unavailable` | Postgres unreachable |

- Validation errors from FastAPI (`RequestValidationError`) and Starlette 404/405 are rewritten into this envelope by exception handlers. The S5 spike's `{"detail": {"code": …}}` shape is replaced.
- `message` and `details` never contain document text, quotes, IBANs, passwords or tokens (C9 §7).

### 1.3 Lists
Two shapes, chosen per endpoint:
```ts
interface Page<T> { items: T[]; total: number; offset: number; limit: number }    // numbered pages (DS Pagination)
interface Feed<T> { items: T[]; nextCursor: string | null }                         // newest-first feeds
```
- `Page` endpoints take `offset` (≥ 0, default 0) and `limit` (1–200, default 50). `total` counts every match.
- `Feed` endpoints take `cursor` (opaque; from `nextCursor`) and `limit` (1–100, default 30). A cursor encodes the sort key of the last item returned (never an offset), so items added meanwhile don't shift the next page. A cursor reused with other filters is 400 `invalid_request` (`field: "cursor"`).

### 1.4 Idempotency
There is no idempotency-key header. Every mutating endpoint is safe to retry by its own semantics, stated per endpoint; the rules are:
- a repeated action whose effect already holds returns 200 with the current state and changes nothing. Only `FileOpResult` (§6.2) carries `outcome: "unchanged"`; a repeated apply answers `groupId: null`, `moved: 0` (§7); deadline status, settings and rule patches return the DTO as it now is;
- undo of an entry already undone is 409 `already_undone`, with nothing changed (C7 §5.3);
- uploads dedupe by content (§5.1); a repeated upload creates a new batch whose items are `duplicate`;
- `POST /api/interviews` and `POST /api/exports` return the existing job for the same scope while it runs (C4 §3.6, §3.13);
- the web disables a button while its request is in flight.

### 1.5 Polling
Cards and pages that change after they render refresh through these endpoints (C3 §5.5, C4 §2.8):

| What | Endpoint | Poll while | Stop when |
|---|---|---|---|
| intake batch | `GET /api/batches/{id}` | `status = 'running'`, or `debrief.status = 'generating'` | `done` and the debrief not `generating`, except that polling continues for 30 s after `finishedAt` while `debrief` is null and `counts.review > 0` (the end-of-batch check creates the interview in a later commit; C6 §3.1, §3.4) |
| interview card | `GET /api/interviews/{id}` | `status = 'generating'` | any other status |
| draft card | `GET /api/drafts/{id}` | `status = 'generating'` | `ready` or `failed` |
| export card | `GET /api/exports/{id}` | `status = 'building'` | `ready` or `failed` |
| rule preview card | `GET /api/rules/{id}/preview` | never polled; fetched on render and after Apply | — |
| a processing document | `GET /api/documents/{id}` | `status = 'processing'` | any other status |
| shell counters | `GET /api/shell` | always, every 15 s | never |

- Interval: 2 s for the first 60 s, then 5 s. Polling pauses while the tab is hidden and stops on 401 or 423.
- Polled endpoints return a weak `ETag` (hash of the JSON body) and answer `If-None-Match` with 304.

## 2. Auth

### 2.1 The profile
- One owner profile (C1 §8 `profile`, R5). There are no users, roles or registration.
- `profile.password_hash` is argon2id in PHC form (`argon2-cffi` `PasswordHasher()` defaults: time cost 3, 64 MiB, parallelism 4). The seed loader sets it from `MONA_OWNER_PASSWORD` (C1 §8); a verify that reports `check_needs_rehash` rehashes in place.
- A forgotten password is reset on the box with `mona profile set-password` (prompted, never an argument). The unlock hint says so (C8 key `auth.unlock.hint`, C8 §5.7), which settles HANDOFF §9's recovery-key line.

### 2.2 Sessions (`auth_sessions`, the table C1 §8 reserves)
```sql
auth_sessions (
  id              text PRIMARY KEY CHECK (id ~ '^ses_[0-9a-hjkmnp-tv-z]{26}$'),
  token_hash      text NOT NULL UNIQUE CHECK (token_hash ~ '^[0-9a-f]{64}$'),   -- sha256 of the cookie token
  created_at      timestamptz NOT NULL DEFAULT now(),
  expires_at      timestamptz NOT NULL,                  -- created_at + 30 days, absolute
  last_active_at  timestamptz NOT NULL DEFAULT now(),    -- §2.3
  revoked_at      timestamptz NULL,
  user_agent      text NULL CHECK (length(user_agent) <= 300),
  updated_at      timestamptz NOT NULL DEFAULT now()        -- C1 §1.3.7: the row is updated in place
)
CREATE INDEX auth_sessions_live ON auth_sessions (expires_at) WHERE revoked_at IS NULL;
```
- The cookie `mona_session` holds 32 random bytes, base64url (43 characters). Only its sha256 is stored. Attributes: `HttpOnly; SameSite=Strict; Path=/`, plus `Secure` whenever the request reached the api over HTTPS (Caddy's `X-Forwarded-Proto`, trusted only from the proxy's address) or the host is `localhost`. No `Max-Age` beyond `expires_at`.
- A session is **live** when `revoked_at IS NULL AND expires_at > now()`. Any other cookie is `unauthenticated`: the web goes to `/unlock`, which creates a new session.
- Snapshots carry no `auth_sessions` rows, so `demo-reset` ends every session and each browser unlocks again (C9 §6.1). A password change revokes every other session.
- Expired and revoked rows older than 7 days are deleted by the periodic `cpu` housekeeping job.

### 2.3 The screen lock
The lock hides the app, not Mona: jobs, Hermes, Telegram and the MCP server keep working (HANDOFF §4).
- **Locked** for a session means: `profile.locked_at IS NOT NULL` (someone pressed Lock; C1 §8 "non-null = locked"), **or** the session is idle: `last_active_at + profile.auto_lock_minutes ≤ now()`.
- **Activity** is what moves `last_active_at` to now: every successful write, and `POST /api/auth/heartbeat`. The web sends the heartbeat at most once a minute while the person has used the keyboard, pointer or touch since the last one. Reads don't count, so polling (§1.5) never keeps a screen unlocked.
- **While locked**, every endpoint answers 423 `locked`, reads included, except `GET /api/auth/state`, `POST /api/auth/unlock`, `POST /api/auth/lock`, `POST /api/auth/logout` and `GET /api/health`. (Plan §12b asks for 423 on writes; reads are refused as well, so an unattended browser can't be read through its devtools. Decided at the W1-B fold.) A chat stream that started before the lock runs to its end.
- **Unlock** checks the password, sets `profile.locked_at = NULL` and this session's `last_active_at = now()`. Other sessions that are idle stay locked (their own idle clock); other active sessions unlock too, since they share the profile's lock.
- The MCP service key never meets the lock (C4 §1.1).

### 2.4 CSRF
- Every non-GET request under `/api` (including `/api/chat` and uploads) needs the header `X-CSRF-Token`. Its value is `base64url(HMAC-SHA256(key = the raw session token, msg = "mona-csrf-v1"))`, which the server recomputes from the cookie, so nothing extra is stored. The web gets it from `GET /api/auth/state` and the unlock response and sends it from an `openapi-fetch` middleware and the chat transport's `headers`.
- If an `Origin` header is present it must equal the app's origin (`MONA_PUBLIC_ORIGIN`, or the request's own scheme and host when unset); otherwise 403 `csrf_failed`.
- `SameSite=Strict` is the first line; the token is the second.

### 2.5 Endpoints
| Method, path | Body | Response | Notes |
|---|---|---|---|
| `GET /api/auth/state` | — | `AuthState` | no session needed |
| `POST /api/auth/unlock` | `{password}` | `AuthState` + `Set-Cookie` when a new session was made | no session or CSRF needed; creates a session if there is no live one, otherwise unlocks it. 401 `invalid_password`, 429 `too_many_attempts` |
| `POST /api/auth/lock` | — | 204 | sets `profile.locked_at = now()` (every session) |
| `POST /api/auth/heartbeat` | — | 204 | activity (§2.3); 423 while locked (it never unlocks) |
| `POST /api/auth/logout` | — | 204 | revokes this session, clears the cookie |
| `PUT /api/auth/password` | `{currentPassword, newPassword}` | 204 | 401 `invalid_password`; 422 `invalid_value` if `newPassword` is under 8 characters; sets `password_changed_at`, revokes every other session |

```ts
interface AuthState {
  authenticated: boolean;          // a live session cookie came with the request
  locked: boolean;                 // §2.3; false when not authenticated
  locale: 'en' | 'fr' | 'ro';      // profile.locale, so /unlock renders in the interface language (C8 §3.1)
  csrfToken: string | null;        // null when not authenticated
  autoLockMinutes: number | null;  // null when not authenticated
  profileName: string | null;      // null when not authenticated or locked
}
```
- **Throttling.** After 5 consecutive failed unlocks (profile-wide, in the api process), every unlock is refused for 60 s with 429 and `Retry-After: 60`; a success resets the count. The throttle check and the password verify run one at a time under a process-wide lock, and an attempt is counted before its verify starts, so parallel requests can't test more than 5 passwords per window. The api runs one process (one uvicorn worker), so the count lives there; a restart resets it. The password and the request body are never logged (C9 §7).

### 2.6 Service key
`Authorization: Bearer $MONA_SERVICE_KEY` is accepted by `/mcp` only (C4 §1.1). No `/api` endpoint accepts it, and a request to `/api` carrying it is treated as having no session. The pipeline doesn't call REST: its jobs run inside the api package (D1) and write through `mona.fileops` and the DB. Hermes reaches Mona only through `/mcp`.

### 2.7 Enforcement order
FastAPI reads a request's body before it resolves dependencies, so the checks in this section can't be dependencies:
1. **Caddy** (prod, C9 §4.3) caps request bodies: `request_body max_size 250MB` on `/api/intake`, `64KB` on every other `/api` path.
2. **ASGI middleware**, before any body byte is read: the session (§2.2), the lock (§2.3), CSRF and `Origin` (§2.4), then the size limit: a `Content-Length` over the route's limit is 413 at once, and a counting receive wrapper stops a chunked body at the limit with 413. Only then does the route read the body.
3. The route validates the body (400, 422) and does the work.

Exceptions: `POST /api/auth/unlock` skips the session, lock and CSRF checks (its `Origin` is still checked); `/api/health` and `GET /api/auth/state` skip all three; `POST /api/auth/lock` and `/api/auth/logout` skip only the lock check (§2.3 allowlist). Every route keeps the size limit. `/api/chat` keeps C3 §2's 32 KiB cap and its 400 `invalid_request`; 413 applies to the other routes. Dev has no Caddy; the middleware alone enforces it.

## 3. Shell and Home

### 3.1 `GET /api/shell`
The sidebar, mobile tab bar and `SystemStatusLine`, polled every 15 s.
```ts
interface ShellState {
  reviewCount: number;             // open review items of non-deleted documents
  processingCount: number;         // documents with status 'processing'
  queue: { llm: number; cpu: number };   // Procrastinate jobs todo + doing per queue
  mona: 'online' | 'offline';      // Hermes /health answered within 2 s (cached 15 s)
}
```

### 3.2 `GET /api/home?since=&entityId=`
Home's brief and action cards. `since` defaults to the start of the current day in Europe/Paris (C4 §3.15: Home passes its own window; the 07:30 cron keeps the 24 h default). `entityId` applies the `EntityScopeSwitcher`.
```ts
interface BriefFacts {             // get_brief (C4 §3.15), camelCase, web channel (C9 §3.1: Visitors documents are left out)
  generatedAt: string; since: string;
  filed: { count: number; byEntity: { entityId: string; name: string; count: number }[] };
  needsReview: { count: number; byReason: Partial<Record<Reason, number>> };
  dueSoon: Deadline[];             // open, due within 7 days or overdue, at most 5
  remindersToday: { reminderId: string; label: string; note: string | null }[];
  learned: { ruleId: string; name: string; createdAt: string; firedSince: number }[];
  pendingInterview: { interviewId: string; openQuestions: number } | null;
}
interface HomeView {
  facts: BriefFacts;
  journalEntryCount: number;       // done journal entries since `since` ("written at … from N journal entries")
  review: { total: number; items: DocumentSummary[] };       // oldest first, at most 3
  due: { total: number; items: Deadline[] };                  // soonest first, at most 3
  activity: { items: ActivityItem[]; documents: DocRefs; rules: Record<string, { name: string }> };   // §9.1's ActivityPage shape, newest first, at most 3
  ingestion: { days: { date: string; count: number }[];       // 14 days, oldest first, documents arrived per Europe/Paris day
               lastBatch: BatchSummary | null };
}
```
- `MonaBrief` is rendered by the web from `facts` with the C8 `home.brief.*` templates; the server stores no prose (C1 §13).

## 4. Documents

### 4.1 Archive search `GET /api/documents`
Query: `q` (1–200 chars), `entityId`, `categoryId`, `counterpartyId`, `year`, `fiscalYear`, `dateFrom`, `dateTo`, `amountMin`, `amountMax`, `status` (`filed` | `review` | `unreadable`, repeatable; default all three), `sort` (`relevance` | `date_desc` | `date_asc` | `arrived_desc` | `amount_desc`; default `relevance` with `q`, else `date_desc`), `offset`, `limit`.
```ts
interface DocumentPage extends Page<DocumentSummary> {
  facets: {
    entities: { id: string; name: string; count: number }[];
    years: { year: number; count: number }[];               // doc_date year
    categories: { id: string; label: string; count: number }[];   // label in the request locale
    counterparties: { id: string; name: string; count: number }[];   // top 20 by count
    statuses: { status: DocStatus; count: number }[];
    amount: { min: number | null; max: number | null };
  };
}
```
- Filters match C4's common filters (C4 §3) with ids instead of names. `q` goes through `norm()` and `websearch_to_tsquery('mona', …)` over `documents.fts` (C1 §1.4, §4.2); `relevance` is `ts_rank`.
- Facet counts apply every filter except the facet's own (standard drill-down).
- `processing` documents are never listed here; Intake shows them.

### 4.2 `GET /api/documents/{id}`
`DocumentDetail` (C1 §11.3). `suggestion` is set while the status is `review` or `unreadable`; its `sentence` follows C5 §9.4 in the request locale. `journal` is this document's entries, newest first (all of them). `Evidence.documentTitle` is filled at serve time (C1 §11.2).

### 4.3 Files
| Endpoint | Serves | Headers |
|---|---|---|
| `GET /api/documents/{id}/pdf` | the viewer PDF: `/data/textcache/<sha[0:2]>/<sha>.ocr.pdf` when it exists (C5 §1.3), else the document's current bytes, **resolved at request time** from `(location, current_path)` through the C7 §3 guard (read side). An image without an OCR'd copy yet is 404 `not_ready` | `Content-Type: application/pdf`; `Content-Disposition: inline; filename*=UTF-8''<stem>.pdf`; `ETag: "<sha>.ocr"` or `"<sha>"`; `Accept-Ranges: bytes` (pdf.js range requests; 206 answers) |
| `GET /api/documents/{id}/original` | the archived bytes as filed (a phone photo stays a `.jpg`) | `Content-Disposition: attachment; filename*=UTF-8''<fileName>`; the stored `mime_type` |
| `GET /api/documents/{id}/thumbnail` | `<sha>.p1.png`; 404 `not_ready` until `render_thumbnail` ran | `image/png`, `Cache-Control: private, max-age=86400` |

- All three add `X-Content-Type-Options: nosniff` and `Cache-Control: private` (plus `Content-Security-Policy: sandbox` on the PDF and the original), and log the document id only.
- `DocumentSummary.pdfUrl` is `/api/documents/{id}/pdf`; `thumbnailUrl` is `/api/documents/{id}/thumbnail` once the file exists, else null (C1 §11.3).

### 4.4 The viewer deep link
The web route `/documents/:documentId?page=<n>&q=<text>&field=<FieldKey>`:
- `page`: 1-based page to open (default 1; clamped to `pageCount`).
- `q`: a phrase for pdf.js find, sent exactly as C5 §7 says (`eventBus.dispatch('find', {query: q, …, matchDiacritics: false})`) after the page opens. `EvidenceSnippet` links carry `page = evidence.page` and `q = evidence.findQuery`, omitting `q` when `findQuery` is null (the side panel then shows the quote only). Archive results opened from a search carry the search text as `q`.
- `field`: the side-panel field to focus (optional).
- The iframe loads `/pdfjs/web/viewer.html?file=<encodeURIComponent(pdfUrl)>#page=<page>` (same origin, W0's pinned pdf.js).
- An unknown or deleted id shows the viewer's not-found state; the route never 404s at the server (it's the SPA).

### 4.5 Folders `GET /api/folders?path=`
The archive tree (HANDOFF `FolderTree`, `FolderContents`), built from the DB paths of non-deleted documents with `location='archive'`, which C7 §9 invariant 2 makes equal to the tree on disk for tracked files. Files a person put in the archive by hand are not listed in v1.
- `path`: folder segments joined with `/` (segments never contain `/`, C5 §8.3); empty = the root.
```ts
interface FolderNode { name: string; path: string[]; documentCount: number; hasChildren: boolean }  // recursive count
interface FolderListing { path: string[]; folders: FolderNode[]; documents: DocumentSummary[] }     // documents directly in this folder
```
- `entityId` filters by the documents' entity. Folders sort by name (locale collation of the request locale), documents by `fileName`.

## 5. Intake

### 5.1 Upload `POST /api/intake`
`multipart/form-data`: one or more `file` parts, plus optional fields `visitor` (`"true"`/`"false"`, default false) and `title` (≤ 120 chars). Composer attachments use this same endpoint (C3 §2).
1. Limits: at most 50 files, each ≤ 25 MB (C4 §3.14), the whole request ≤ 250 MB; over any limit → 413 `too_large` and nothing is written. The 250 MB cap is enforced before the body is read, and a part is refused as it streams past 25 MB (§2.7).
2. One transaction creates one batch (`source='drop'`, `visitor`, `title`) and its `intake_batch` op group (C1 §4.1), then, **in part order**, one `intake_items` row per file:
   - type sniffed from the bytes (PDF, JPEG, PNG), never from the name or the client's content type; anything else → `rejected`, `unsupported_type`; 0 bytes → `empty`; bytes that fail to open (a truncated PDF) → `unreadable_file`;
   - `sha256` equal to an existing document's, in any location including the trash → `duplicate`, `document_id` = that document, no file written (C7 §8.4);
   - otherwise `accepted`: the bytes land in the inbox as `<document_id>.<ext>` (C7 §1) through `mona.fileops` (temp file + rename), the `documents` row is created (`status='processing'`, `pipeline_stage='queued'`), and `extract_text` is enqueued in part order (C5 §1.2).
3. A batch with no accepted document is `done` at creation (C1 §4.1).
4. `visitor = true` makes the whole batch a visitor batch: C5 §4.6.8 files it under Visitors, and C9 §5 purges it.

Response 201:
```ts
interface IntakeItem {
  id: string; originalName: string; sha256: string; sizeBytes: number;
  outcome: 'accepted' | 'duplicate' | 'rejected';
  rejectReason: 'unsupported_type' | 'too_large' | 'empty' | 'unreadable_file' | null;
  documentId: string | null;
  deleted: boolean;                     // the duplicate is a document in the trash (C7 §8.4)
  restoreJournalId: number | null;      // when deleted: the live `delete` entry whose undo restores it
}
interface IntakeResult { batch: BatchSummary; items: IntakeItem[] }
```
- **Restore.** The Intake row of a `deleted: true` duplicate offers Restore, which is `POST /api/journal/{restoreJournalId}/undo` (§9.2): your undo of the delete (C7 §5.3 item 4, §8.4).

### 5.2 Batches
| Method, path | Response |
|---|---|
| `GET /api/batches?offset&limit` | `Page<BatchSummary>`, newest `started_at` first |
| `GET /api/batches/{id}` | `BatchDetail` (polled, §1.5) |
| `PATCH /api/batches/{id}` `{title}` | `BatchSummary` ("Tuesday's post"; ≤ 120 chars, or null) |

```ts
interface BatchSummary {
  id: string; source: 'drop' | 'telegram' | 'reclassify'; status: 'running' | 'done';
  title: string | null; visitor: boolean; startedAt: string; finishedAt: string | null;
  counts: { items: number; accepted: number; duplicate: number; rejected: number;
            processing: number; filed: number; review: number; unreadable: number; failed: number };  // failed = pipeline_stage 'failed'
  groupId: string;                      // its intake_batch group: "Undo whole batch" (§9.2, C7 §5.4)
  debrief: { interviewId: string; status: Interview['status']; openQuestions: number } | null;  // batches.debrief_interview_id (C6 §3)
}
interface BatchDetail { batch: BatchSummary; items: (IntakeItem & { document: DocumentSummary | null })[] }   // items in upload order
```
- `BatchQuestionsBanner` shows when `debrief.status = 'ready'` and `openQuestions > 0` (C6 §3.4, C3 §2).

## 6. Review and corrections

### 6.1 `GET /api/review?reason=&entityId=&offset&limit`
`Page<DocumentSummary>` of non-deleted documents with status `review` or `unreadable`, oldest `arrived_at` first (C4 §3.4). `reason` filters on `reasons`. The detail comes from §4.2.

### 6.2 Document actions
Every action below is a C7 A–C operation with `actor='user'`, `via='ui'`, holding the document lock (C7 §4.1). They return:
```ts
interface FileOpResult {
  document: DocumentDetail | null;      // null after delete
  outcome: 'moved' | 'unchanged';
  journalIds: number[];                 // entries written, in order
  groupId: string | null;
  undo: { journalId: number } | { groupId: string } | null;   // what the toast's Undo calls (§9.2)
}
```

| Method, path | Body | Does | Errors |
|---|---|---|---|
| `POST /api/documents/{id}/confirm` | — | Accepts the current suggestion: files the document with its current classification (`file`; the review item closes `resolution='confirmed'`, C1 §4.5). `review_items.scope` stays null | 422 `not_renderable` (no entity or no path, C5 §9.3); 409 `stale`/`conflict`; a `filed` document → 200 `unchanged` |
| `POST /api/documents/{id}/correct` | `CorrectionRequest` | C4 §3.5 behaviour steps 1–3 and 5 with the person as actor: a `method='user'` classification, alias learning (C5 §6.2.5), `doc.update` for field values, `fiscal_year` recomputed, then `file` or `move`/`rename` in a `correction` group; the review item closes `resolution='corrected'`, `scope='one'` | 400; 403 `not_allowed` (Visitors, C1 §2.1); 409 `stale`/`conflict`; the same correction again → 200 `unchanged` |
| `POST /api/documents/{id}/like-this` | `{conversationId?}` | "Every document like this" after a correction (`CorrectionScopePrompt`): C4 §3.5 step 4 for the document's latest user classification. Returns `{rule: Rule, preview: RulePreview}`. Sets the closed review item's `scope='all'` and `rule_id` | 422 `invalid_value` (`field: "counterparty"`) when the document has no counterparty; 404 when it has no user correction; again → the existing draft rule for that counterparty and action |
| `POST /api/documents/{id}/unfile` | — | "Send back to review": `unfile` (C7 §2.1); status `review`, reasons = the current classification's reasons, or `{low}` if empty; a review item opens | 409 `stale`; a document not in the archive → 200 `unchanged` |
| `POST /api/documents/{id}/delete` | `{confirm: true, fileName}` | C7 §7: moves to the trash. `fileName` must equal the document's current basename (the danger dialog shows it and sends it back), so a stale screen can't delete another file. Any open review item closes `resolution='deleted'` | 400 without `confirm: true`; 409 `stale` if `fileName` differs; 404 if already deleted |

```ts
interface CorrectionRequest {        // at least one field; omitted fields are kept (C4 §3.5)
  entityId?: string; subUnitId?: string | null;
  categoryId?: string; subcategoryKey?: string | null;
  counterparty?: { id: string } | { name: string };     // a name resolves through C5 §6.2 and teaches the alias
  docDate?: string; periodEnd?: string; dueDate?: string | null;
  amount?: Money | null;
}
```
- The HANDOFF flow: the person corrects (`/correct`), then `CorrectionScopePrompt` offers "Just this one" (nothing more to call) or "Every document like this" (`/like-this`, then the `RulePreviewCard`).
- **Delete is the person's only.** No MCP tool reaches it (C4 §2.7, C7 §7.1). The web shows the DS `Dialog tone="danger"` first; the body's `confirm` and `fileName` are the server's half of that confirmation.

## 7. Rules

| Method, path | Body | Response |
|---|---|---|
| `GET /api/rules?state=&source=&entityId=&q=&offset&limit` | — | `Page<RuleListItem>`; `entityId` matches the action's entity; `q` matches `norm(name)`; order: `state` (active, draft, disabled), then priority descending |
| `GET /api/rules/{id}` | — | `RuleListItem` |
| `PATCH /api/rules/{id}` | `RulePatch` | `RuleListItem` |
| `GET /api/rules/{id}/preview?limit=` | — | `RulePreview` (C1 §11.5), `moves` capped at `limit` (default 50, max 200), `movesTotal` full; not applied → the C4 §3.8 candidates, applied → C1 §11.5 "Applied" |
| `POST /api/rules/{id}/apply` | `{conversationId?}` | `ApplyResult` |
| `GET /api/rules/learned?since=` | — | `LearnedItem[]`: rules created since `since` (default 7 days ago) with `source IN ('interview','correction')`, newest first (`LearnedPanel`) |

```ts
interface RuleListItem { rule: Rule; valid: boolean; problems: string[] }   // C5 §4.2 item 9: references that no longer resolve
interface RulePatch {
  name?: string;                          // 1–120 chars
  enabled?: boolean;                      // true → state 'active' (a draft becomes active without re-filing anything); false → 'disabled'
  conditions?: Condition[]; action?: RuleAction; priority?: number;   // validated by C5 §4; bumps the version (C1 §3)
}
interface ApplyResult {
  preview: RulePreview;                   // now applied (C1 §11.5)
  groupId: string | null; moved: number; unchanged: number;
  failed: { documentId: string; code: string }[];
}
interface LearnedItem { rule: Rule; createdAt: string; moved: number }       // moved = done entries of its live rule_apply groups
```
- `PATCH` writes one `rule.change` entry (`before`/`after` = the changed fields and state); an invalid rule is 422 `invalid_rule` with nothing written. Toggling `enabled` doesn't bump the version (C1 §3).
- `apply` is C4 §3.9 with the person as actor: `state='active'`, the moves in one `rule_apply` group, firings counted, review items closed `rule_applied`. Idempotent: a second call moves nothing (`groupId: null`, `moved: 0`). A draft rule's preview and apply follow C5 §4.6.9.
- There is no rule delete (disable instead), and rules aren't created here: they come from the seed, interviews (§11) and corrections (§6.2).
- `Adjust` on a `RulePreviewCard` opens `/rules/:ruleId`, which edits through `PATCH`.

## 8. Registry: entities, people, categories, counterparties

Registry DTOs are C1 §11.8's, plus `EntityDetail` and `PersonDetail` below for the edit forms. Every write validates, then commits in one transaction; none moves an existing file (a renamed folder applies to later filings; existing documents move only when re-filed).

**Responses.** A write to an entity or one of its parts (sub-units, accounts, people links) returns the entity's updated `EntityDetail`; a write to a category or its subcategories and templates returns the updated `Category`; a write to a person returns `PersonDetail`. `POST` answers 201, `PATCH` and `PUT` 200, `DELETE` 204.

| Method, path | Body | Notes |
|---|---|---|
| `GET /api/entities` | — | `{items: Entity[], documentCounts: Record<string, number>, visitorsEntityId: string \| null}`, `sort_order` then name. `EntityScopeSwitcher` and `EntityCard` read it; the export dialog and the correction picker leave out `visitorsEntityId` |
| `GET /api/entities/{id}` | — | `EntityDetail`, the edit form's prefill |
| `POST /api/entities` | `EntityWrite` | `key` from `folderName` slug if absent. `purgeAfterHours` → 403 `not_allowed`: only the seed creates the Visitors entity |
| `PATCH /api/entities/{id}` | `Partial<EntityWrite>` | The Visitors entity (C1 §2.1) accepts only `displayName` and `purgeAfterHours`, which must stay a whole number from 1 to 168 (null or out of range → 422 `invalid_value`); anything else → 403 `not_allowed`. On any other entity `purgeAfterHours` → 403 `not_allowed` |
| `DELETE /api/entities/{id}` | — | The Visitors entity → 403 `not_allowed`. 409 `in_use` (`details.references`: the kinds found) when a document, classification, deadline, sub-unit, account, export or rule references it (C1 §10; entity-people links and template overrides go with it). The UI disables Delete when `documentCounts[id] > 0` |
| `POST /api/entities/{id}/sub-units` · `PATCH /api/sub-units/{id}` · `DELETE /api/sub-units/{id}` | `{key?, label, personId?}` | label unique in the entity; delete → 409 `in_use` if a document, classification or rule uses it |
| `POST /api/entities/{id}/accounts` | `{key?, label, iban, currency, subUnitId?, bankCounterpartyId?}` | the IBAN is normalised, checked (mod-97), hashed and cut to its last 4 (C1 §2.4) in the handler and **never stored, logged or echoed**; the body of this route is excluded from request logging (C9 §7). 422 `invalid_value` (`field: "iban"`) on a bad checksum; 409 `conflict` (`reason: "duplicate_account"`) when the hash exists |
| `DELETE /api/accounts/{id}` | — | 409 `in_use` if a rule names its key |
| `GET /api/people` · `POST /api/people` · `PATCH /api/people/{id}` | `{key?, displayName, shortName?, aliases?}` | `{items: PersonDetail[]}` for the list, else `PersonDetail` |
| `PUT /api/entities/{id}/people/{personId}` · `DELETE …` | `{role?}` | `entity_people`; returns the entity's `EntityDetail` (`DELETE` too, 200, since the form redraws from it) |
| `GET /api/categories` | — | `{items: Category[], documentCounts: Record<string, number>}` |
| `POST /api/categories` | `{id, labels, icon, modelDefinition, template: {pathTemplate, fileTemplate}}` | the id is the slug (C1 §1.2) |
| `PATCH /api/categories/{id}` | `Partial<…>` | templates re-parsed; 422 `invalid_template` with `details.offset` |
| `PUT /api/categories/{id}/templates/{entityId}` · `DELETE …` | `{pathTemplate, fileTemplate}` | the entity override (C1 §2.7); returns the `Category` (`DELETE` too, 200) |
| `POST /api/categories/{id}/subcategories` · `PATCH /api/categories/{id}/subcategories/{key}` | `{key?, labels}` | |
| `POST /api/templates/preview` | `{pathTemplate, fileTemplate, documentId?, entityId?}` | `TemplatePreview` (200), the `CategoryEditor` preview: rendered with C5 §8 against `documentId`, else against a fixed synthetic sample (C5 §8.5 case 5's values) under `entityId` or the first practice entity |
| `GET /api/counterparties?q=&limit=` | — | `Counterparty[]` (C1 §11.8), matching `norm(q)` against names and aliases (trigram, best first); the correction picker's `Combobox` |

```ts
interface EntityWrite {
  key?: string; displayName: string; folderName: string; legalForm?: string | null; siren?: string | null;
  visibility: 'practice' | 'personal'; fiscalYearEnd: string /* "MM-DD" */; filingLanguage?: Lang | null;
  aliases?: string[]; addresses?: string[]; purgeAfterHours?: number | null; sortOrder?: number;
}
interface EntityDetail extends Entity { aliases: string[]; addresses: string[]; purgeAfterHours: number | null; sortOrder: number }
interface PersonDetail extends Person { aliases: string[] }
interface TemplatePreview { path: string[]; fileName: string | null; error: { template: 'path' | 'file'; offset: number; message: string } | null }
```
- `labels` must carry `en`, `fr` and `ro` (C1 §2.6); `icon` is the DS union; slugs follow C1 §1.2. Violations are 422 `invalid_value` with `field`.
- `siren` is accepted with or without spaces and stored as 9 digits (C1 §2.1). SIRENs, aliases and addresses are served in `EntityDetail` (the owner sees them); IBANs never are.
- An omitted array (`aliases`, `addresses`) is left as it is; `[]` clears it.

## 9. Journal and activity

### 9.1 Reading
| Method, path | Response |
|---|---|
| `GET /api/activity?actor=&entityId=&kind=&q=&cursor&limit` | `ActivityPage` (`Feed`), newest first |
| `GET /api/journal/groups/{id}` | `{group: JournalGroup, entries: JournalEntry[], documents: DocRefs}`, entries in id order |
| `GET /api/journal/{id}` | `{entry: JournalEntry, documents: DocRefs}` |

```ts
type DocRefs = Record<string, { title: string; fileName: string; deleted: boolean }>;
type ActivityItem =
  | { kind: 'group'; group: JournalGroup; preview: JournalEntry[]; entriesTotal: number;   // first 5 entries
      redoGroupId: string | null }       // the live undo group targeting this one, for "Redo" (C7 §5.4)
  | { kind: 'entry'; entry: JournalEntry };                                                 // an entry with no group
interface ActivityPage extends Feed<ActivityItem> { documents: DocRefs; rules: Record<string, { name: string }> }
```
- `actor` is `mona` or `user` (the `ActivityFilters` "by Mona" / "by you"; "by you" means done by you in the app, D5). `kind` filters on the group kind or the entry action. `q` matches document titles and file names (`norm`). `entityId` keeps items touching a document of that entity.
- Items are ordered by their time (`op_groups.created_at` or `file_ops.at`), then id. Only `fs_state='done'` entries appear (C1 §5).
- Deleted documents keep their journal: `DocRefs[...].deleted` is true.

### 9.2 Undo and redo
| Method, path | Body | Does |
|---|---|---|
| `POST /api/journal/{id}/undo` | `{conversationId?}` | C7 §5.3 on the entry (acting on its chain tip; undoing an undo is a redo) |
| `POST /api/journal/groups/{id}/undo` | `{conversationId?}` | C7 §5.4. Redo of a group = this call on the undo group (`redoGroupId`) |

```ts
interface UndoResult {
  groupId: string | null;
  undone: { journalId: number; documentId: string; title: string; to: PathState }[];
  skipped: { journalId: number; state: 'superseded' | 'already_undone' | 'not_undoable' | 'not_allowed' }[];
  entries: JournalEntry[];                // the new undo/redo entries
  ruleStates: { ruleId: string; state: Rule['state'] }[];   // rule states changed by C6 §7.3
}
```
- A single entry that is not undoable answers 409 `superseded`, 409 `already_undone` or 422 `not_undoable`, with nothing changed. A group with nothing undoable answers the same way; a group with some undoable entries answers 200 and lists the rest under `skipped`.
- The person may undo a restore (moving a document back to the trash) because the actor is `user` (C7 §7.1 refuses only `mona`).
- Toasts call these with the `undo` target from §6.2 and stay at least 8 s (HANDOFF §4).

## 10. Deadlines and reminders

| Method, path | Body | Response |
|---|---|---|
| `GET /api/deadlines?withinDays=&includeOverdue=&status=&entityId=&offset&limit` | — | `Page<Deadline>`, soonest first; defaults: `withinDays` 30 (0–366), `includeOverdue` true, `status` `open`. Deadlines of Visitors documents are left out (C9 §5.5) |
| `PATCH /api/deadlines/{id}` | `{status: 'open' \| 'done' \| 'dismissed'}` | `Deadline` |
| `POST /api/reminders` | `{deadlineId?, documentId?, remindOn, note?, conversationId?}` | 201 (200 when it existed) `ReminderResult` |
| `DELETE /api/reminders/{id}` | — | 204; `status='cancelled'` |

- **Deadline "Done"** closes C1 open question 1: `DeadlineCard` and Home's `DueCard` offer Done (`status='done'`); the Deadlines list offers Dismiss and Reopen. Mona never changes a deadline's status in v1. The change isn't journaled (C1 has no deadline-status action, and it moves no file); the same PATCH reverses it.
- `POST /api/reminders` mirrors C4 §3.11 with `created_by='user'` and a `reminder.add` entry (`user`/`ui`): one of `deadlineId`/`documentId`; `remindOn` today or later (Europe/Paris), else 422 `invalid_value`; idempotent on (target, `remindOn`). `note` ≤ 200 chars. `interface ReminderResult { reminderId: string; remindOn: string; created: boolean; deadline: Deadline | null }`.

## 11. Interviews (semantics: C6)

| Method, path | Body | Response |
|---|---|---|
| `GET /api/interviews/{id}` | — | `Interview` (C6 §5.1), polled while `generating` |
| `GET /api/interviews?status=&kind=&offset&limit` | — | `Page<Interview>` (questions included), newest first |
| `POST /api/interviews` | `{scope: InterviewScope, lang?}` | 201 `{interview, reused: false}` or 200 `{interview, reused: true}` (C4 §3.6 reuse, C6 §2.3) |
| `POST /api/interviews/{id}/questions/{qid}/answer` | `{optionId?, freeText?, conversationId?}` | `AnswerResult` (C6 §6) |
| `POST /api/interviews/{id}/questions/{qid}/skip` | `{conversationId?}` | `InterviewQuestion` |
| `POST /api/interviews/{id}/questions/{qid}/apply` | `{conversationId?}` | `{results: ApplyResult[]}`: "Apply all" for a multi-branch answer, one C4 §3.9 application per rule in branch order (C6 §7.1) |
| `POST /api/interviews/{id}/cancel` | — | `Interview` (C6 §8) |

`InterviewScope` and `AnswerResult` are C6's (§2.1, §6). Exactly one of `optionId`/`freeText` (`freeText` ≤ 500). Checks, in this order (C6 §6.4):
1. the same answer again → 200 with the existing result, whatever the interview's status;
2. a different answer to an answered question → 409 `already_answered`;
3. answering or skipping an open question of an interview that is `generating`, `failed` or `cancelled` → 409 `conflict` (`reason: "interview_not_ready"`).

`…/apply` needs an answered question whose rules are `draft` or `active`, and returns one `ApplyResult` per rule; a repeat re-applies active rules and moves nothing (`moved: 0`, `groupId: null`, §1.4). Only when no rule is `draft` or `active` does it answer 409 `conflict`, `reason: "nothing_to_apply"`. The interview may be `ready` or `done`.

## 12. Drafts and exports

| Method, path | Body | Response |
|---|---|---|
| `GET /api/drafts/{id}` | — | `Draft` (C1 §11.7); `docxUrl` = `/api/drafts/{id}/docx` once `ready` |
| `GET /api/drafts/{id}/docx?conversationId=` | — | the `.docx` (`Content-Disposition: attachment`); with `conversationId`, writes the `draft.download` note (C3 §6.2) |
| `GET /api/exports?entityId=&offset&limit` | — | `Page<ExportPack>`, newest first |
| `GET /api/exports/preview?entityId=&fiscalYear=` | — | `ExportPreview` for `AccountantExportDialog` |
| `POST /api/exports` | `{entityId, fiscalYear}` | 201 `ExportPack` (`building`), or 200 with the one already building for the same entity and year (C4 §3.13) |
| `GET /api/exports/{id}` | — | `ExportPack`; `zipUrl` = `/api/exports/{id}/zip`, `csvUrl` = `/api/exports/{id}/csv` once `ready` |
| `GET /api/exports/{id}/zip` · `/csv` | — | the files (`Content-Disposition: attachment`) |

```ts
interface ExportPreview {
  entityId: string; fiscalYear: number;
  documentCount: number;                                // filed, non-deleted, documents.fiscal_year = year (C9 §3.3)
  inReview: number;                                     // same entity and year, still in review: not included
  categories: { id: string; label: string; count: number }[];
  fiscalYears: number[];                                // years that have documents for this entity, newest first
}
```
- A personal entity or the Visitors entity → 403 `not_allowed` on preview and build (C4 §3.13, C9 §3). The dialog lists practice entities only.
- "Destination": the pack is written under `/data/exports` on the box (C4 §3.13) and downloaded by the browser to the person's Downloads folder. Nothing is sent (R32).
- Drafts are started from chat only (`draft_reply`, C4 §3.12); there is no REST create in v1.

## 13. Conversations and chat (shape: C3)

| Method, path | Response |
|---|---|
| `POST /api/chat` | C3 §2–§4 (UI Message Stream); session, CSRF and lock as §2 |
| `GET /api/conversations?q=&cursor&limit` | `Feed<ConversationSummary>` (C3 §7.1), newest `lastMessageAt` first; `q` matches `norm(title)` |
| `GET /api/conversations/{id}/messages` | `UIMessage[]` (C3 §7.2) |

C3 §2's pre-stream errors use §1.2's envelope. Conversations can't be renamed or deleted in v1.

## 14. Card actions and notes

A card action is an endpoint called from a card rendered in a conversation. It carries that conversation's id as `conversationId` (body, or query for `GET`), and in the **same transaction** as its effect it inserts the C3 §6.1 note for that conversation. Actions that move several documents (both applies and the group undo) commit each document on its own (C7 §4.3); they write the note in one final transaction after the last move, with the final counts:

| Endpoint | Note `kind` (C3 §6.2, C6 §9) |
|---|---|
| `POST /api/interviews/{id}/questions/{qid}/answer` | `interview.answer`, or `interview.answer_text` for a free-text answer |
| `POST /api/interviews/{id}/questions/{qid}/skip` | `interview.skip` |
| `POST /api/rules/{id}/apply` and `…/questions/{qid}/apply` | `rule.apply` (one per applied rule) |
| `POST /api/journal/{id}/undo`, `POST /api/journal/groups/{id}/undo` | `undo` |
| `POST /api/reminders` | `reminder.add` |
| `GET /api/drafts/{id}/docx` | `draft.download` |
| `POST /api/documents/{id}/like-this` | none in v1 (the correction happens outside chat) |

- An unknown `conversationId` is ignored (the action still happens; no note). Without `conversationId` there is no note: Review, Activity and Rules pages create none (C3 §6.1 item 4).
- Note texts are built exactly as C3 §6.2 says, with its single-line, quote and 80-character rules.

## 15. Settings and system status

### 15.1 `GET /api/settings`, `PATCH /api/settings`
One view over `profile` and `settings` (C1 §8):
```ts
interface SettingsView {
  profileName: string; locale: Lang; autoLockMinutes: number;              // profile
  practiceName: string; filingLanguage: Lang;                              // settings
  confidenceHigh: number; confidenceLow: number; badgeHours: number;
  debriefQueueThreshold: number; debriefEarlyMin: number;                // C6 §3.2–§3.3
}
type SettingsPatch = Partial<SettingsView>;
```
- Validation (422 `invalid_value`, `field`): `0 < confidenceLow < confidenceHigh ≤ 100`; `autoLockMinutes` 1–1440; `badgeHours` 1–168; `debriefQueueThreshold` and `debriefEarlyMin` 1–50; `profileName` and `practiceName` 1–120 chars.
- New thresholds apply to classifications made afterwards (C5 §9.4). A `locale` change applies to the next request (the web switches i18next and `<html lang>` at once, C8 §3.1).
- Settings changes are not journaled.

### 15.2 `GET /api/system/status`
Settings › System status and the `SystemStatusLine` detail. Each probe has a 2 s timeout; the result is cached 30 s; a failed probe gives nulls, never an error status.
```ts
interface SystemStatus {
  version: string; build: string | null;                 // package version; git sha from the image build arg, else null
  env: 'dev' | 'prod';
  mona: { status: 'online' | 'offline'; hermesVersion: string | null };   // Hermes GET /health
  llm: {
    endpoint: 'local' | 'openrouter';                    // C9 §1
    model: string | null;                                // prod: the loaded model id; dev: the configured OpenRouter model
    quantization: string | null;                         // parsed from the GGUF file name in /props (e.g. "Q4_K_XL")
    contextPerSlot: number | null; slots: number | null; // /props n_ctx and total_slots
    vramBytes: null;                                     // not readable from the api container in v1 (mona doctor has it)
  };
  queues: { llm: { todo: number; doing: number }; cpu: { todo: number; doing: number } };
  database: 'ok' | 'error';
  disk: { dataFreeBytes: number; dataTotalBytes: number };   // statvfs of /data
  privacy: { cloudAi: boolean; telegram: boolean };      // C9 §1: cloudAi = env is dev; telegram = the owner bot is configured
}
```
- **Prod probes** (C9 §1): `GET {MONA_LLM_BASE_URL}/models` (llama-swap's model list) and `GET {root}/upstream/{model}/props` (llama-server's `/props` through llama-swap's upstream passthrough), where `root` is `MONA_LLM_BASE_URL` with a trailing `/v1` removed. There is no separate root variable, so the probes can't reach a host C9 §1.2's check didn't pass. L6 confirms both paths on mona's pinned llama-swap on Oct 8; a different path is a C2 amendment, not a lane choice.
- **Dev** makes no call to OpenRouter for status: `model` comes from configuration, the rest is null.

## 16. OpenAPI → TypeScript client

1. FastAPI generates the schema. `mona openapi` writes `apps/api/openapi.json` (W0), which is committed.
2. `npm run gen:api -w apps/web` writes `apps/web/src/api/schema.gen.ts` with `openapi-typescript` (committed). `make api-client` (CI, D1) regenerates into a scratch file and fails on any difference, so a server change without a regenerated client can't merge.
3. The web calls the API through `openapi-fetch` (`apps/web/src/api/client.ts`) with two middlewares: add `X-CSRF-Token` to non-GET requests; on 401 or 423, stop polling and route to `/unlock?next=<the current route>`, which returns there after the unlock (so the person lands back on the chat or Intake page they were on). `next` is used only when it starts with a single `/`; anything else goes to Home.
4. Every route has an explicit camelCase `operation_id` (`getDocument`, `correctDocument`, `undoJournalEntry`, …), a `response_model`, and its error statuses declared with `ApiError` (`responses={409: {"model": ApiError}, …}`).
5. Schema component names equal the DTO names in C1 §11 and this contract (`DocumentSummary`, `BatchSummary`, …). The app sets `separate_input_output_schemas=False` so a model used both ways stays one component.
6. `/api/chat` is in the schema with a `text/event-stream` response (the web uses the AI SDK transport for it, not `openapi-fetch`). Uploads are `multipart/form-data` and use `openapi-fetch`'s `bodySerializer` with `FormData`. `/mcp` is excluded (`include_in_schema=False`).

## 17. Test obligations

**[M]** = mutation-checked (break the code, watch the test fail, restore).

1. **Error envelope [M].** For one route per status in §1.2, the body validates against `ApiError`; a FastAPI validation error and an unknown route come out in the envelope. Mutation: remove the validation-error handler → the test fails.
2. **Auth and lock [M].** No cookie → 401 on a protected route; unlock with the right password → cookie with `HttpOnly`, `SameSite=Strict`; wrong password → 401 and no cookie; the sixth failure within the window → 429 with `Retry-After`; a burst of 20 concurrent wrong unlocks verifies at most 5 passwords (the verify is counted) and the rest get 429. With the clock injected: a session idle past `auto_lock_minutes` gets 423 on a GET and a POST; polling GETs alone don't prevent it; a heartbeat does; `POST /api/auth/lock` locks a second live session; unlock unlocks this session and leaves an idle one locked; the allowlist answers while locked. Mutation: count GETs as activity → the polling test fails.
3. **CSRF [M].** A POST without `X-CSRF-Token`, with a token from another session, and with a foreign `Origin` → 403 `csrf_failed`; `/api/chat` and the upload need it too. Mutation: skip the Origin check → a test fails.
4. **Service key isolation.** `Authorization: Bearer $MONA_SERVICE_KEY` on `/api/documents` → 401; on `/mcp` → accepted (C4 test 1).
5. **Upload.** A batch of PDF, JPEG, PNG, a renamed `.exe`, an empty file and a truncated PDF → accepted ×3, `unsupported_type`, `empty`, `unreadable_file`; items and `extract_text` jobs in part order; the same PDF again → `duplicate`; a trashed document's bytes → `duplicate` with `deleted: true` and `restoreJournalId`, and undoing that entry restores it; `visitor=true` → `batches.visitor`; 51 files → 413 with nothing written.
6. **Corrections.** `/correct` writes a `user`/`ui` classification and a `correction` group, closes the review item `corrected`/`one`, and teaches the counterparty alias; the same body again → `unchanged`; a Visitors target → 403; `/like-this` → a draft rule whose preview matches `GET /api/rules/{id}/preview`; again → the same rule.
7. **Delete [M].** Without `confirm` → 400; with the wrong `fileName` → 409 `stale`; right → trash, `delete` entry `user`/`ui`, undoable; no MCP path deletes (C4 test 10). Mutation: skip the `fileName` comparison → a test fails.
8. **PDF endpoint.** A scanned document serves the cached OCR'd copy; a born-digital one serves the archive bytes; after a move, the same URL serves the bytes at the new path (resolved per request); `Range: bytes=0-99` → 206 with 100 bytes; a deleted document → 404; an image before OCR → 404 `not_ready`.
9. **Visibility on REST.** The web channel sees personal entities; export preview and build of a personal or Visitors entity → 403 (C9 test 3).
10. **Undo via REST.** Entry undo, group undo, and group redo through `redoGroupId` follow C7 §5 (C7's property tests cover the semantics; this checks the HTTP mapping and `UndoResult`); a superseded entry → 409 with nothing changed.
11. **Notes [M].** Each §14 endpoint with `conversationId` writes exactly one note of the listed kind; without it, none. For the single-transaction actions (answer, skip, reminder, draft download, single-entry undo) a failure after the note rolls both back. The multi-document actions (both applies, group undo) write their note once, after the last move, with the final counts. Mutation: write a single-transaction action's note after commit → the rollback test fails.
12. **Polling.** The §1.5 endpoints return an `ETag` and 304 on `If-None-Match`; an interview moves `generating` → `ready` between two polls with the job stubbed.
13. **OpenAPI parity.** `make api-client` passes; every route has an `operationId`; every DTO named in C1 §11 and here is a schema component under its exact name.
14. **Registry.** An IBAN posted to `/accounts` appears nowhere in the DB dump, the api log or the response (C1 test 3 applied to REST); a template with a stray brace → 422 `invalid_template` with the offset; deleting an entity referenced by a document, by a sub-unit only, or by a classification only → 409 `in_use` (never 500); deleting the Visitors entity → 403; `purgeAfterHours` in a POST, or in a PATCH of a practice entity → 403; `purgeAfterHours: null` or 169 on Visitors → 422 and the purge setting unchanged; `GET /api/entities` names `visitorsEntityId`; every write returns its documented DTO and status.
15. **Settings.** `confidenceLow ≥ confidenceHigh` → 422 with nothing written; a locale change is reflected by `GET /api/auth/state`.
16. **Body limits before auth [M].** Against a real uvicorn: an unauthenticated `POST /api/intake` declaring 300 MB, and one streaming past 250 MB chunked, are refused (401, or 413 for the chunked one once past the limit) with fewer than 1 MiB of the body read; a 70 KiB JSON body to a JSON route → 413 before parsing. Mutation: move the session check into a route dependency → the byte-count assertion fails.
17. **Interview answers.** On a single-question `depends` interview: answer (the interview becomes `done`), repeat the answer → 200 with the same rules; Apply all → one `ApplyResult` per rule; a different answer → 409 `already_answered`; answering a question of a `generating` interview → 409 `interview_not_ready`.

## 18. Open questions

Nothing is open in this contract. Settled at the fold (W1-B report numbers in brackets): reads are refused while locked [1]; unlocking on one device also unlocks other *active* sessions after a manual Lock (one owner) [10]; untracked archive files aren't listed in the folder tree [17]; deadline status changes aren't journaled, and a `deadline.change` action can come later as an additive C1 amendment [18].

Follow-up, decided and waiting on a measurement:
1. **System status probe paths** (§15.2) [8]. L6 confirms llama-swap's model list and upstream `/props` paths on mona's pinned llama-swap on Oct 8; the orchestrator amends if they differ. Blocks only the Settings › System status tile.

## Changes in 0.2

- Intake polls while the batch runs **or** its debrief is `generating` (§1.5) (G4).
- Registry: `visitorsEntityId`, `GET /api/entities/{id}` → `EntityDetail`, `PersonDetail`; response type and status for every write; `in_use` for every referencing row; the Visitors entity can't be deleted; `purgeAfterHours` is 1–168 on Visitors and refused elsewhere (§8, test 14) (G22, G38, G45, G61).
- Interview endpoints: repeats first, then `already_answered`, then not-ready for open questions only; Apply all needs only an answered question (§11, test 17) (G15, G42).
- `outcome: "unchanged"` exists only on `FileOpResult` (§1.4) (G43).
- Home's activity carries `documents` and `rules` like `ActivityPage` (§3.2) (G44); Visitors documents are left out of `BriefFacts` and deadlines (§3.2, §10; C9 §5.5) (G53).
- Multi-document card actions write their note after the last move (§14, test 11) (G39).
- Auth, lock, CSRF and body limits run in middleware and at Caddy before the body is read (§2.7, §5.1, test 16) (G60); the unlock throttle counts before verifying, one verify at a time (§2.5, test 2) (G59).
- The status probes derive their root from `MONA_LLM_BASE_URL` (§15.2) (G24).
- The ask label is not a request-locale string (§1.1 item 5) (G20).
- `/unlock?next=` returns to the page the person was on (§16 item 3) (G29).
- `auth_sessions.updated_at`; the header's user/ui sentence narrowed; `auth.unlock.hint` defined in C8 §5.7 (§2.1, §2.2) (G27).
- `debriefEarlyMin` in `SettingsView` (§15.1) (orchestrator ruling on the early debrief).
- Open questions settled per the orchestrator [1, 8, 10, 17, 18].
- Post-verify fixes (orchestrator): §2.7 exceptions (unlock skips CSRF; lock/logout skip only the lock check; `/api/chat` keeps C3's 32 KiB/400); Apply all is idempotent on active rules; Intake polls 30 s past `finishedAt` while the debrief is pending.
