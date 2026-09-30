# Contract amendments

Changes to frozen contracts C1–C9, numbered A1, A2, … in the order they're made. An amendment wins over the contract text it amends until the contract document is updated; a brief never wins over either.

Each entry: number, date, contract and section, the change, the reason, and the lanes it affects.

Set A (C1, C3 shape, C4, C5, C7) froze at v1.0 on 2026-09-30. Set B (C2, C6, C8, C9) froze at v1.0 on 2026-10-01.

## A1 · 2026-09-30 · C1 §8 `settings.iban_salt`: created by the seed loader

- **Change:** C1 says the migration generates `settings.iban_salt`. But the settings row can't exist before the profile's `practice_name` is known, so the **seed loader** creates it on first load. The value is `MONA_IBAN_PEPPER` when that is set, else 32 random bytes. The hash formula is unchanged.
- **Why:** F0 found the migration wording unbuildable (NOT NULL `practice_name`).
- **Lanes:** F0 (done), L1, L2 (read the salt from settings, never from env), L5c (`demo-reset` keeps the settings row).

## A2 · 2026-09-30 · C4 §3.8/§3.9, C5 §4.6.9: Visitors documents are never rule candidates

- **Change:** documents from a visitor batch are excluded from `preview_rule` / `apply_rule` candidates and from rule application in the pipeline.
- **Why:** as written, applying a rule could move a Visitors document into a practice entity. That breaks C1 §2.1's Visitors invariant and takes the document out of the 24 h purge (W1-B P1).
- **Lanes:** L1 (candidates), L2 (tools).

## A3 · 2026-09-30 · C4 §3.7: an "ask me each time" answer

- **Change:** `answer_question` with an `ask` option returns `rules: [{id, state: "active"}]` (the `review: true` rule, C1 §11.5) with `previews: []` and no card.
- **Why:** it makes explicit what C6 §6.2 records (W1-B P3).
- **Lanes:** L2, L4.

## A4 · 2026-09-30 · C4 §3.9: the activating rule change joins the apply group

- **Change:** when `apply_rule` creates a group, the rule's activating `rule.change` journal entry carries that `group_id`.
- **Why:** undoing a whole Apply group must revert the rule to draft (C6 §7.3) (W1-B P4).
- **Lanes:** L1, L2.

## A5 · 2026-09-30 · C1 §1.2: id prefix `ses`

- **Change:** add `ses` → `auth_sessions` to the prefix table (C2 §2.2 owns the table). Editorial (W1-B P5).
- **Lanes:** L2.

## A6 · 2026-09-30 · C5 §3/§5.2: Romanian titles use comma-below

- **Change:** generated titles stored for a practice filing in Romanian pass through `ro_comma_below` (C8 §7 rule 2). No effect on the demo (FR filing) (W1-B P6).
- **Lanes:** L1.

## A8 · 2026-10-01 · C1 §4.1 batch-done check: `FOR NO KEY UPDATE`

- **Change:** the batch-done check locks the batch row with `SELECT … FOR NO KEY UPDATE`, not `FOR UPDATE`.
- **Why:** L1-M1 reproduced a deadlock between two concurrent filings under `FOR UPDATE`. The file-op transactions touch rows referencing the batch, and their FK `KEY SHARE` locks conflict with `FOR UPDATE`. `FOR NO KEY UPDATE` still serialises the check, and a race test fails without the lock.
- **Lanes:** L1 (done), L1-M2.

## A7 · 2026-10-01 · C5 §4.7: Romanian and French `condition_text` wording, amounts

- **Change:** the Romanian column of C5 §4.7 takes C8 §8's reviewed phrases (gender agreement with "lui"/"îl … pe", the missing genitive nouns, fewer calques), with Romanian closing quotes `”` (U+201D) and French U+00A0 inside « ».
- **Amounts:** `{money}`, `{a}` and `{b}` are the number part of `format_money` (C8 §6.4): two decimals, no currency, and each language's own marks. EN groups with `,` and uses `.` for decimals (`1,284.60`); FR groups with U+00A0 and uses `,` (`1 284,60`); RO groups with `.` and uses `,` (`1.284,60`).
- **Test:** C5 §11 test 16 gains one amount row per language.
- **Why:** W1-B P2 and gate G19. F0's `mona/rules/text.py` groups French with a plain space.
- **Lanes:** L1.

## A9 · 2026-10-01 · C1 §8 `settings`: the early-debrief setting

- **Change:** replace the `debrief_queue_threshold` line with:
  ```
  debrief_queue_threshold smallint NOT NULL DEFAULT 5,    -- C6 §3.3: uncovered candidates of done batches that start a queue debrief
  debrief_early_min  smallint NOT NULL DEFAULT 5 CHECK (debrief_early_min BETWEEN 1 AND 50),   -- C6 §3.2: candidates that start a running batch's debrief early
  ```
- **Why:** the orchestrator's early-debrief ruling (set B G9, G31, G37). The stage snapshot sets 7 (C9 §6.7).
- **Lanes:**
  - L2: the migration, `SettingsView.debriefEarlyMin`, and the seed loader's `practice.debrief_early_min`;
  - L4: the trigger;
  - L5c: the stage value.

## A10 · 2026-10-01 · C1 §6.2: no extracted deadline for a visitor document

- **Change:** append to the bullet that begins "A filed document with a verified `due_date` gets an `extracted` deadline": *A document of a visitor batch (`batches.visitor`, §4.1) never gets one: a visitor's bill is not the practice's obligation (C9 §5.5).*
- **Why:** set B G53.
- **Lanes:** L1 (the filing transaction).

## A11 · 2026-10-01 · C3 §2: the banner's page summary

- **Change:** `summary: "Intake, batch bat_… {state}, N questions"`, where `{state}` is `running` while the batch runs, else `finished`.
- **Why:** set B G9. An early debrief can be ready while the batch still runs.
- **Lanes:** L3.

## A12 · 2026-10-01 · C4 §3.3 `sum_amounts`: titles in the result

- **Change:** each summed document in the result carries its `title` (for up to 10 documents; beyond that, ids only with `"truncated": true`), within the §2.3 cap.
- **Why:** L2-P1's live runs showed the model following a sum with two `get_document` calls just to name the documents, against the ≤2-calls budget (C4 §2.9).
- **Lanes:** L2.

## A13 · 2026-10-01 · C4 §4.2 and C7 §1: two narrower attachment mounts

- **Change:** instead of the whole `/opt/data/cache`, the api mounts only `cache/documents` and `cache/images`, read-only, as two volume subpaths at the same absolute paths. `ATTACH_ROOT` and the guard are unchanged.
- **Why:** the single mount also exposed Hermes' own cache files to the api (L2-P1).
- **Lanes:** L2.
