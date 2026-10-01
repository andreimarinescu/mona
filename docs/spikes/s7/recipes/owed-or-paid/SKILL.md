---
name: owed-or-paid
description: 'How much we paid or owe a counterparty: amounts'
---
- **Owe:** call `search_documents` once with `counterparty` as the person wrote it. Answer with the documents that have a due date: amount, currency, due date.
- **Paid or total:** call `sum_amounts` once with `counterparty`, plus `year` if the person named one. Give the total, the number of documents, and any excluded for having no amount.
- Amounts are what the documents state; the archive doesn't record payments, so say "billed" or "due", not "paid", unless the document is a receipt.
