# ⚡ AI Infrastructure Investment Intelligence (AI3)

**AI Infrastructure, Data Centre, Small Electronic Components, Circular Electronics & IPO Investment Research Platform**

AI3 is a production-oriented Python quantitative research and portfolio-analysis platform built for Indian equity investors (`NSE`, `BSE`, `NSE Emerge`, `BSE SME`) with global supply-chain benchmark comparisons (`US`, `Taiwan`, `Japan`, `South Korea`, `Europe`).

---

## 🎯 Key Capabilities

1. **Complete 8-Segment AI Infrastructure Value-Chain Taxonomy (`config/sector_taxonomy.yaml`)**
   - `A_COMPUTE_HARDWARE`: GPU/AI servers, HPC systems, server motherboards, racks, EMS.
   - `B_ELECTRONIC_COMPONENTS`: Multilayer PCBs, PCBA, connectors, passives, power conversion, OSAT, precision machining.
   - `C_DATACENTRE_INFRA`: Colocation operators, hyperscale campuses, GPU cloud, MEP construction, UPS & switchgear.
   - `D_POWER_AND_GRID`: Generation utilities, HVDC/ISTS transmission, power transformers, conductors, cables, backup gensets.
   - `E_COOLING_THERMAL`: Precision chillers, liquid/CDU cooling, heat exchangers, compressors, cooling towers.
   - `F_CONNECTIVITY_FIBRE`: Optical fibre, transceivers, telecom subsea/terrestrial networks, enterprise interconnect.
   - `G_ENTERPRISE_AI_IT`: AI implementation, data engineering, cloud migration, engineering R&D.
   - `H_CIRCULAR_ELECTRONICS`: IT Asset Disposition (ITAD), server refurbishment, PCB/copper/precious-metal recovery, battery recycling, certified data destruction.

2. **Verified Security Master & High-Risk Gatekeeper (`config/seed_stocks.csv`, `core/security_master.py`)**
   - 74 deduplicated securities (46 Indian equities + 28 global supply-chain benchmarks).
   - Tracks historical ticker aliases (`POWERINDIA` $\leftrightarrow$ `HITACHIEN`, `TARIL` $\leftrightarrow$ `TRIL`, `KPIL` $\leftrightarrow$ `KALPATARU`, `BBOX` $\leftrightarrow$ `BLACKBOX`).
   - Isolates financially distressed, illiquid, or unverified-narrative candidates (`ELCIDIN`, `BDL`, `TTML`, `ECORECO`, `CEREBRAINT`, `NAMOEWASTE`, `ERI`) in a separate `HIGH_RISK_RESEARCH` tier so they are never silently dropped nor automatically placed into investable portfolios.

3. **100-Point AI Exposure Scoring Engine & 8 Investor Profiles (`analytics/exposure_scoring.py`)**
   - Combines Direct AI/DC Revenue Share (25 pts), Confirmed Backlog Visibility (15 pts), Customer Quality (15 pts), Supply-Chain Criticality (15 pts), Margin & ROCE Quality (10 pts), Balance-Sheet Strength (10 pts), and Valuation Reasonableness (10 pts).
   - Enforces **Fact-vs-Narrative** caps (`PRESS_RELEASE_ONLY` and `ANNOUNCED_PLAN` cannot receive full realised-revenue points) and mandatory **Risk Flags** (`CRITICAL` governance/balance-sheet flags block investability regardless of composite score).

4. **Value Alternative Finder (`analytics/value_alternatives.py`)**
   - For any popular or high-multiple stock (`DIXON`, `ABB`, `SIEMENS`, `HITACHIEN`, `CUMMINSIND`, `KAYNES`, `BLUESTARCO`, `POLYCAB`, `PERSISTENT`, `NETWEB`), identifies 3–5 cheaper supply-chain alternatives with similarity scores, P/E & EV/EBITDA discounts, quality comparisons, thesis-breaking risks, and liquidity sizing guidance.

5. **ETF & Smallcase Look-Through Overlap Module (`portfolio/overlap.py`)**
   - Tracks 10 Indian ETFs (`NIFTYBEES`, `ITBEES`, `ENERGY`, `JUNIORBEES`, `GOLDBEES`, `MONIFTY500`, `INFRABEES`, `MAKEINDIA`, `MID150BEES`, `HDFCSML250`) and 4 thematic smallcase baskets.
   - Respects subscription-locked smallcases (`SC_NIVESHAAY_TECHSTACK`) without fabricating constituents, supports custom CSV uploads, computes multi-sleeve look-through stock exposure, and models Smallcase subscription fees vs DIY direct equity replication.

6. **IPO, DRHP, RHP & Newly Listed Company Tracker (`pages/ipo_tracker.py`)**
   - Covers Jio Platforms, Zetwerk Manufacturing, Soleos Energy, Oswal Cables, and Tonbo Imaging plus newly listed equities (`NETWEB`, `CYIENTDLM`, `AVALON`, `RRKABEL`, `NAMOEWASTE`).
   - Enforces unconfirmed-date guards (`UNCONFIRMED / TBA`) and preserves `None` for 5-year CAGR on newly listed stocks.

7. **Portfolio Optimiser (8 Methods), Risk Stress Testing & Point-in-Time Backtester (`analytics/portfolio_optimisation.py`, `backtesting/engine.py`)**
   - Equal Weight, Conviction Weight, Inverse Volatility, Minimum Variance, Maximum Sharpe, Hierarchical Risk Parity (`HRP`), Black-Litterman, and Core-Satellite.
   - Point-in-time backtesting with listing-date guards, 60-day fundamental reporting lag, next-open execution, Indian delivery transaction costs (STT, stamp duty, exchange/SEBI fees, GST, liquidity slippage), and Walk-Forward validation.

---

## 🚀 Quickstart

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
Copy `.env.example` to `.env`. By default, `AI3_DATA_MODE=HYBRID` works out of the box with zero paid API keys required.
```bash
cp .env.example .env
```

### 3. Run the Streamlit Research Terminal
```bash
streamlit run app.py
```

### 4. Run Automated Discovery & Refresh Jobs via CLI
```bash
python -m jobs.update_security_master
python -m jobs.discover_new_listings
python -m jobs.discover_ipos
python -m jobs.refresh_prices
python -m jobs.refresh_financials
python -m jobs.research_news
```

### 5. Run the Test Suite
```bash
pytest -v
```

---

## 📚 Documentation
- [System Architecture & 28-Table Schema](docs/architecture.md)
- [Data Sources, Provenance & Adapters](docs/data_sources.md)
- [Quantitative Methodology & Scoring Rules](docs/methodology.md)

## ⚠️ Regulatory Disclaimer
AI3 is an analytical research and portfolio-simulation tool for educational and informational purposes only. It does not constitute SEBI-registered investment advice, does not place live brokerage orders, and does not automatically subscribe to IPOs.
