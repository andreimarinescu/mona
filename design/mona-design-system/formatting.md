# Formatting

Every project formats numbers, money, dates and times through `Mona.format`, so EN, FR and RO read the same everywhere. The functions wrap `Intl`, with a few house rules on top: French no-break spaces are the regular U+00A0 (the brand fonts lack the narrow U+202F), euros in French and Romanian go after the number with a no-break space, and lei is always written *lei*, never RON.

| Call | EN | FR | RO |
|---|---|---|---|
| `format.money(1284.6, 'EUR', lang)` | €1,284.60 | 1 284,60 € | 1.284,60 € |
| `format.money(4812, 'RON', lang)` | 4,812.00 lei | 4 812,00 lei | 4.812,00 lei |
| `format.percent(0.62, lang)` | 62% | 62 % | 62% |
| `format.number(1284, lang)` | 1,284 | 1 284 | 1.284 |
| `format.date(d, lang)` (long) | 14 March 2026 | 14 mars 2026 | 14 martie 2026 |
| `format.date(d, lang, 'medium')` | 14 Mar 2026 | 14 mars 2026 | 14 mar. 2026 |
| `format.date(d, lang, 'short')` | 14/03/2026 | 14/03/2026 | 14.03.2026 |
| `format.time(d, lang)` | 14:02 | 14:02 | 14:02 |
| `format.relative(d, lang)` | 2 minutes ago · yesterday | il y a 2 minutes · hier | acum 2 minute · ieri |
| `format.fileSize(234567, lang)` | 229.1 KB | 229,1 Ko | 229,1 KB |

- Pass the page language (`en`, `fr`, `ro`); English uses UK conventions.
- `relative` switches to a medium date after six days. Journals show the exact time in a tooltip.
- Put amounts and dates in columns with tabular figures (`mona-num`, or `numeric` on `Table` and `DescriptionList` cells).
- Components that show numbers (`ConfidenceMeter`, `Pagination`, `Textarea` counts, `FileInput` sizes, `Progress`) already format through this module.
- Interface strings the components carry are in `Mona.i18n.UI`, keyed by language. Add a language there and every component picks it up.
