# C7 · File-ops invariants

| | |
|---|---|
| Version | 1.0 |
| Status | **Frozen** (set A verdict: Andrei, 2026-09-30) |
| Freeze | 2026-09-30 |
| Change rule | Amend via `docs/contracts/amendments.md`, orchestrator only |
| Consumers | L1 (implements `mona.fileops`), L2 (REST and MCP callers: corrections, undo, delete, rule apply), L3 (undo UI, badge, superseded state), L5 (demo-reset, fixtures) |
| Depends on | C1 (`documents`, `file_ops`, `op_groups`), C5 (§8 rendering). Forward: C2 (delete endpoint and confirmation), C6 (interview apply/undo), C9 (Visitors purge) |

Every change to where a document lives goes through one library, `mona.fileops`. Nothing else in the codebase renames, moves or deletes a document file. The rules below are its contract.

**Changes in 0.2**
- Actor = who executed (§2.1; D5, closes the C1 actor question).
- The attachment root is Hermes' media cache, mounted read-only at the same path (§1; F23, F52).
- Every path component must sit on the root's filesystem (§3; F13).
- Failures inside an operation: `ENOENT` retried once, anything else rolled back and the entry marked `failed`; pipeline filing failures go to review; the lock lives on one connection (§4.1, §4.2; F13, F39, F49).
- Recovery re-checks under the lock that the entry is still pending and the document still at `before` (§4.3; F49).
- Review resolutions come from the caller (§4.2 C.3; F44).
- Undo after redo: an entry's live state follows its undo chain, and undo acts on the chain's tip (§5.2, §5.3, §5.4; F26). A failed undo doesn't block a retry (§5.3; F50).
- Undo and redo restore `filed_by`/`filed_at` (§6; F40).
- Mona can never move a document to the trash, by any path (§4.2, §7, §9 invariant 12; F53).
- Adoption: crash ordering, recovery shape and invariant 2's exemption (§8.3, §9; F41, F56). A re-upload of a trashed document offers Restore (§8.4; F57).
- The intake group is created with the batch (§5.4; F15, F37).
- Open questions 1, 2, 4, 5 and 6 adopted as proposed; 3 goes to C6.
- Post-verify fixes (orchestrator): open-question 2 cites §5.3 item 7.

## 1. Roots and paths

| Root | Path | Holds |
|---|---|---|
| data | `$MONA_DATA_DIR` (default `/data`) | everything below |
| inbox | `/data/inbox` | documents not filed: `processing`, `review`, `unreadable`. Name: `<document_id>.<ext>`, flat |
| archive | `/data/archive` | filed documents, at their rendered path (C5 §8) |
| trash | `/data/trash` | deleted documents: `<document_id>/<basename at deletion>` |
| attachments | `/opt/data/cache` (`ATTACH_ROOT`) | Hermes' Telegram media cache (`$HERMES_HOME/cache`, D3), mounted **read-only** into the api at the same absolute path through a volume subpath (never the whole Hermes profile, which holds `.env` and `state.db`). Only its `documents/` and `images/` subtrees are read (C4 §4.2). Hermes prunes both hourly after 24 h |

1. `documents.location` names one of inbox, archive or trash; `documents.current_path` is relative to it (C1 §1.3.5).
2. **inbox, archive and trash are on one filesystem.** The API and the `cpu` worker check `st_dev` of the three at startup and refuse to start if they differ (and `mona doctor` reports it). This is what makes a move a rename-class operation.
3. Root paths are resolved with `realpath` once at startup; the resolved values are the ones compared in §3.
4. The inbox and trash belong to Mona. The archive may also hold files a person put there by hand; Mona never moves, renames or deletes an untracked file (except as §8.3 describes: it leaves it where it is).

## 2. Journal entries

### 2.1 Actions
| Action | From → to | Undoable kind (§5.1) | Who |
|---|---|---|---|
| `file` | inbox → archive (first filing) | yes | Mona (pipeline, rules), you (review confirm/correct) |
| `move` | archive → archive, folder changed | yes | Mona (rule apply), you |
| `rename` | archive → archive, same folder, new name | yes | Mona, you |
| `unfile` | archive → inbox (back to review) | yes | you |
| `delete` | inbox or archive → trash | yes | **you only** |
| `undo` | reverses its `undo_of` entry | yes (undoing it is a redo) | Mona (MCP `undo`), you |
| `redo` | reverses an `undo` | yes (undoing it is an undo) | Mona, you |
| `doc.update` | fields changed, no file change | no (v1) | Mona, you |
| `rule.create`, `rule.change` | rule snapshot before/after | no (v1; C6 may amend) | Mona, you |
| `deadline.add`, `reminder.add` | snapshot after | no (v1) | Mona, you |
| `mark.unreadable` | status change only | no | Mona (pipeline) |

`actor` is who executed (D5, C1 §5): REST calls from the web UI → `user`/`ui`; MCP tools → `mona`/`chat` or `telegram` (Hermes cron included); pipeline → `mona`/`pipeline`. "You" in the table means a direct action in the web UI.

### 2.2 PathState (the `before`/`after` of path entries)
Stored in `file_ops.before`/`after`:
```json
{"location": "archive", "path": "Cabinet Marchand/Appels de paiement/2025/2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf",
 "status": "filed", "reasons": [], "classification_id": "cls_…", "rule_id": "rul_…",
 "filed_by": "mona", "filed_at": "2026-10-14T07:02:11Z"}
```
- `path` is the full relative path including the file name.
- `classification_id` and `rule_id` capture what the document "was" at that point, so an undo restores the document's entity, sub-unit, category, subcategory, counterparty, confidence and band from that classification, not just its path.
- The DTO form is C1 §11.6 `PathState` (`path` split into folder segments + `fileName`).
- Optional keys used by §8.3: `adopted: true`, `trash_copy: "<doc_id>/<name>"`.

## 3. The move-inside-root guard

`resolve_inside(root, rel) -> absolute path`, used for every source and target, before any filesystem change:
1. Reject `rel` if it is absolute, contains U+0000 or `\`, or has an empty, `.` or `..` segment. Normalise it to NFC.
2. `abs = root_real / rel`.
3. Walk the parent directories from the root down. Each existing component must be a directory, **not a symlink** (`lstat`), and on the root's filesystem (`st_dev` equal to the root's, so a mount point inside the archive is refused). Missing components are created one at a time (`mkdir`, mode `0o750`), and re-checked with `lstat` after creation.
4. If the final component exists, `lstat` must show a regular file, not a symlink.
5. `realpath(parent of abs)` must equal `root_real` or start with `root_real + "/"`.

Any failure raises `ForbiddenPath` before any change; the caller reports `forbidden_path` (C4 §2.4) and logs the relative path (never file contents). The same check runs on the source path of every move.

## 4. Atomic move, journal and crash recovery

### 4.1 One document, one operation
Every operation on a document holds `pg_advisory_lock(hashtextextended(document_id, 0))` (session-level) from step A to step C, so two operations on one document never interleave. Different documents proceed in parallel. The lock is taken and released on one dedicated connection, with `pg_advisory_unlock` in a `finally`, so a pooled connection never carries a stale lock. File ops run inline in the API/MCP request for single documents and groups (demo scale ≤ 200 documents), and in `file_document` on the `cpu` queue for pipeline filing; the lock makes both safe together.

### 4.2 Steps
**A. Intent (transaction 1).**
0. If the document has a `pending` entry, run §4.3 recovery for it first (this operation already holds the lock).
1. Re-read the document. If its `(location, current_path)` differs from what the caller computed its change from, abort with `stale` (nothing written).
2. If `actor = 'mona'` and the target location is `trash`, abort with `not_allowed` (nothing written), whatever the action (`delete`, `undo`, `redo`; §7).
3. Render the target (C5 §8) and pick a free name (§8). A `ForbiddenPath` from §3 aborts here, with nothing written.
4. Insert the `file_ops` row: `fs_state='pending'`, `before` = current PathState, `after` = target PathState, plus actor, via, action, group, batch, rule, confidence, band, `undo_of`. For `file`, `move` and `rename` landing in the archive, `after.filed_by`/`after.filed_at` are this entry's actor and time; for `undo`/`redo`, `after` is the reversed entry's PathState as recorded (§5.3). Commit.

**B. Filesystem.**
1. `os.link(src, dst)`.
   - `EEXIST`: if the existing file's sha256 equals the document's → §8.3; otherwise take the next suffix (§8.1), update the pending row's `after` (own short transaction), retry.
   - `ENOENT` on the destination side (another document's step D removed an empty folder after §3 created it): re-run §3 for `dst`, retry once.
2. `fsync` the destination directory.
3. `os.unlink(src)`; `fsync` the source directory.

**Any other error after A.4** (in B or C: `EACCES`, `ENOSPC`, `EIO`, a second `ENOENT`, `EXDEV`, …) is handled before the lock is released:
- if `dst` exists and is the same inode as `src`, unlink `dst` (roll back);
- else if `src` is gone and `dst` holds the document's sha256, run step C (the move had completed);
- the entry is then `failed` unless step C ran, and the error goes to the caller: `conflict` with the errno name for REST and MCP, and for pipeline filing C5 §1.2 sends the document to review;
- if this cleanup itself fails, the entry stays `pending` for §4.3.

**C. Commit (transaction 2).**
1. Update the document: `location`, `current_path`, and the state in `after` (status, reasons, classification pointer and the fields it implies, `rule_id`, `filed_by`, `filed_at`, `filed_op_id`).
2. `fs_state='done'` on the entry; for `undo`/`redo`, set the target entry's `undone_by` to this entry's id.
3. Keep the review invariant (C1 §4.5): entering `review`/`unreadable` opens a review item with the state's reasons; leaving closes the open item with the `resolution` the caller passed (C1 §4.5: `confirmed`, `corrected`, `rule_applied`, `deleted`; default `refiled`), `resolved_by` = actor.
4. Commit.

**D. Tidy.** Remove the source's parent directories that are now empty, walking up and stopping at (never removing) the root. Archive only.

**The journal entry becomes visible (`fs_state='done'`) in the same transaction as the document's path update.** Entries that are `pending` or `failed` are hidden from every read path except recovery.

A move to the document's current path is a no-op: no entry, result `unchanged`.

### 4.3 Recovery
`recover_pending()` runs at API startup, at `cpu` worker startup, before `demo-reset` takes or restores a snapshot, and as a periodic `cpu` job every 60 s for entries pending more than 30 s. For each `pending` entry, oldest first, under the document lock:
1. Re-read the entry `FOR UPDATE`; if it is no longer `pending`, skip it.
2. If the document's `(location, current_path)` is not the entry's `before`, a later operation has moved it: mark the entry `failed` and touch nothing else.
3. Otherwise apply the table (for an adoption entry, §8.3, "dst" is `after.trash_copy` in the trash root, and step C also requires the file at `after.path` to hold the document's sha256; else `failed`):

| src exists | dst exists | Then |
|---|---|---|
| yes | no | the move never happened → `fs_state='failed'` |
| yes | yes, same inode as src | the link happened, the unlink didn't → unlink src, then step C |
| yes | yes, different inode | the name was taken by something else → `failed` |
| no | yes, sha256 = document's | step C |
| no | no, or dst sha256 differs | `failed`; `documents.pipeline_error='missing_file'`; `mona doctor` lists it |

A pipeline `file` entry that ends `failed` here sends its document to review (C5 §1.2). Group operations are not atomic as a whole: each document is its own A–C unit, and the group's result lists per-document outcomes.

## 5. Undo and redo

### 5.1 Undoable kinds
`file`, `move`, `rename`, `unfile`, `delete`, `undo`, `redo`. Every other action has `file_ops.undoable=false`.

### 5.2 Live state of an entry (`JournalEntry.undoState`)
The **undo chain** of a `done` entry `e` is `e, e.undone_by, e.undone_by.undone_by, …` (each element reverses the previous one); its **tip** `tip(e)` is the last element, and `depth(e)` the number of elements after `e`. An odd depth means `e`'s effect is reversed; an even depth (0 included) means it is in place, possibly through a redo.

For a `done` entry `e` about document `d`:
1. kind not undoable → `not_undoable`;
2. `depth(e)` odd → `undone`;
3. `(d.location, d.current_path) ≠ (tip(e).after.location, tip(e).after.path)` → **`superseded`** (shown, disabled);
4. otherwise → `undoable`.

Consequences:
- Undoing the latest entry of a document can make its previous entry undoable again (its `after` is current again), so a chain unwinds step by step.
- After undo then redo, the original entry reads `undoable` again, the undo entry reads `undone`, and the redo reads `undoable` (the demo's 10:30 beat: the Hello bank row doesn't say "Undone" after Redo).

### 5.3 Single undo and redo
`undo(e)` requires `undoState(e) = 'undoable'`; otherwise it changes nothing and returns `superseded`, `already_undone` or `not_undoable`. It acts on `t = tip(e)` (`t = e` when nothing has undone `e`):
1. It is an A–C operation with `before = t.after`, `after = t.before` (the state, not just the path), `undo_of = t.id`, action `redo` if `t.action = 'undo'`, else `undo`.
2. If `t.before`'s path is now occupied, §8 applies and the entry records the path actually used.
3. When the restored state's status is `processing` (undoing a pipeline filing, directly or through a chain), the document gets `status='review'` with that state's reasons, or `{low}` if they are empty: it goes back to the queue.
4. Undoing a `delete` puts the file back where it was and clears `deleted_at`.
5. **Undo of an undo is redo**: the redo entry reverses the undo; undoing the redo is an undo again. No depth limit.
6. Available forever, subject to §5.2 (toast, activity log, document history).
7. A path undo doesn't undo field corrections: a correction that changes a date writes `doc.update` (not undoable in v1) plus a `rename`, and undoing the rename restores the old name, not the old date. Entity, sub-unit, category, subcategory and counterparty come back, since the classification pointer travels with the PathState (§2.2).
8. A second live undo of the same entry violates `file_ops_undo_of_live` (C1 §5) and is reported as `already_undone`. A `failed` undo attempt doesn't count, so the person can retry.

### 5.4 Group undo
`undo_group(g)`:
1. `E` = `done` entries with `group_id = g` and an undoable kind, **in descending id order (reverse journal order)**.
2. Create group `u`: `kind = 'redo'` if `g.kind = 'undo'`, else `'undo'`; `target_group_id = g`; actor and via of the caller.
3. For each `e` in `E`: if `undoState(e) = 'undoable'`, `undo(e)` (acting on `tip(e)`, §5.3) with `group_id = u`; otherwise skip it and report `{id, state}`.
4. Result: `{group_id: u, undone: [entry ids], skipped: [{id, state}]}`. If nothing was undoable, no group is created and the result is `already_undone` or `not_undoable`.

Group live state (`JournalGroup.undoState`), over `E`: none undoable and some undone → `undone`; none undoable and none undone → `not_undoable`; all undoable → `undoable`; otherwise `partial`. Undo of a group is allowed whenever at least one entry is undoable. **Group redo is the group undo of the undo group.**

"Undo whole batch" is `undo_group` on the batch's `intake_batch` group, created with the batch (C1 §4.1).

## 6. The "filed by Mona" badge

`badgeUntil` (C1 §11.3) is `filed_at + settings.badge_hours` when all hold, else null:
- `status = 'filed'`;
- `filed_by = 'mona'`;
- `now() < filed_at + badge_hours`.

`filed_by`/`filed_at` come from the `after` PathState of the entry that put the document where it is (§4.2 A.4, C.1):
- `file`, `move`, `rename` landing in the archive: that entry's actor and time;
- `undo`, `redo`: the restored state's own `filed_by`/`filed_at`, so undoing your move of a document Mona filed an hour ago brings back Mona's badge until its original 24 h run out.

So the badge expires after 24 h, and disappears at once when you move, rename or re-file the document; a later move by Mona (a rule applied through chat, D5) shows it again. Computed on read; no job.

## 7. Delete

1. **You only.** Only the REST endpoint (C2) calls `delete`, with the danger-dialog confirmation C2 specifies. There is no MCP delete tool (C4). `mona.fileops` refuses (`not_allowed`) any operation with `actor='mona'` whose target is the trash (§4.2 A.2), so Mona can't delete through `undo` of a restore or a group undo either.
2. Delete is an A–C move to `trash/<document_id>/<current basename>`, `deleted_at = now()`, `location='trash'`, status unchanged. The entry is `delete`, undoable.
3. Any open review item closes with `resolution='deleted'`.
4. Deleted documents disappear from search, lists, sums, the tree, deadlines and exports; the journal keeps them.
5. Nothing empties the trash in v1. The Visitors purge is C9's.

## 8. Names at the target

### 8.1 Collisions
The target path is taken when any file or directory exists there that is not this document. The policy is **`-2`, `-3`, … appended to the stem, before the extension**:
`2026-02-27_OPCO_Contribution-OPCO_2025-A-118.pdf` → `2026-02-27_OPCO_Contribution-OPCO_2025-A-118-2.pdf`.
- Why `-N` and not ` (N)`: C5 file names are slugs without spaces or parentheses; `-N` keeps them that way.
- The stem was capped at 116 characters (C5 §8.4) so the suffix fits.
- The atomic `link` failing with `EEXIST` is the collision test; a pre-check is only an optimisation.
- After `-999`, the operation fails with `collision_exhausted` and the document goes to review with reason `conflict`.
- Names differing only in case (`URSSAF.pdf`, `Urssaf.pdf`) are distinct on Linux and are not a collision in v1, although they clash on Windows or Drive exports.

### 8.2 Same document
If the target equals the document's current path, the operation is a no-op (§4.2).

### 8.3 Identical bytes at the target: a duplicate, not a collision
If the file at the target has the document's sha256:
- It can't be another document's file (sha256 is unique, C1 §4.2); if it is, that's a bug: raise.
- It is untracked (a person put it there). The document **adopts** it: its `current_path` becomes the target and its own copy moves to `trash/<document_id>/<basename>`. Order, inside the §4.2 A–C operation:
  1. update the pending row's `after` with `adopted: true` and `trash_copy: "<document_id>/<basename>"` (own short transaction), before touching any file;
  2. B1–B3 with `dst` = the trash copy's path (through §3 for the trash root);
  3. step C with `current_path` = the adopted target.
- §4.3 recovers an adoption entry with `dst` = `after.trash_copy` (§4.3 step 3).
- Undo moves the trash copy back to `before` and leaves the adopted file where it was, untracked again: an entry whose `before` carries `adopted: true` takes its source from `before.trash_copy` in the trash root, not from `before.path`, both in the operation and in §4.3.
- The trash copy is exempt from invariant 2 while its entry is `done` and not undone (§9).

### 8.4 Intake dedupe (for reference)
An upload or attachment whose sha256 is already a document's (in any location, trash included) creates no document: the intake item's outcome is `duplicate` and points to the existing document (C1 §4.1). No file op happens. When that document is in the trash, the outcome says so (`deleted: true` in the C2 intake DTO and in C4 §3.14's result), and the Intake row offers **Restore**, which is your undo of its `delete` entry.

## 9. Invariants

Each is a testable statement. **[M]** = the implementing lane mutation-checks it. The property tests run a random sequence of operations (ingest, file, move to a random rendered target, rename, unfile, delete, undo of a random entry, group undo, group redo) against a temporary data root, from an empty archive, checking the invariants after every step.

1. **Mirror [M].** For every document, a regular file (not a symlink) exists at `root(location)/current_path`, and its sha256 equals the document's.
2. **No strays [M].** Every file under the inbox and trash roots is some document's current file, or the `trash_copy` of a `done`, not undone adoption entry (§8.3). In the property tests (empty archive at start), the same holds for the archive: **the archive tree equals the set of DB paths** after any sequence of file/undo/redo.
3. **Unique.** No two documents share `(location, current_path)`; no two current paths are hard links to one inode after step C.
4. **Replay [M].** For each document, applying its `done` path entries in id order, starting from its first entry's `before`, ends at its current `(location, current_path)`.
5. **Round-trip [M].** `undo(e)` leaves the document at `e.before`'s path (or a §8.1 suffix of it if that path was taken meanwhile), with `e.before`'s status and classification; a following redo leaves it at `e.after`'s path.
6. **Group round-trip [M].** With no other operation in between, `undo_group(g)` leaves every file of `g` at its pre-`g` path and the archive tree identical to its state before `g`; then `undo_group(u)` restores the tree after `g`.
7. **Supersede [M].** An entry is undoable iff it is `done`, of an undoable kind, has an even undo-chain depth, and its document is at its chain tip's `after` (§5.2). Undoing a non-undoable entry leaves the DB and the filesystem byte-identical.
8. **Crash safety [M].** With a crash injected after step A, after B1, after B3, or inside C before commit, `recover_pending()` restores invariants 1–4, and the operation is either fully applied or fully absent. The same holds when another operation on the same document runs before recovery does, and for an adoption crashed after its trash move.
9. **Guard [M].** No operation creates, moves or deletes anything outside its root, including with a symlinked directory or file planted under the root, `..` in a relative path, or an absolute path.
10. **Review invariant.** C1 §4.5 holds after every operation.
11. **Badge.** `badgeUntil` is non-null iff §6's three conditions hold.
12. **Mona never deletes.** No `done` entry with `actor='mona'` has `after.location = 'trash'`, whatever the sequence of MCP calls, pipeline jobs, undos and group undos.

## 10. Test obligations

1. The property-test state machine above (hypothesis `RuleBasedStateMachine`), ≥ 500 steps per run in CI, invariants 1–7 and 10–11 after every step.
2. Crash injection for invariant 8: a hook that raises at each of the four points, then `recover_pending()`, then the invariants; one test per point, plus the five recovery-table rows of §4.3 constructed directly.
3. Guard tests for invariant 9, one per attack: symlinked parent directory, symlinked target file, symlinked source, `..`, absolute path, `\` in a segment, NUL, a parent on another device (simulated `st_dev`).
4. Collision: three documents rendering the same name get `.pdf`, `-2.pdf`, `-3.pdf`; concurrent filing of two documents to one name (two threads) ends with both files present and distinct.
5. Duplicate at target (§8.3): adoption, then undo, restores both files; invariant 2 holds after the adoption; a crash after the trash move, then recovery, completes it with `trash_copy` recorded, and a later undo restores the trash copy (not the adopted file).
6. Supersede: file → move → the `file` entry is `superseded` and its undo is refused with nothing changed; undo the move → the `file` entry is `undoable` again.
7. Group undo order: a group that moves one document twice is undone in reverse order and ends at the original path.
8. Undo of undo = redo, three levels deep. After group undo then group redo of a `rule_apply` group, the original group reads `undoable`, its entries `undoable`, the undo group `undone`; a second group undo of the original acts on the redo entries and leaves the tree as after the first undo.
9. Badge: filed by Mona → badge; after `badge_hours` (clock injected) → none; moved by you → none; that move undone → Mona's badge is back with its original `filed_at`.
10. Delete: REST delete with actor `user` works and is undoable; calling `fileops.delete` with actor `mona` raises; after a user delete and its restore, MCP `undo` of the restore (actor `mona`) is refused with `not_allowed`, alone and inside a group undo.
11. Single-filesystem startup check refuses to start when trash is on another device (simulated `st_dev`).
12. Failures: `EACCES` at B1 → entry `failed`, no file moved, the lock released; `ENOENT` at B1 once → retried and done; for pipeline filing, the document ends in review with reason `conflict` and the errno in `pipeline_error`.
13. Stale recovery: B1 fails and leaves a `pending` entry (cleanup hook disabled), the retry of the same move succeeds, then `recover_pending()` → exactly one `done` entry, the classification pointer unchanged.
14. Failed undo: an undo whose B step fails ends `failed`; a second undo of the same entry succeeds.

**Mutation checks required (report each in the lane report):** drop the supersede comparison; iterate the group ascending; skip the source unlink in recovery; skip the symlink `lstat` on parents; write the journal `done` before the filesystem step; skip recovery's still-pending/`before` re-check; drop the `actor='mona'` trash guard; compute the live state from `undone_by` alone (ignoring the chain).

## 11. Open questions

Resolved in 0.2 (adopted as proposed; each is normative in the body):
- 1: delete goes to trash and is undoable; nothing empties the trash in v1 (§7).
- 2: a path undo doesn't undo field corrections (§5.3 item 7).
- 4: file ops run inline for REST/MCP and on the `cpu` queue for pipeline filing (§4.1).
- 5: empty folders are removed after a move out, never the root (§4.2 D).
- 6: case-only collisions are ignored in v1 (§8.1).
- 3 goes to C6 (set B): whether undoing an interview's Apply also disables the rule. C7 keeps `rule.*` entries non-undoable.

No question is still open.
