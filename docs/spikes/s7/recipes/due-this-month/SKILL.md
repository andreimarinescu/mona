---
name: due-this-month
description: 'What is due this month or soon: upcoming deadlines'
---
1. Call `list_deadlines` once: `within_days` = the days from today to the last day of this month, `include_overdue: true`.
2. Answer from that result only: each deadline with its amount, currency, due date and entity, overdue ones first. Leave out anything due after this month.
3. Offer a reminder in one line; call `schedule_reminder` only if the person agrees.
