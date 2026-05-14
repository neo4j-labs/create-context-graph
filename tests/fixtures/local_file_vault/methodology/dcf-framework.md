---
id: methodology-dcf-framework
created: 2026-01-30
updated: 2026-05-04
tags: [methodology, valuation, dcf]
aliases: ["DCF framework", "DCF methodology"]
status: stable
owner: Sarah Chen
---

# DCF Framework — Internal Methodology Note

How we run DCFs for [ACME](../companies/acme-corp.md) and its [comparables](../companies/betawidgets-inc.md). This is the methodology note — the live models live in our spreadsheet repo (not in this vault).

Authored and maintained by [Sarah Chen](../people/sarah-chen.md). Last reviewed by [Dana Liu](../people/dana-liu.md) on 2026-03-12.

A separate AsciiDoc version of the technical spec lives at [dcf-spec.adoc](./dcf-spec.adoc) (more formal, for the broader team).

## Core assumptions

We hold these constant across companies for comparability. Override only with explicit justification documented in the company note.

| Assumption | Value | Notes |
|---|---|---|
| Forecast horizon | 10 years explicit + terminal | aligns with industrial cycle length |
| Discount rate (industrials) | 9.5% nominal, USD | CAPM-derived, see [WACC build](#wacc-build) |
| Terminal growth rate | 2.0% nominal | matches long-run US GDP growth assumption |
| Tax rate | 23% effective | US fed + state blended |
| Maintenance capex / D&A | 1.0x | industrials should not under-spend |

We bias these conservative on purpose. If a thesis only works when we relax these, the thesis isn't strong enough.

## WACC build

For ACME specifically:
- Risk-free rate: 4.2% (10y UST baseline, smoothed 90d)
- Equity risk premium: 5.5% (long-run historical)
- Beta: 1.05 (2y daily, weekly cross-check)
- Cost of equity: 4.2% + 1.05 × 5.5% = **9.98%**
- After-tax cost of debt: 5.8% × (1 - 0.23) = 4.47%
- Capital structure: 75% equity / 25% debt (target, not current)
- **WACC: 9.98% × 0.75 + 4.47% × 0.25 = 8.6%**

We round to 9.5% for cushion against rate volatility — that's the 90bps adjustment Dana flagged in our [last methodology review](#change-log).

## Terminal value

Two methods, used as a cross-check:

1. **Perpetuity growth method** — `TV = FCF_t+1 / (WACC - g)` where g = 2.0%. This is our primary method.
2. **Exit multiple method** — apply current trading multiple to year-10 EBITDA. For ACME we use 10.5x EBITDA (mid-cycle, not current). cross-check only.

If the two methods disagree by >20%, one of them is wrong (usually the explicit period). Investigate before using the model.

For ACME the perpetuity method gives ~$1.8B terminal value contribution to enterprise value, exit multiple gives ~$2.1B. ~15% gap. acceptable — explicit-period margin assumptions are bringing them close enough.

> [!warning] historical mistake: in 2024 we set the exit multiple at 12x — that was the prevailing multiple at the time, not mid-cycle. ended up overvaluing the target by ~18%. **rule: exit multiples are *mid-cycle*, not current.** see [change-log](#change-log).

## Sensitivity analysis

We run three-by-three sensitivity tables on (WACC, terminal growth) for every model. Standard ranges:

- WACC: 8.5%, 9.5%, 10.5%
- Terminal growth: 1.5%, 2.0%, 2.5%

For ACME this generates a 9-cell fair value matrix ranging $24 (bear) to $43 (bull). Our [bull/base/bear cases](../companies/acme-corp.md#current-model) are derived from this matrix, not separate scenarios.

## Sum-of-parts model

Used when a company has materially different segments. We do this for ACME because [aftermarket within widget distribution](../companies/acme-corp.md#sub-segments-worth-distinguishing) is structurally different from the rest of the business.

Three-piece split for ACME:
- Widget Distribution (commodity + engineered) — apply distribution-segment multiple (~7-8x EBITDA)
- Widget Distribution (aftermarket) — apply consumables/aftermarket multiple (~14-16x EBITDA)
- Precision Components — apply precision-industrial multiple (~12-14x EBITDA)

This methodology change is the centerpiece of the [Q2 thesis call](../decisions/2026-q2-thesis-call.md). Dana's pushback: *"if the market wanted to disaggregate they would have. why is your disaggregation right?"* answer: it's not that we're disaggregating — we're saying the market is *implicitly* applying a blended multiple that under-weights aftermarket. unprovable directly, but [the math implies it](#sensitivity-analysis).

## Comparable set multiples

Used as a sanity cross-check, not a primary valuation method.

| Company | EV/EBITDA (NTM) | P/E (NTM) | Notes |
|---|---|---|---|
| ACME | 8.4x | 11.2x | our subject |
| [BetaWidgets](../companies/betawidgets-inc.md) | 9.1x | 12.8x | trading rich vs us on the margin compression story |
| DeltaSystems | 7.8x | 10.5x | pure-play distribution |
| Industrial Holdings Co | 10.3x | 14.1x | broader mix, Dana wants to exclude |

The comp set used for any model is documented per-company. The [Q2 ACME model](../companies/acme-corp.md#current-model) is using all four; [decision pending on whether to drop Industrial Holdings](../decisions/2026-q2-thesis-call.md#comparable-set).

External reference: see the [Q1 2026 sector report](../external/sector-report-q1-2026.html#valuation-comparables) which has slightly different comp picks — useful for sanity checking but we don't adopt their set.

## Change log

| Date | Change | By | Reason |
|---|---|---|---|
| 2026-01-30 | Initial version | Sarah Chen | DCF standardization across team |
| 2026-02-18 | Added WACC cushion (+90bps over CAPM) | Dana Liu | Rate volatility concern |
| 2026-03-12 | Reviewed, no changes | Dana Liu | Quarterly review |
| 2026-05-04 | Added sum-of-parts section | Sarah Chen | Q2 thesis call requires it |

## Related

- [[acme-corp]] · [[betawidgets-inc]]
- [[2026-q2-thesis-call]]
- [dcf-spec.adoc](./dcf-spec.adoc) — technical spec version
- #methodology #valuation
