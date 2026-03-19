# Nexus Core: Quantitative Options Architecture

![Nexus Dashboard Concept](https://img.shields.io/badge/Status-Active_Deployment-brightgreen) ![Python version](https://img.shields.io/badge/Python-3.9%2B-blue) ![Streamlit](https://img.shields.io/badge/Frontend-Streamlit-FF4B4B) ![Supabase](https://img.shields.io/badge/Database-Supabase-3ECF8E)

**Nexus Core** is an institutional-grade algorithmic options trading architecture designed to ingest real-time order flow, calculate multi-timeframe mathematical trends, and visualize quantitative positioning arrays across the US Equities market.

> **Security Note:** This repository is a sanitized, structural reflection of the live production architecture. All broker account references, webhook endpoints, API keys, and server infrastructure bounds have been safely eradicated and replaced with `.env` shells.

---

## 🏛️ Architectural Layout

The Nexus architecture is decoupled into three heavily resilient layers. By completely separating the intense data processing from the visual presentation, the front-end never crashes—no matter how volatile the market gets.

### 1. The Headless Processing Engines (Ubuntu VPS)
The brutal mathematical lifting occurs unconditionally in the background via persistent `tmux` terminals on a remote Linux server.
* **TradeStation WebAPI Ingestion**: Scripts like `analyze_snapshots.py` and `spx_profiler_nexus.py` connect via OAuth to capture raw option flow data and broad-market indices.
* **Algorithmic Models**: The backend calculates dynamic 200-period SMAs, McMillan Exhaustion Bands, Gamma Exposure (GEX) profiles, and Implied Volatility parameters.
* **Unusual Whales & ORATS Integration**: Real-time integration pipelines pull localized Dark Pool levels and unusual options flow parameters directly into the analysis array.

### 2. The Cloud Router (Supabase PostgreSQL)
Instead of the front-end executing complex logic, the math engines compile their final statistical arrays into rapid JSON payloads and serialize them across an autonomous pipe into **Supabase**.
* `supabase_bridge.py` allows background engines to continuously overwrite indices like `mtf_latest` and `spy_latest` natively in the cloud, acting as a high-speed, structural state manager.

### 3. The Visual Dashboard (Streamlit Web Interface)
Hosted exclusively on port `8501`, the **Streamlit Web Dashboard** (`app.py`) is the presentation layer. It simply mounts to the open internet and retrieves the pre-calculated Supabase JSON states every 30 seconds.
* **Password Gateway**: Bound natively behind a custom Python cryptographic lock to restrict data unauthorized public access.
* **Gemini LLM Auditor**: Integrates the Google Gemini 1.5 Pro AI directly into the dashboard state, using systemic logic to read the structural tables and write professional, forward-looking market analyses natively into the GUI. 

---

## ⚙️ Core Components

| Module | Description |
|--------|-------------|
| **`app.py`** | The central Streamlit visual hub containing the Market Regime mapping, Killbox analysis, and unified algorithmic output grids. |
| **`mtf_nexus.py`** | Generates Multi-Timeframe quantitative matrices including dynamic McMillan Volatility bands and statistical direction probabilities. |
| **`ts_nexus.py` / `nexus_hunter.py`** | The central TradeStation Manager engines handling OAuth tokens, automated routing, and raw option-chain array pulls. |
| **`gemini_market_auditor.py`** | Autonomous AI agent that digests raw data states from the dashboard, evaluating market structure to determine positional risk contexts. |

---

## 🛡️ License & Contact
This architecture serves as an advanced structural portfolio for programmatic algorithmic design. Built from the ground up to synthesize big-data streams into human-readable action-vectors.
