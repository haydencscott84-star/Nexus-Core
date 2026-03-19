# System Audit Report
Date: 2025-11-30
Scope: Full System (Data -> Logic -> Execution)

## 1. Dependency Mapping
- **Data Source:** `yfinance` (External)
- **Risk Engine:** `watchtower_engine.py`
    - Inputs: SPY, RSP, VIX, VIX3M
    - Outputs: `market_state_live.json`
- **Strategy Engine (Mind):** `gemini_market_auditor.py`
    - Inputs: `market_state_live.json`, `market_config.json`, `gemini_constitution.json`
    - Outputs: Discord Alerts (Recommendations)
- **Execution Engine (Body):** `ts_nexus.py`
    - Inputs: ZMQ Commands (Manual/Dashboard)
    - **CRITICAL FINDING:** The Execution Engine is currently **BLIND** to the Watchtower. It does not read `market_state_live.json`. It relies on the human or the Dashboard to respect the Auditor's warnings.

## 2. Zombie Variables (Config Leak)
The following variables are defined in `market_config.json` but appear unused in the `gemini_constitution.json` logic text:
- `max_drawdown_pct`
- `max_position_size_pct`
- `vix_inversion_limit` (Watchtower uses hardcoded `1.05`)
- `vvix_crash_level`
- `breadth_divergence_threshold` (Watchtower uses hardcoded `0.01`)

## 3. Redundant Logic (Constitution)
`gemini_constitution.json` contains two conflicting/overlapping protocols:
1.  `risk_override_protocol`: References old `market_health.json`.
2.  `passive_intervention_protocol`: References new `market_state_live.json`.
**Recommendation:** Delete `risk_override_protocol` to avoid confusion.

## 4. Hard-Coded Logic
`watchtower_engine.py` contains hardcoded thresholds that should ideally be moved to `market_config.json`:
- VIX Inversion: `1.05`
- Breadth Divergence: `0.01` (1%)
- Rolling Vol Window: `5` days

## 5. Simulation Readiness
The system is ready for simulation. The `master_sim_harness.py` will test the **Risk -> Strategy** pipeline.
- **Scenario:** Flash Crash (VIX Spike).
- **Expected Result:** Watchtower -> RED. Auditor -> "PROHIBITED".
