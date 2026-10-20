# Quantitative Methodology — Scoring, Value Alternatives, Portfolio Optimisation & Backtesting

## 1. 100-Point AI Infrastructure Exposure Scoring Model

Implemented in [`analytics/exposure_scoring.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/analytics/exposure_scoring.py):

$$\text{Total Score (100)} = S_{\text{Rev}}(25) + S_{\text{Backlog}}(15) + S_{\text{Customer}}(15) + S_{\text{Criticality}}(15) + S_{\text{Margin/ROCE}}(10) + S_{\text{BalanceSheet}}(10) + S_{\text{Valuation}}(10)$$

### Fact-vs-Narrative Enforcement
- Every company is classified into one of six `EvidenceType` tiers:
  1. `AUDITED_SEGMENT` — Explicitly reported in audited segment revenue or annual report notes.
  2. `CONTRACT_DISCLOSURE` — Confirmed exchange order-book or customer contract disclosure.
  3. `INDIRECT_INFRASTRUCTURE` — Core grid, cable, transformer, or chiller supplier into power/industrial buildouts.
  4. `ANNOUNCED_PLAN` — Board-approved capex or expansion under construction but not yet generating full revenue.
  5. `PRESS_RELEASE_ONLY` — Non-binding MOU or media announcement.
  6. `UNVERIFIED_NARRATIVE` — Market rumour or thematic misattribution (e.g., `ELCIDIN`, `TTML`).
- If `evidence_type` is `PRESS_RELEASE_ONLY`, `ANNOUNCED_PLAN`, or `UNVERIFIED_NARRATIVE`, Direct AI/DC Revenue points are strictly capped at $\le 5.0/25$ and Contract Backlog points at $\le 3.0/15$.

### 8 Configurable Scoring Profiles
`DEFAULT_100PT`, `CONSERVATIVE_QUALITY`, `BALANCED_GARP`, `HIGH_GROWTH_INFRA`, `SMALL_CAP_SUPPLIERS`, `CIRCULAR_ECONOMY_FOCUS`, `VALUE_CONTRARIAN`, `LOW_VOLATILITY_DEFENSIVE`, and `IPO_NEW_LISTING`.

## 2. Value Alternative Finder

Implemented in [`analytics/value_alternatives.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/analytics/value_alternatives.py):
- Computes a multi-factor business similarity score $S_{\text{sim}} \in [0, 100]$ combining primary category match, Jaccard overlap across all 8 categories and 68 subcategories, curated supply-chain family membership (e.g., high-kVA gensets `CUMMINSIND` $\leftrightarrow$ `KIRLOSENG` $\leftrightarrow$ `TDPOWERSYS`; HV transformers `HITACHIEN` $\leftrightarrow$ `CGPOWER` $\leftrightarrow$ `TRIL`), and operating margin proximity.
- Filters strictly for `is_investable=True` and `has_critical_red_flag=False`, and requires a positive valuation discount on P/E, EV/EBITDA, or PEG.

## 3. Portfolio Optimisation & Risk Engine

Implemented in [`analytics/portfolio_optimisation.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/analytics/portfolio_optimisation.py) and [`analytics/portfolio_risk.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/analytics/portfolio_risk.py):
- Supports 8 allocation algorithms: `EQUAL_WEIGHT`, `CONVICTION_WEIGHT`, `INVERSE_VOLATILITY`, `MINIMUM_VARIANCE`, `MAXIMUM_SHARPE`, `HRP` (Hierarchical Risk Parity via recursive bisection), `BLACK_LITTERMAN` (market-cap implied equilibrium returns blended with AI Exposure Score views), and `CORE_SATELLITE` (65% liquid large-cap core + 35% high-growth small/mid-cap component suppliers).
- Enforces configurable single-stock caps (default $\le 10\%$) and subsector caps (default $\le 30\%$) via iterative capped-simplex projection.

## 4. Point-in-Time Backtesting & Indian Transaction Cost Model

Implemented in [`backtesting/engine.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/backtesting/engine.py) and [`portfolio/rebalancing.py`](file:///c:/Users/epurntr/Downloads/Gravity/AI-Data-Center-Growth-Theme/portfolio/rebalancing.py):
- **Survivorship & Listing-Date Guard:** A stock is eligible at rebalance date $t$ only if $t \ge \text{listing\_date}$.
- **Next-Open Execution:** Signals generated at close $t$ execute at open $t+1$.
- **Indian Statutory Cash Delivery Costs:** Models brokerage (5 bps), STT (10 bps on delivery buy & sell), NSE exchange transaction charges (0.325 bps), SEBI turnover fees, stamp duty (1.5 bps on buy), 18% GST on brokerage/exchange/SEBI fees, plus liquidity-scaled market impact slippage.
