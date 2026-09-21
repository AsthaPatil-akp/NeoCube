# Commerce comparison

## Currency policy B (no invented exchange rates)

NeoCube does **not** convert between currencies. There is no configured
exchange-rate source, so amounts in different currencies are never treated as
equal.

Rules used by the matching hard filter:

1. If client and supplier currencies are both present and **equal**, compare
   amounts after applying budget/price basis (`TOTAL` vs `PER_UNIT`).
2. If both currencies are **omitted** (legacy rows), compare the numeric
   amounts only. Status: `LEGACY_UNSPECIFIED`.
3. If the currencies are both present and **different**, the pair is not
   eligible. Status: `CURRENCY_COMPARISON_UNAVAILABLE`.
4. Missing currency is stored as unknown. The extractor never defaults to INR.

## Basis

- Client `budget_basis`: `TOTAL` or `PER_UNIT`. Unspecified client budget is
  treated as `TOTAL` because that is the historical meaning of the budget
  column.
- Supplier `price_basis`: `TOTAL` or `PER_UNIT`. If still unknown after parsing
  pricing text, the budget check is skipped rather than guessing.

Example: quantity 80, client 960000 INR TOTAL, supplier 11200 INR PER_UNIT
produces required cost `80 × 11200 = 896000`, which is within budget.
