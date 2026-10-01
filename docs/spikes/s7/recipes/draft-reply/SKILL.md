---
name: draft-reply
description: 'Draft a reply or letter answering a document'
---
1. Call `search_documents` once with `counterparty` (and `query` with one word of the letter's subject if the person gave one), `limit: 3`.
2. Call `draft_reply` straight away with the top result's `document_id`, `lang` = the person's language, `instructions` = what the person wants, in one sentence. Don't call `get_document` or `list_deadlines` first: the draft reads the letter itself.
3. Say in one line that the draft is being written and appears as a card; nothing is sent.
