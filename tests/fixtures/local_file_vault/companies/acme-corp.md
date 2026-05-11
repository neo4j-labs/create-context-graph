---
id: company-acme-corp
created: 2026-03-20
updated: 2026-05-10
tags: [company, internal, primary]
aliases: ["ACME", "ACME Corp", "ACME Incorporated"]
ticker: ACME
sector: Industrials
---

# ACME Incorporated

The home company. Everything in this vault is *for* ACME's strategy team, but this note is the structured one-pager on ACME itself — useful for explaining the org to consultants, new hires, and the [Q2 IC](../decisions/2026-q2-thesis-call.md) audience.

External one-line description that goes on slides: *"ACME Incorporated is a diversified mid-cap industrial manufacturer with leading share in widget distribution and adjacent precision components."*

## Snapshot

- HQ: Dayton, OH (corporate); manufacturing footprint across 11 US states + 3 in Mexico
- ~$2.1B FY25 revenue, 18.4% adj. EBITDA margin
- Public, listed on NYSE as ACME (mid-cap, ~$3.8B market cap)
- Two reporting segments: Widget Distribution (~64% rev) and Precision Components (~36% rev)
- Largest customer (NDA, ~9.5% of revenue) — see [customer-concentration-note](#customer-concentration)
- Org chart link: not in this vault, but see [Marcus Reyes](../people/marcus-reyes.md) for corp dev structure

See also: [BetaWidgets Inc](./betawidgets-inc.md) — our nearest public comp; [DCF framework](../methodology/dcf-framework.md) — how we model the segments.

## Widget Distribution segment

The legacy core. Distributes industrial widgets (technical category — see [SIC 5085 reference](https://www.sic-code.com/sic-code/5085)) to ~3,200 OEMs in North America. This is where ACME has structural advantage:

- 47 distribution centers, ~95% of US OEMs within 200 miles of one
- 60+ year relationships with top customers, multi-generation
- Long-tail SKU mix (~84,000 active SKUs) creates switching friction
- ROIC consistently mid-20s — much better than the segment looks like it should be

The segment is the cash cow but also the [growth ceiling](#growth-thesis) — saturated NA market, low pricing power on commodity SKUs.

### Sub-segments worth distinguishing

The street treats Widget Distribution as one block. internally we track three:

1. **Commodity widgets** — high volume, low margin, price-sensitive. ~35% of segment revenue, ~18% segment gross margin.
2. **Engineered widgets** — custom specs, longer cycle, sticky. ~45% of segment revenue, ~36% segment gross margin.
3. **Aftermarket & service** — replacement parts + on-site service contracts. ~20% of segment revenue, ~52% segment gross margin. Best part of the business by far.

If we ever do a sum-of-the-parts, the aftermarket sub-segment is the hidden gem. See [sum-of-parts model](../methodology/dcf-framework.md#sum-of-parts-model).

## Precision Components segment

Smaller, faster-growing. Custom-engineered components for aerospace, medical devices, and EV powertrains. Acquired piecewise through three M&A deals between 2017–2022 (see [Marcus Reyes](../people/marcus-reyes.md)'s deal history note).

- ~$760M FY25 revenue, ~23% adj. EBITDA margin
- Higher growth (14% CAGR last 3y), higher margin
- More cyclical (aero exposure)
- Direct comparable: [BetaWidgets' Precision Solutions arm](./betawidgets-inc.md#precision-solutions)

## Customer concentration

We don't disclose the names but internally:

| Tier | Customers | % of Revenue | Avg Tenure |
|---|---|---|---|
| Top 1 | 1 | 9.5% | 23 years |
| Top 5 | 5 | 28.1% | 18 years avg |
| Top 25 | 25 | 56.0% | 12 years avg |
| Long tail | ~3,170 | 44.0% | varies |

Compare to [BetaWidgets concentration](./betawidgets-inc.md#customer-concentration) where top 1 is 23% — much more concentrated. our diversity is a real durability advantage.

## Current model

Most recent valuation model: [Q2 2026 base case](../methodology/dcf-framework.md#core-assumptions). Key outputs:

- Base case fair value: $34/share (current $27)
- Bull case (margin expansion + share gain from BW): $41
- Bear case (tariff escalation, demand softness): $22

Sensitivity analysis is in the [dcf framework note](../methodology/dcf-framework.md#sensitivity-analysis).

## Growth thesis

Three levers, in order of probability:

1. **Margin expansion in Precision Components** — moving up the value chain on aero programs
2. **Aftermarket share within Widget Distribution** — currently 20% of segment, structural ceiling closer to 30%
3. **Tuck-in M&A in adjacent precision categories** — [Marcus Reyes](../people/marcus-reyes.md) tracking ~8 targets

What's NOT in the thesis: a big home-run acquisition. Board has been clear about capital discipline. See [2026-Q2 thesis call](../decisions/2026-q2-thesis-call.md) decision trace.

## Risks

- Tariff exposure — see [Tariq Osei](../people/tariq-osei.md)'s [tariff scenario note](../external/sector-report-q1-2026.html#tariff-scenarios)
- Customer concentration in Precision Components (top 3 = 47% of segment) — much higher than widget distribution
- Successor risk on the CEO — [[CEO succession note]] (in progress)
- ESG: legacy industrial sites, two with known remediation obligations

## Related

- [[betawidgets-inc]] — comparison anchor
- [[dcf-framework]] — methodology
- [[2026-q2-thesis-call]] — current open decision
- [Dana Liu](../people/dana-liu.md) — sector lead, primary internal critic of this thesis
