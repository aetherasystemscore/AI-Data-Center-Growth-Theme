# Data Sources, Provenance & Adapter Hierarchy

## 1. Data Provenance Philosophy

Every record in AI3 carries four mandatory provenance fields:
- `source_name`: Origin of the data (e.g., `NSE_ARCHIVES_EQUITY_L`, `YFINANCE_LIVE`, `SEBI_RSS_FEED`, `SEED_FUNDAMENTALS_FY25`, `SEED_REFERENCE_PRICE_MODEL`).
- `source_url`: Reference URL or seed file path.
- `as_of_date` / `reporting_date`: Effective date of the market observation or financial statement.
- `value_type`: Explicit classification distinguishing live exchange data (`ACTUAL_OFFICIAL_EXCHANGE`, `ACTUAL_MARKET_CLOSE`), regulatory filings (`REGULATORY_FILING_AND_SEED_SNAPSHOT`), curated reference snapshots (`SEED_REFERENCE_SNAPSHOT`), and calibrated offline sample price series (`SYNTHETIC_SAMPLE_CALIBRATED`).

## 2. Pluggable Provider Adapters (`data/providers/`)

| Domain | Adapter Class | Live Free Source (`HYBRID` / `LIVE`) | Offline / Fallback Source (`OFFLINE` / `HYBRID`) |
| :--- | :--- | :--- | :--- |
| **Security Master & Listings** | `HybridExchangeProvider` | NSE Official Archives (`EQUITY_L.csv`, `SME_EQUITY_L.csv`) | `config/seed_stocks.csv` (74 verified tickers + ISINs) |
| **OHLCV & Turnover** | `HybridPriceProvider` | `yfinance` (`*.NS`, `*.BO`, global tickers) | Deterministic business-day OHLCV generator calibrated to reference market cap & volatility |
| **Fundamentals & KPIs** | `HybridFundamentalsProvider` | Exchange filing snapshots | `config/sample_fundamentals_synthetic.csv` |
| **IPO, DRHP & RHP** | `HybridIPOProvider` | SEBI Official RSS Feed (`sebirss.xml`) | `config/seed_ipos.json` (5 detailed IPO filings) |
| **ETFs & Smallcases** | `AI3Repository` + CSV Uploader | Public AMC disclosures + User CSV upload | `config/seed_etfs.csv` & `config/seed_smallcases.json` |
| **News & Filing Evidence** | `HybridNewsProvider` | Exchange corporate announcements | Curated filing evidence with `EvidenceType` tags |

## 3. Mandatory Data Integrity Rules

1. **Missing Data Never Becomes Zero:** `parse_optional_float()` and `ensure_missing_not_zero()` preserve `None` / `NaN` for unavailable metrics (such as `rev_cagr_5y_pct` on newly listed companies `NETWEB`, `CYIENTDLM`, `AVALON`, `RRKABEL`, `NAMOEWASTE`).
2. **Locked Smallcases Never Fabricated:** Commercial subscription smallcases (`SC_NIVESHAAY_TECHSTACK`) have `constituents_locked=True` and an empty constituent array until the user uploads an authorised CSV export.
3. **Unconfirmed IPO Dates Never Fabricated:** Any IPO candidate with `dates_confirmed=False` is validated so `issue_open_date`, `issue_close_date`, and `listing_date` remain `None` (`UNCONFIRMED / TBA` in UI).
