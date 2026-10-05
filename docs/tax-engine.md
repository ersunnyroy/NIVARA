# Tax and charges engine

Answers "how much will I actually make" for Indian listed equity: gross P&L → charges → P&L before tax →
estimated income tax → net. Every figure is an **estimate** (`label: "ESTIMATED"`).

> Estimated tax only. Verify with a qualified tax professional before filing.
> This does not replace a chartered accountant or tax-filing software.

## Code map

| Module | Responsibility |
|---|---|
| `app/tax/charges.py` | Brokerage and statutory charges per order from dated charge schedules |
| `app/portfolio/lots.py` | FIFO tax lots, split/bonus adjustments, matching sells to lots, charge allocation |
| `app/tax/rules.py` | Dated tax rules (`TaxRuleSpec`) and `RuleBook` look-ups |
| `app/tax/engine.py` | STCG/LTCG/SPEC classification, per-match capital gain, tax-year computation, unrealized estimate, net P&L |
| `app/tax/harvesting.py` | Informational tax-loss harvesting view |
| `app/tax/defaults.py` | Seed data: default tax rules, charge schedules, basic exemption limits, regime surcharge caps |
| `app/services/portfolio_service.py` | Wires the pure engines to the database (`tax_rules`, `charges`, `tax_profiles`, `transactions`) |

All engines are pure functions over `Decimal`. Money is rounded to paise (`ROUND_HALF_UP`) only at the reporting
edge. Charge rates are stored as percent values (`0.1` = 0.1%); tax rates as fractions (`0.125` = 12.5%).
Tax years are written `2026-27` (1 April – 31 March).

## Dated tax rules

Rules are rows in `tax_rules`, keyed by **date of transfer** (`effective_from ≤ sold date ≤ effective_to`), grouped
by `rule_set_version`. The engine uses the highest (lexically sorted) rule-set version present among active rows
(`is_active = true`); if no rows exist it falls back to the built-in defaults. The seeded set is
`IN-2026.10` (`app/tax/defaults.py`, source `https://www.incometaxindia.gov.in/en/sale-of-shares`):

| Asset type | Term | Transfers | Rate | LTCG exemption / year | Legal reference |
|---|---|---|---|---|---|
| `listed_equity_stt_paid` | STCG | 2018-04-01 – 2024-07-22 | 15% | — | s.111A, Income-tax Act, 1961 |
| `listed_equity_stt_paid` | STCG | 2024-07-23 – 2026-03-31 | 20% | — | s.111A (as amended by Finance (No.2) Act, 2024) |
| `listed_equity_stt_paid` | STCG | from 2026-04-01 | 20% | — | s.196, Income-tax Act, 2025 |
| `listed_equity_stt_paid` | LTCG | 2018-04-01 – 2024-07-22 | 10% | ₹1,00,000 | s.112A, Income-tax Act, 1961 |
| `listed_equity_stt_paid` | LTCG | 2024-07-23 – 2026-03-31 | 12.5% | ₹1,25,000 | s.112A (as amended by Finance (No.2) Act, 2024) |
| `listed_equity_stt_paid` | LTCG | from 2026-04-01 | 12.5% | ₹1,25,000 | s.198, Income-tax Act, 2025 |
| `intraday_equity` | SPEC | from 2018-04-01 | user's slab rate | — | Speculative business income (s.43(5)/s.73, Income-tax Act, 1961; corresponding provisions of the 2025 Act) |

All listed-equity rules: holding period 12 months, cess 4%, surcharge cap 15%, grandfathering date 31-Jan-2018 on
LTCG rules. The intraday rule has no surcharge cap of its own (the regime cap applies).

### Holding period boundary

`classify()` returns LTCG only when the sale date is **after** acquisition date + 12 calendar months
(`add_months`, day clamped to month end). Holding exactly 12 months is STCG. Example: bought 2025-05-02 →
sold 2026-05-02 is STCG; sold 2026-05-03 is LTCG. Intraday (`segment = intraday`) is always SPEC.

### FY 2024-25 split rates

Gains are bucketed by (term, rate), so a year can contain STCG at 15% and 20%, and LTCG at 10% and 12.5%.
The LTCG exemption is taken from the LTCG rule effective on the **last day** of the tax year, so FY 2024-25 uses
₹1,25,000 for the whole year (`RuleBook.exemption_for_tax_year`).

## Capital gain per FIFO match

`capital_gain_for_match()`:

- **Capital gain** = (sale value − transfer expenses excluding STT) − (cost + acquisition expenses excluding STT).
  STT is not deductible for capital gains.
- **Trading P&L** = sale value − purchase value − all buy and sell charges (including STT and DP).
- **SPEC (intraday)**: gain = trading P&L (all charges, including STT, deducted; s.36(1)(xv)).
- **Grandfathering** (LTCG, acquired on/before 31-Jan-2018): cost = max(actual cost, min(FMV on 31-Jan-2018 ×
  quantity, sale value)). The per-share FMV is entered as `fmv_31jan2018` on the buy transaction
  (`POST /api/portfolios/{pid}/transactions`), stored on the transaction and carried into the FIFO lot (adjusted for
  later splits). Without an FMV the gain is computed on actual cost and the estimate is flagged incomplete.
- **Bonus lots**: nil cost, holding period from the ex-date (proxy for allotment).
- A listed-equity line with no STT recorded is flagged ("concessional rates assume STT was paid").
- A sale with no matching rule becomes `UNCLASSIFIED` and makes the estimate incomplete.

## Tax-year computation

`compute_tax_year(lines, tax_year, profile, rulebook)` applies, in order (each step is written to `set_off_log`):

1. Current-year STCL against STCG.
2. Current-year LTCL against LTCG (LTCL can only offset LTCG).
3. Remaining current-year STCL against LTCG.
4. Brought-forward STCL against STCG, brought-forward LTCL against LTCG, remaining brought-forward STCL against
   LTCG.
5. LTCG exemption — once per tax year per asset type.
6. Basic-exemption-limit shortfall against STCG/LTCG — **residents only**: shortfall = limit − other income −
   speculative income. Limits: new regime ₹3,00,000 (FY 2024-25), ₹4,00,000 (FY 2025-26 onwards); old regime
   ₹2,50,000 (age-dependent; flagged).
7. Base tax per bucket at the rule rate.
8. Surcharge on total income (other income + net STCG + net LTCG before exemption + net speculative income):
   slabs above ₹50 lakh 10%, ₹1 crore 15%, ₹2 crore 25%, ₹5 crore 37%. Capped at 15% for 111A/112A gains (rule
   cap) and at the regime cap (new regime 25%). Marginal relief is not computed.
9. Health and education cess 4% on tax + surcharge.
10. Carry-forward of unabsorbed STCL/LTCL (8 years) and speculative loss (4 years). Expiry is not tracked.

Within a term, losses and exemptions are applied to the **highest-rate bucket first**, and LTCL is applied to LTCG
before leftover STCL so the more flexible STCL is preserved for carry-forward (taxpayer-favourable ordering).

Speculative income is netted within the year; only speculative losses (current and brought forward) offset it.
It is taxed at `slab_rate_for_business_income` from the tax profile.

`compute_tax_years()` chains carry-forward across consecutive years.

### When the estimate is "incomplete"

`status = "incomplete"` with message "Tax estimate incomplete — additional tax information required." when any
of these apply (the tax is still computed under the stated assumption):

| Missing fact | Assumption / effect |
|---|---|
| Tax regime | New regime assumed |
| Residency | Basic-exemption shortfall not applied (could reduce tax) |
| Other taxable income | Shortfall not applied; surcharge computed with other income = 0 (may be understated) |
| Slab rate for business income (with intraday profit) | Speculative tax excluded from the total |
| FMV on 31-Jan-2018 for a lot acquired on/before that date (not entered on the buy) | Grandfathering not applied (gain may be overstated) |
| Tax rule for a transfer date | Line unclassified and excluded |
| Old regime (age-dependent basic exemption) | ₹2,50,000 assumed |

Brought-forward losses not provided are assumed nil (noted, not incomplete).

### Not modelled

Rebate u/s 87A, marginal relief, rounding u/s 288A/288B, DTAA relief and NRI TDS (noted for NRIs),
carry-forward expiry, F&O (non-speculative business) income tax.

## FIFO lots

`app/portfolio/lots.py::build_lots`. Shares are deemed sold first-in-first-out (CBDT Circular No. 768 dated
24-Jun-1998).

- Processing is chronological per symbol. Within one day: corporate actions (ex-date) first, then buys, then
  intraday sells (matched only against that day's intraday buys), then delivery sells (FIFO over delivery lots).
  Intraday buys not squared off the same day are carried as delivery lots. Overselling raises an error (API 422).
- Buy charges stay with the lot and are allocated pro-rata by quantity as it is consumed; sell charges are allocated
  pro-rata across the lots a sell consumes. The last slice takes the residual so allocations sum exactly.
- **Split** (face value a → b): quantity × a/b, cost per share ÷ (a/b), acquisition date unchanged.
- **Bonus** a:b: one new zero-cost lot of floor(holding × a/b) shares acquired on the ex-date; fractional
  entitlements ignored. Shares bought on the ex-date are not entitled.

In the application, lots and realized matches are rebuilt from the full transaction history on every
transaction add/delete, using NSE corporate actions of type `split`/`bonus` with parsed ratios and an ex-date
after the first trade. Each lot stores its buy charges and, separately, the STT portion (`tax_lots.buy_stt`), so
hypothetical and harvesting estimates exclude buy STT from the cost of acquisition, as for realized sales.

## Charges

`app/tax/charges.py`. A schedule is selected by trade date (the covering schedule with the latest
`effective_from`; if none covers the date, the nearest is used and a note says so). Turnover = quantity × price
(premium for options).

Seeded schedules (`app/tax/defaults.py`), name "Discount broker (Zerodha-style) — verify with your broker",
source `https://zerodha.com/charges`, retrieved 2026-10-05:

| Item | Equity delivery | Equity intraday | Futures | Options (on premium) |
|---|---|---|---|---|
| Brokerage | ₹0 | 0.03%, max ₹20 | 0.03%, max ₹20 | ₹20 flat |
| STT buy | 0.1% | 0 | 0 | 0 |
| STT sell | 0.1% | 0.025% | 0.02% until 31-Mar-2026; **0.05% from 1-Apr-2026** | 0.1% until 31-Mar-2026; **0.15% from 1-Apr-2026** |
| Exchange transaction | NSE 0.00307%, BSE 0.00375% | NSE 0.00307%, BSE 0.00375% | NSE 0.00183% | NSE 0.03553% |
| SEBI fee | ₹10 per crore | ₹10 per crore | ₹10 per crore | ₹10 per crore |
| Stamp duty (buy) | 0.015% | 0.003% | 0.002% | 0.003% |
| IPFT | 0 (configurable) | 0 | 0 | 0 |
| GST | 18% on brokerage + exchange + SEBI + IPFT | same | same | same |
| DP charge | ₹15.34 per scrip per day on delivery sells (GST-inclusive) | — | — | — |

Two dated schedules exist: 2024-10-01 – 2026-03-31 and from 2026-04-01; equity rates are identical and only the
F&O STT changes (noted as Union Budget 2026). STT is rounded to the nearest rupee by default
(`stt_rounding: "rupee"`, can be set to `"paise"`). Users can override a transaction's charges with the contract
note total (`charges_total`); the component split then remains an estimate.

## Net P&L flow

`net_pnl(gross, charges, estimated_tax)` returns gross P&L, charges, P&L before tax, estimated tax and net after
tax. If the tax estimate is unavailable, net after tax is `None` (gross is always reported).

For open holdings (`GET /api/portfolios/{pid}`):

- each position shows charges paid, estimated exit charges for selling the whole position today, and the
  **incremental** tax if only that position were sold today: `tax(realized + hypothetical sale) − tax(realized)`
  for the current tax year, so set-offs and exemption already used by realized gains are respected;
- the portfolio summary's `estimated_tax_unrealized` is computed **once over all open lots together**, so the LTCG
  exemption and loss set-off are applied once (the per-position figures therefore need not add up to it); it
  carries its own `status` and incomplete reasons.

Unrealized gains are labelled "informational and not necessarily currently taxable". Tax is computed per taxpayer, not per portfolio:
`GET /api/portfolio/dashboard` recomputes realized and unrealized tax once across all live portfolios
(`pooled_tax_estimates`), and `GET /api/tax/summary` does the same for realized gains, so the annual exemption and
set-offs are applied only once.

The trade journal and paper trades store a simpler per-trade indicative tax: rate × max(gross − charges, 0) ×
(1 + cess), without set-off or exemption; the Tax Center (`/api/tax/summary`) is the portfolio-level estimate.

## Worked example

Produced by running the engine (`ChargesEngine.default()`, `RuleBook.default()`, `build_lots`,
`capital_gain_for_match`, `compute_tax_year`, `net_pnl`); all numbers below are program output.

Trades (delivery, NSE):

| Symbol | Buy | Sell | Buy charges (STT) | Sell charges (STT, DP) |
|---|---|---|---|---|
| AAA | 300 @ ₹1,000 on 2025-05-02 | 300 @ ₹1,600 on 2026-06-15 | ₹356.22 (₹300) | ₹513.30 (₹480, ₹15.34) |
| BBB | 50 @ ₹2,000 on 2026-01-12 | 50 @ ₹2,300 on 2026-05-20 | ₹118.74 (₹100) | ₹134.65 (₹115, ₹15.34) |
| CCC | 200 @ ₹500 on 2026-04-08 | 200 @ ₹460 on 2026-07-01 | ₹118.74 (₹100) | ₹110.77 (₹92, ₹15.34) |

AAA buy charges itemised: STT ₹300.00, exchange ₹9.21, SEBI ₹0.30, stamp ₹45.00, GST ₹1.71, brokerage ₹0.

Per-line results:

| Symbol | Term | Rate | Sale value | Cost incl. acquisition exp. (excl. STT) | Transfer exp. (excl. STT) | Capital gain | Trading P&L |
|---|---|---|---|---|---|---|---|
| AAA | LTCG | 12.5% (s.198, 2025 Act) | ₹4,80,000.00 | ₹3,00,056.22 | ₹33.30 | ₹1,79,910.48 | ₹1,79,130.48 |
| BBB | STCG | 20% (s.196, 2025 Act) | ₹1,15,000.00 | ₹1,00,018.74 | ₹19.65 | ₹14,961.61 | ₹14,746.61 |
| CCC | STCG | 20% (s.196, 2025 Act) | ₹92,000.00 | ₹1,00,018.74 | ₹18.77 | −₹8,037.51 | −₹8,229.51 |

Tax year 2026-27, profile: resident, new regime, other taxable income ₹18,00,000, no brought-forward losses.
Status: `complete`.

| Bucket | Gross gains | Loss set-off | Exemption | Taxable | Base tax | Surcharge | Cess |
|---|---|---|---|---|---|---|---|
| STCG @ 20% | ₹14,961.61 | ₹8,037.51 | ₹0 | ₹6,924.10 | ₹1,384.82 | ₹0 | ₹55.39 |
| LTCG @ 12.5% | ₹1,79,910.48 | ₹0 | ₹1,25,000.00 | ₹54,910.48 | ₹6,863.81 | ₹0 | ₹274.55 |

Total estimated tax ₹8,578.58 (base ₹8,248.63 + cess ₹329.95). No surcharge: total income is below ₹50 lakh.

| Gross P&L | Charges | P&L before tax | Estimated tax | Net after tax |
|---|---|---|---|---|
| ₹1,87,000.00 | ₹1,352.42 | ₹1,85,647.58 | ₹8,578.58 | ₹1,77,069.00 |

With an empty tax profile the same trades give the same total (₹8,578.58) but `status = "incomplete"` with:
"Tax regime not provided; new regime (default) assumed.", "Residency not provided — …", and "Other taxable income
not provided — surcharge depends on total income; computed assuming no other income (may be understated)."

Reproduce (from `backend/`, `PYTHONPATH=.`):

```python
from datetime import date
from decimal import Decimal as D
from app.tax.charges import ChargesEngine
from app.tax.rules import RuleBook
from app.tax.engine import capital_gain_for_match, compute_tax_year, TaxProfileIn, net_pnl
from app.portfolio.lots import TxnIn, build_lots

ce, rb = ChargesEngine.default(), RuleBook.default()
trades = [("b1", "AAA", "BUY", 300, "1000", date(2025, 5, 2)), ("s1", "AAA", "SELL", 300, "1600", date(2026, 6, 15)),
          ("b2", "BBB", "BUY", 50, "2000", date(2026, 1, 12)), ("s2", "BBB", "SELL", 50, "2300", date(2026, 5, 20)),
          ("b3", "CCC", "BUY", 200, "500", date(2026, 4, 8)), ("s3", "CCC", "SELL", 200, "460", date(2026, 7, 1))]
txns = []
for tid, sym, side, q, px, d in trades:
    br = ce.compute("delivery", side, D(q), D(px), "NSE", trade_date=d).rounded()
    txns.append(TxnIn(id=tid, symbol=sym, side=side, quantity=D(q), price=D(px), trade_date=d,
                      charges=br.total, stt=br.stt))
ledger = build_lots(txns)
lines = [capital_gain_for_match(m, rb) for m in ledger.matches]
profile = TaxProfileIn(residency="resident", regime="new", other_taxable_income=D("1800000"),
                       carried_forward_stcl=D(0), carried_forward_ltcl=D(0))
res = compute_tax_year(lines, "2026-27", profile, rb)
gross = sum((m.gross_pnl for m in ledger.matches), D(0))
charges = sum((m.charges_alloc for m in ledger.matches), D(0))
print(res.status, res.total_tax_estimate, net_pnl(gross, charges, res.total_tax_estimate).rounded())
```

## Tax-loss harvesting view

`GET /api/tax/harvesting` (`app/tax/harvesting.py`) lists positions with an unrealized capital loss and the tax
impact of selling the **whole** position at the current price (FIFO prevents selling only specific loss lots),
computed as `tax(realized + hypothetical) − tax(realized)` for the current tax year. Labelled
"Tax planning estimate — verify with a qualified tax professional." and "Not a sell recommendation."

## Keeping rules current

- Seeding inserts default rules and schedules only when the `tax_rules` / `charges` tables are empty. When the law
  or exchange charges change, add new dated rows (new `effective_from`, and close the old row with
  `effective_to`) or a new `rule_set_version`; editing `app/tax/defaults.py` alone does not update an existing
  database.
- `GET /api/tax/rules` and `GET /api/admin/charges` show what is stored.
- Each scan records the tax rule-set version in `recommendation_runs.tax_rule_version`.

## Disclaimers

- All tax and charge figures are estimates labelled `ESTIMATED`; the broker's contract note and a qualified tax
  professional are authoritative.
- Unrealized gains are informational and not necessarily currently taxable.
- The tool does not file returns and does not replace a chartered accountant or tax-filing software.
