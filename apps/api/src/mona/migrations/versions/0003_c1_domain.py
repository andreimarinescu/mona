"""C1 domain schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ULID = "[0-9a-hjkmnp-tv-z]{26}"
TS = "timestamptz NOT NULL DEFAULT now()"


def _id(prefix: str) -> str:
    return f"id text PRIMARY KEY CHECK (id ~ '^{prefix}_{ULID}$')"


SEARCH_CONFIG = [
    "CREATE TEXT SEARCH CONFIGURATION mona (COPY = simple)",
    "ALTER TEXT SEARCH CONFIGURATION mona"
    " ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple",
]

TABLES: dict[str, str] = {
    "entities": f"""
        {_id("ent")},
        key text NOT NULL UNIQUE,
        display_name text NOT NULL,
        folder_name text NOT NULL UNIQUE,
        legal_form text NULL,
        siren text NULL CHECK (siren ~ '^[0-9]{{9}}$'),
        visibility text NOT NULL DEFAULT 'practice' CHECK (visibility IN ('practice','personal')),
        fy_end_month smallint NOT NULL DEFAULT 12 CHECK (fy_end_month BETWEEN 1 AND 12),
        fy_end_day smallint NOT NULL DEFAULT 31,
        filing_language text NULL CHECK (filing_language IN ('fr','en','ro')),
        aliases text[] NOT NULL DEFAULT '{{}}',
        addresses text[] NOT NULL DEFAULT '{{}}',
        purge_after_hours integer NULL CHECK (purge_after_hours > 0),
        sort_order integer NOT NULL DEFAULT 0,
        created_at {TS},
        updated_at {TS},
        CHECK (fy_end_day BETWEEN 1 AND CASE fy_end_month WHEN 2 THEN 28
          WHEN 4 THEN 30 WHEN 6 THEN 30 WHEN 9 THEN 30 WHEN 11 THEN 30 ELSE 31 END)
    """,
    "sub_units": f"""
        {_id("sub")},
        entity_id text NOT NULL,
        key text NOT NULL,
        label text NOT NULL,
        person_id text NULL,
        created_at {TS},
        updated_at {TS},
        UNIQUE (entity_id, key),
        UNIQUE (entity_id, label)
    """,
    "people": f"""
        {_id("per")},
        key text NOT NULL UNIQUE,
        display_name text NOT NULL,
        short_name text NULL,
        aliases text[] NOT NULL DEFAULT '{{}}',
        created_at {TS},
        updated_at {TS}
    """,
    "entity_people": """
        entity_id text,
        person_id text,
        role text NULL,
        PRIMARY KEY (entity_id, person_id)
    """,
    "accounts": f"""
        {_id("acc")},
        key text NOT NULL UNIQUE,
        entity_id text NOT NULL,
        sub_unit_id text NULL,
        bank_counterparty_id text NULL,
        label text NOT NULL,
        iban_hash text NOT NULL UNIQUE CHECK (iban_hash ~ '^[0-9a-f]{{64}}$'),
        iban_last4 text NOT NULL CHECK (iban_last4 ~ '^[0-9A-Z]{{4}}$'),
        currency text NOT NULL DEFAULT 'EUR' CHECK (currency IN ('EUR','RON')),
        created_at {TS},
        updated_at {TS}
    """,
    "counterparties": f"""
        {_id("cpt")},
        key text NOT NULL UNIQUE,
        name text NOT NULL,
        name_norm text NOT NULL UNIQUE,
        kind text NULL CHECK (kind IN ('supplier','bank','insurer','administration','social',
                                       'accountant','client','other')),
        siren text NULL CHECK (siren ~ '^[0-9]{{9}}$'),
        origin text NOT NULL CHECK (origin IN ('seed','extracted','user')),
        created_at {TS},
        updated_at {TS}
    """,
    "counterparty_aliases": """
        alias_norm text PRIMARY KEY,
        counterparty_id text NOT NULL
    """,
    "categories": f"""
        id text PRIMARY KEY,
        labels jsonb NOT NULL,
        icon text NOT NULL DEFAULT 'invoice'
          CHECK (icon IN ('bank','invoice','tax','insurance','payroll','training','travel',
                          'personal')),
        model_definition text NOT NULL,
        sort_order integer NOT NULL DEFAULT 0,
        created_at {TS},
        updated_at {TS},
        CHECK (labels ?& array['en','fr','ro'])
    """,
    "subcategories": """
        category_id text NOT NULL,
        key text NOT NULL CHECK (key ~ '^[a-z][a-z0-9_]{0,39}$'),
        labels jsonb NOT NULL CHECK (labels ?& array['en','fr','ro']),
        sort_order integer NOT NULL DEFAULT 0,
        PRIMARY KEY (category_id, key)
    """,
    "templates": f"""
        {_id("tpl")},
        category_id text NOT NULL,
        entity_id text NULL,
        path_template text NOT NULL,
        file_template text NOT NULL,
        created_at {TS},
        updated_at {TS},
        UNIQUE NULLS NOT DISTINCT (category_id, entity_id)
    """,
    "rules": f"""
        {_id("rul")},
        key text NOT NULL UNIQUE,
        name text NOT NULL,
        state text NOT NULL DEFAULT 'active' CHECK (state IN ('draft','active','disabled')),
        source text NOT NULL CHECK (source IN ('seed','interview','correction')),
        priority integer NOT NULL,
        conditions jsonb NOT NULL,
        action jsonb NOT NULL,
        condition_text jsonb NOT NULL CHECK (condition_text ?& array['en','fr','ro']),
        version integer NOT NULL DEFAULT 1,
        fired_count integer NOT NULL DEFAULT 0,
        last_fired_at timestamptz NULL,
        corrections_since integer NOT NULL DEFAULT 0,
        origin_question_id text NULL,
        origin_document_id text NULL,
        created_at {TS},
        updated_at {TS}
    """,
    "rule_versions": f"""
        rule_id text,
        version integer,
        conditions jsonb NOT NULL,
        action jsonb NOT NULL,
        condition_text jsonb NOT NULL,
        priority integer NOT NULL,
        created_at {TS},
        PRIMARY KEY (rule_id, version)
    """,
    "batches": f"""
        {_id("bat")},
        source text NOT NULL CHECK (source IN ('drop','telegram','reclassify')),
        status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','done')),
        title text NULL,
        visitor boolean NOT NULL DEFAULT false,
        started_at {TS},
        finished_at timestamptz NULL,
        debrief_interview_id text NULL,
        created_at {TS}
    """,
    "intake_items": f"""
        {_id("itm")},
        batch_id text NOT NULL,
        original_name text NOT NULL,
        sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
        size_bytes bigint NOT NULL,
        outcome text NOT NULL CHECK (outcome IN ('accepted','duplicate','rejected')),
        document_id text NULL,
        reject_reason text NULL
          CHECK (reject_reason IN ('unsupported_type','too_large','empty','unreadable_file')),
        created_at {TS}
    """,
    "documents": f"""
        {_id("doc")},
        sha256 text NOT NULL UNIQUE CHECK (sha256 ~ '^[0-9a-f]{{64}}$'),
        original_name text NOT NULL,
        mime_type text NOT NULL CHECK (mime_type IN ('application/pdf','image/jpeg','image/png')),
        size_bytes bigint NOT NULL,
        page_count integer NULL,
        source text NOT NULL CHECK (source IN ('drop','telegram')),
        batch_id text NOT NULL,
        arrived_at {TS},
        location text NOT NULL CHECK (location IN ('inbox','archive','trash')),
        current_path text NOT NULL,
        status text NOT NULL CHECK (status IN ('processing','filed','review','unreadable')),
        pipeline_stage text NOT NULL DEFAULT 'queued'
          CHECK (pipeline_stage IN ('queued','reading','ocr','classifying','filing','done',
                                    'failed')),
        pipeline_error text NULL,
        reasons text[] NOT NULL DEFAULT '{{}}'
          CHECK (reasons <@ array['low','entity','conflict','unreadable']),
        title text NULL,
        entity_id text NULL,
        sub_unit_id text NULL,
        category_id text NULL,
        subcategory_key text NULL,
        counterparty_id text NULL,
        issuer text NULL,
        reference text NULL,
        doc_type text NULL,
        doc_date date NULL,
        period_start date NULL,
        period_end date NULL,
        fiscal_year integer NULL,
        amount numeric(14,2) NULL,
        currency text NULL CHECK (currency IN ('EUR','RON')),
        due_date date NULL,
        addressee text NULL,
        addressee_person_id text NULL,
        confidence smallint NULL CHECK (confidence BETWEEN 0 AND 100),
        band text NULL CHECK (band IN ('high','medium','low')),
        extraction_id text NULL,
        classification_id text NULL,
        rule_id text NULL,
        filed_at timestamptz NULL,
        filed_by text NULL CHECK (filed_by IN ('mona','user')),
        filed_op_id bigint NULL,
        deleted_at timestamptz NULL,
        head_norm text NULL,
        fts tsvector NULL,
        created_at {TS},
        updated_at {TS},
        CHECK ((amount IS NULL) = (currency IS NULL)),
        CHECK ((location = 'trash') = (deleted_at IS NOT NULL)),
        CHECK (status <> 'filed' OR location IN ('archive','trash')),
        CHECK (status <> 'unreadable' OR 'unreadable' = ANY (reasons)),
        UNIQUE (location, current_path)
    """,
    "extractions": f"""
        {_id("ext")},
        document_id text NOT NULL,
        version integer NOT NULL,
        text_method text NOT NULL CHECK (text_method IN ('pdftotext','ocr','none')),
        text_cache_key text NOT NULL,
        char_count integer NOT NULL,
        model text NULL,
        prompt_version text NULL,
        raw_output jsonb NULL,
        from_cache boolean NOT NULL DEFAULT false,
        duration_ms integer NULL,
        prompt_tokens integer NULL,
        completion_tokens integer NULL,
        created_at {TS},
        UNIQUE (document_id, version)
    """,
    "extraction_fields": """
        extraction_id text,
        key text CHECK (key IN ('entity','counterparty','issuer','reference','doc_type','doc_date',
                                'period_start','period_end','amount','due_date','addressee')),
        value text NOT NULL,
        currency text NULL CHECK (currency ~ '^[A-Z]{3}$'),
        quote text NOT NULL,
        page integer NOT NULL CHECK (page >= 1),
        stated_page integer NOT NULL,
        verified boolean NOT NULL,
        find_query text NULL,
        confidence smallint NOT NULL CHECK (confidence BETWEEN 0 AND 100),
        PRIMARY KEY (extraction_id, key)
    """,
    "classifications": f"""
        {_id("cls")},
        document_id text NOT NULL,
        extraction_id text NULL,
        method text NOT NULL CHECK (method IN ('llm','rule','user')),
        rule_id text NULL,
        conflicting_rule_ids text[] NOT NULL DEFAULT '{{}}',
        entity_id text NULL,
        sub_unit_id text NULL,
        category_id text NULL,
        subcategory_key text NULL,
        counterparty_id text NULL,
        model_confidence smallint NULL,
        confidence smallint NOT NULL CHECK (confidence BETWEEN 0 AND 100),
        band text NOT NULL CHECK (band IN ('high','medium','low')),
        reasons text[] NOT NULL DEFAULT '{{}}'
          CHECK (reasons <@ array['low','entity','conflict','unreadable']),
        proposed_path text NULL,
        proposed_file_name text NULL,
        created_at {TS}
    """,
    "review_items": f"""
        {_id("rev")},
        document_id text NOT NULL,
        reasons text[] NOT NULL CHECK (cardinality(reasons) > 0),
        status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','resolved','dismissed')),
        resolution text NULL
          CHECK (resolution IN ('confirmed','corrected','rule_applied','deleted','refiled')),
        scope text NULL CHECK (scope IN ('one','all')),
        rule_id text NULL,
        resolved_by text NULL CHECK (resolved_by IN ('mona','user')),
        created_at {TS},
        resolved_at timestamptz NULL
    """,
    "op_groups": f"""
        {_id("grp")},
        kind text NOT NULL
          CHECK (kind IN ('intake_batch','rule_apply','correction','undo','redo','refile')),
        actor text NOT NULL CHECK (actor IN ('mona','user')),
        via text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
        batch_id text NULL,
        rule_id text NULL,
        target_group_id text NULL,
        created_at {TS}
    """,
    "file_ops": """
        id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        at timestamptz NOT NULL DEFAULT now(),
        actor text NOT NULL CHECK (actor IN ('mona','user')),
        via text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
        action text NOT NULL CHECK (action IN (
          'file','move','rename','unfile','delete','undo','redo',
          'doc.update','rule.create','rule.change','deadline.add','reminder.add',
          'mark.unreadable')),
        document_id text NULL,
        subject_id text NULL,
        sha256 text NULL,
        before jsonb NULL,
        after jsonb NULL,
        fs_state text NOT NULL DEFAULT 'done' CHECK (fs_state IN ('pending','done','failed')),
        batch_id text NULL,
        group_id text NULL,
        rule_id text NULL,
        confidence smallint NULL,
        band text NULL CHECK (band IN ('high','medium','low')),
        undoable boolean NOT NULL,
        undone_by bigint NULL UNIQUE,
        undo_of bigint NULL,
        CHECK ((action IN ('undo','redo')) = (undo_of IS NOT NULL))
    """,
    "interviews": f"""
        {_id("int")},
        kind text NOT NULL CHECK (kind IN ('seed','debrief','on_demand')),
        status text NOT NULL DEFAULT 'generating'
          CHECK (status IN ('generating','ready','done','failed','cancelled')),
        scope jsonb NOT NULL,
        lang text NOT NULL CHECK (lang IN ('en','fr','ro')),
        batch_id text NULL,
        conversation_id text NULL,
        analysis text NULL,
        error text NULL,
        created_at {TS},
        ready_at timestamptz NULL,
        finished_at timestamptz NULL
    """,
    "interview_questions": f"""
        {_id("qst")},
        interview_id text NOT NULL,
        ordinal smallint NOT NULL CHECK (ordinal BETWEEN 1 AND 7),
        text text NOT NULL,
        impact integer NOT NULL,
        affected_document_ids text[] NOT NULL,
        evidence jsonb NOT NULL,
        options jsonb NOT NULL,
        suggestion_confidence smallint NOT NULL,
        status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','answered','skipped')),
        created_at {TS},
        UNIQUE (interview_id, ordinal)
    """,
    "interview_answers": f"""
        {_id("ans")},
        question_id text NOT NULL UNIQUE,
        option_id text NULL,
        free_text text NULL,
        actor text NOT NULL CHECK (actor IN ('mona','user')),
        via text NOT NULL CHECK (via IN ('ui','chat','telegram','pipeline')),
        created_at {TS},
        CHECK (option_id IS NOT NULL OR free_text IS NOT NULL)
    """,
    "deadlines": f"""
        {_id("ddl")},
        document_id text NULL,
        entity_id text NOT NULL,
        label text NOT NULL,
        due_date date NOT NULL,
        amount numeric(14,2) NULL,
        currency text NULL CHECK (currency IN ('EUR','RON')),
        paid_by_account_id text NULL,
        status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','done','dismissed')),
        origin text NOT NULL CHECK (origin IN ('extracted','mona','user')),
        created_at {TS},
        updated_at {TS},
        CHECK ((amount IS NULL) = (currency IS NULL))
    """,
    "reminders": f"""
        {_id("rem")},
        deadline_id text NULL,
        document_id text NULL,
        remind_on date NOT NULL,
        note text NULL,
        status text NOT NULL DEFAULT 'scheduled'
          CHECK (status IN ('scheduled','delivered','cancelled')),
        created_by text NOT NULL CHECK (created_by IN ('mona','user')),
        created_at {TS},
        delivered_at timestamptz NULL,
        CHECK (deadline_id IS NOT NULL OR document_id IS NOT NULL)
    """,
    "drafts": f"""
        {_id("drf")},
        document_id text NOT NULL,
        lang text NOT NULL CHECK (lang IN ('en','fr','ro')),
        instructions text NULL,
        status text NOT NULL DEFAULT 'generating' CHECK (status IN ('generating','ready','failed')),
        title text NULL,
        body text NULL,
        error text NULL,
        created_at {TS},
        updated_at {TS}
    """,
    "exports": f"""
        {_id("exp")},
        entity_id text NOT NULL,
        fiscal_year integer NOT NULL,
        status text NOT NULL DEFAULT 'building' CHECK (status IN ('building','ready','failed')),
        document_count integer NULL,
        zip_path text NULL,
        csv_path text NULL,
        error text NULL,
        created_at {TS},
        updated_at {TS}
    """,
    "conversations": f"""
        {_id("cnv")},
        title text NOT NULL,
        created_at {TS},
        updated_at {TS},
        last_message_at {TS}
    """,
    "chat_turns": f"""
        {_id("trn")},
        conversation_id text NOT NULL,
        status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','closed','failed','aborted')),
        user_text text NOT NULL,
        ui_message_id text NOT NULL,
        reply_language text NOT NULL CHECK (reply_language IN ('en','fr','ro')),
        opened_at {TS},
        lease_expires_at timestamptz NOT NULL,
        closed_at timestamptz NULL,
        reasoning_ms integer NULL,
        finish_reason text NULL,
        error_code text NULL,
        usage jsonb NULL,
        parts jsonb NOT NULL DEFAULT '[]'
    """,
    "card_events": f"""
        {_id("crd")},
        tool text NOT NULL,
        kind text NOT NULL
          CHECK (kind IN ('doc','deadline','interview','rulePreview','draft','export')),
        subject jsonb NOT NULL,
        channel text NOT NULL CHECK (channel IN ('web','telegram')),
        turn_id text NULL,
        emitted_at timestamptz NULL,
        created_at {TS}
    """,
    "card_action_notes": f"""
        {_id("not")},
        conversation_id text NOT NULL,
        kind text NOT NULL,
        text text NOT NULL CHECK (length(text) <= 300),
        created_at {TS},
        consumed_turn_id text NULL
    """,
    "profile": f"""
        singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
        name text NOT NULL,
        password_hash text NOT NULL,
        locale text NOT NULL DEFAULT 'en' CHECK (locale IN ('en','fr','ro')),
        auto_lock_minutes integer NOT NULL DEFAULT 15 CHECK (auto_lock_minutes BETWEEN 1 AND 1440),
        locked_at timestamptz NULL,
        password_changed_at {TS},
        created_at {TS},
        updated_at {TS}
    """,
    "settings": f"""
        singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
        practice_name text NOT NULL,
        filing_language text NOT NULL DEFAULT 'fr' CHECK (filing_language IN ('fr','en','ro')),
        confidence_high smallint NOT NULL DEFAULT 85,
        confidence_low smallint NOT NULL DEFAULT 60,
        badge_hours smallint NOT NULL DEFAULT 24 CHECK (badge_hours BETWEEN 1 AND 168),
        debrief_queue_threshold smallint NOT NULL DEFAULT 5,
        iban_salt bytea NOT NULL,
        created_at {TS},
        updated_at {TS},
        CHECK (0 < confidence_low AND confidence_low < confidence_high AND confidence_high <= 100)
    """,
}

# Added after every table exists: several references are circular (documents <-> extractions).
FOREIGN_KEYS = [
    "sub_units (entity_id) REFERENCES entities ON DELETE RESTRICT",
    "sub_units (person_id) REFERENCES people ON DELETE SET NULL",
    "entity_people (entity_id) REFERENCES entities ON DELETE CASCADE",
    "entity_people (person_id) REFERENCES people ON DELETE CASCADE",
    "accounts (entity_id) REFERENCES entities ON DELETE RESTRICT",
    "accounts (sub_unit_id) REFERENCES sub_units ON DELETE SET NULL",
    "accounts (bank_counterparty_id) REFERENCES counterparties ON DELETE SET NULL",
    "counterparty_aliases (counterparty_id) REFERENCES counterparties ON DELETE CASCADE",
    "subcategories (category_id) REFERENCES categories ON DELETE CASCADE",
    "templates (category_id) REFERENCES categories ON DELETE CASCADE",
    "templates (entity_id) REFERENCES entities ON DELETE CASCADE",
    "rules (origin_question_id) REFERENCES interview_questions ON DELETE SET NULL",
    "rules (origin_document_id) REFERENCES documents ON DELETE SET NULL",
    "rule_versions (rule_id) REFERENCES rules ON DELETE CASCADE",
    "batches (debrief_interview_id) REFERENCES interviews ON DELETE SET NULL",
    "intake_items (batch_id) REFERENCES batches ON DELETE CASCADE",
    "intake_items (document_id) REFERENCES documents ON DELETE SET NULL",
    "documents (batch_id) REFERENCES batches ON DELETE RESTRICT",
    "documents (entity_id) REFERENCES entities ON DELETE RESTRICT",
    "documents (sub_unit_id) REFERENCES sub_units ON DELETE SET NULL",
    "documents (category_id) REFERENCES categories ON DELETE RESTRICT",
    "documents (counterparty_id) REFERENCES counterparties ON DELETE SET NULL",
    "documents (addressee_person_id) REFERENCES people ON DELETE SET NULL",
    "documents (extraction_id) REFERENCES extractions ON DELETE SET NULL",
    "documents (classification_id) REFERENCES classifications ON DELETE SET NULL",
    "documents (rule_id) REFERENCES rules ON DELETE SET NULL",
    "documents (filed_op_id) REFERENCES file_ops",
    "documents (category_id, subcategory_key) REFERENCES subcategories (category_id, key)"
    " ON DELETE SET NULL (subcategory_key)",
    "extractions (document_id) REFERENCES documents ON DELETE CASCADE",
    "extraction_fields (extraction_id) REFERENCES extractions ON DELETE CASCADE",
    "classifications (document_id) REFERENCES documents ON DELETE CASCADE",
    "classifications (extraction_id) REFERENCES extractions ON DELETE SET NULL",
    "classifications (rule_id) REFERENCES rules ON DELETE SET NULL",
    "classifications (entity_id) REFERENCES entities",
    "classifications (sub_unit_id) REFERENCES sub_units",
    "classifications (category_id) REFERENCES categories",
    "classifications (counterparty_id) REFERENCES counterparties",
    "review_items (document_id) REFERENCES documents ON DELETE CASCADE",
    "review_items (rule_id) REFERENCES rules ON DELETE SET NULL",
    "op_groups (batch_id) REFERENCES batches ON DELETE SET NULL",
    "op_groups (rule_id) REFERENCES rules ON DELETE SET NULL",
    "op_groups (target_group_id) REFERENCES op_groups",
    "file_ops (document_id) REFERENCES documents ON DELETE RESTRICT",
    "file_ops (batch_id) REFERENCES batches ON DELETE SET NULL",
    "file_ops (group_id) REFERENCES op_groups ON DELETE SET NULL",
    "file_ops (rule_id) REFERENCES rules ON DELETE SET NULL",
    "file_ops (undone_by) REFERENCES file_ops",
    "file_ops (undo_of) REFERENCES file_ops",
    "interviews (batch_id) REFERENCES batches ON DELETE SET NULL",
    "interviews (conversation_id) REFERENCES conversations ON DELETE SET NULL",
    "interview_questions (interview_id) REFERENCES interviews ON DELETE CASCADE",
    "interview_answers (question_id) REFERENCES interview_questions ON DELETE CASCADE",
    "deadlines (document_id) REFERENCES documents ON DELETE SET NULL",
    "deadlines (entity_id) REFERENCES entities ON DELETE RESTRICT",
    "deadlines (paid_by_account_id) REFERENCES accounts ON DELETE SET NULL",
    "reminders (deadline_id) REFERENCES deadlines ON DELETE CASCADE",
    "reminders (document_id) REFERENCES documents ON DELETE CASCADE",
    "drafts (document_id) REFERENCES documents ON DELETE CASCADE",
    "exports (entity_id) REFERENCES entities ON DELETE RESTRICT",
    "chat_turns (conversation_id) REFERENCES conversations ON DELETE CASCADE",
    "card_events (turn_id) REFERENCES chat_turns ON DELETE SET NULL",
    "card_action_notes (conversation_id) REFERENCES conversations ON DELETE CASCADE",
    "card_action_notes (consumed_turn_id) REFERENCES chat_turns ON DELETE SET NULL",
]

INDEXES = [
    "CREATE UNIQUE INDEX entities_one_visitors ON entities ((true))"
    " WHERE purge_after_hours IS NOT NULL",
    "CREATE INDEX counterparties_name_trgm ON counterparties USING gin (name_norm gin_trgm_ops)",
    "CREATE INDEX rules_active ON rules (priority DESC) WHERE state = 'active'",
    "CREATE INDEX documents_fts ON documents USING gin (fts)",
    "CREATE INDEX documents_head ON documents USING gin (head_norm gin_trgm_ops)",
    "CREATE INDEX documents_facets ON documents (entity_id, category_id, fiscal_year)"
    " WHERE deleted_at IS NULL",
    "CREATE INDEX documents_status ON documents (status, arrived_at DESC) WHERE deleted_at IS NULL",
    "CREATE INDEX documents_cpt ON documents (counterparty_id) WHERE deleted_at IS NULL",
    "CREATE INDEX documents_doc_date ON documents (doc_date) WHERE deleted_at IS NULL",
    "CREATE INDEX classifications_doc ON classifications (document_id, created_at DESC)",
    "CREATE UNIQUE INDEX review_items_one_open ON review_items (document_id) WHERE status = 'open'",
    "CREATE UNIQUE INDEX op_groups_intake ON op_groups (batch_id) WHERE kind = 'intake_batch'",
    "CREATE INDEX file_ops_doc ON file_ops (document_id, id DESC)",
    "CREATE INDEX file_ops_group ON file_ops (group_id, id DESC)",
    "CREATE INDEX file_ops_pending ON file_ops (id) WHERE fs_state = 'pending'",
    "CREATE UNIQUE INDEX file_ops_undo_of_live ON file_ops (undo_of) WHERE fs_state <> 'failed'",
    "CREATE UNIQUE INDEX deadlines_doc_date ON deadlines (document_id, due_date)"
    " WHERE document_id IS NOT NULL",
    "CREATE UNIQUE INDEX reminders_once ON reminders"
    " (coalesce(deadline_id, document_id), remind_on) WHERE status = 'scheduled'",
    "CREATE UNIQUE INDEX chat_turns_one_open ON chat_turns (conversation_id) WHERE status = 'open'",
    "CREATE INDEX chat_turns_conv ON chat_turns (conversation_id, opened_at)",
    "CREATE INDEX card_events_turn ON card_events (turn_id, created_at)",
    "CREATE INDEX card_action_notes_pending ON card_action_notes (conversation_id, created_at)"
    " WHERE consumed_turn_id IS NULL",
]


def upgrade() -> None:
    for stmt in SEARCH_CONFIG:
        op.execute(stmt)
    for name, body in TABLES.items():
        op.execute(f"CREATE TABLE {name} ({body})")
    for fk in FOREIGN_KEYS:
        table, rest = fk.split(" ", 1)
        op.execute(f"ALTER TABLE {table} ADD FOREIGN KEY {rest}")
    for stmt in INDEXES:
        op.execute(stmt)


def downgrade() -> None:
    op.execute(f"DROP TABLE {', '.join(reversed(TABLES))} CASCADE")
    op.execute("DROP TEXT SEARCH CONFIGURATION mona")
