# System Context & Architecture

> [!IMPORTANT]
> This file is a living document of the Nexus Trading System architecture (Updated Jan 2026). Refer to this for server details, data flow, and stability protocols.

## 1. Server Information

> [!CAUTION]
> **CRITICAL ARCHITECTURE MANDATE**:
> The Nexus System uses a **24-Window "Cockpit" Layout** inside Tmux.
>
> - **DO NOT** use a single supervisor script to run everything in one window.
> - **Exception**: `market_bridge_v2.py` and `alert_manager.py` run in their own specific interactive windows in the foreground.
> - **Visuals**: Each critical service (Sweeps, Profilers, Greeks, Dashboard) MUST have its own dedicated interactive window.
> - The canonical launch script is `launch_cockpit.sh`.

| Component | Detail |
| :--- | :--- |
| **IP Address** | `<YOUR_VPS_IP>` |
| **User** | `root` |
| **Auth** | `<YOUR_VPS_PASSWORD>` (Root) |
| **Root Directory** | `/root/` (on remote server) |
| **Local Workspace** | `/Users/haydenscott/Desktop/Local Scripts/` |
| **Deployment** | via `remote_deploy.sh` (rsync/tar pipe) |
| **Restart Cmd** | `./launch_cockpit.sh` (manages 24 tmux windows) |

## 2. Technology Stack

### Core Runtime

- **Language**: Python 3.10+
- **Environment**: Virtual Environment (`/root/.venv/bin/python3` for MTF_NEXUS)
- **Process Management**: `tmux` (Terminal Multiplexer) for detached sessions.

### Libraries & Frameworks

- **Asynchronous I/O**: `asyncio`, `aiohttp` (High-performance non-blocking I/O).
- **Messaging**: `pyzmq` (ZeroMQ) for inter-process communication (IPC) between components.
- **Data Analysis**: `pandas`, `numpy`, `scipy` (Financial math & time-series).
- **UI/TUI**: `textual` (Terminal User Interface for `ts_nexus.py`, `nexus_sweeps_tui_v1.py`, etc.).
- **AI/LLM**: `google-generativeai` (Gemini Pro/Flash models).

## 3. Operations & Intelligence

### A. The "Timing Intelligence" Upgrade (Jan 24, 2026)

To solve the "When" problem, the system now features two dedicated Timing Gauges:

1. **Jard's Momentum (Velocity)**:
    - **Engine**: `TS_NEXUS` (Window 1).
    - **Logic**: Tracks price velocity over a 60-second sliding window (`deque`).
    - **Metric**: `-10` (Bearish Velocity) to `+10` (Bullish Velocity). `0` = Stasis.
2. **RVOL (Volume Intelligence)**:
    - **Engine**: `STRUCTURE` (Window 7) calculates real-time Relative Volume.
    - **Visual**: `HISTORY` (Window 9) displays `D:1.2x H:2.1x` in the header.
    - **Logic**: Hourly RVOL > 2.0 triggers a "Green Light" condition (Confirmation).

### B. Sheets Bridge Architecture (Delta Premium)

The Google Sheets report (`nexus_sheets_bridge.py`) is enriched with "Delta Premium" (Wall Strength) using a robust "Source of Truth" pipeline:

1. **Persistence**: `gex_worker_nexus.py` (Window 24) saves the **Raw Option Chain** to `nexus_gex_chain.json`.
2. **Aggregation**: `analyze_snapshots.py` (Window 9) consumes this chain and **sums** the Notional Delta across **ALL** expirations.
3. **Bridge**: `nexus_sheets_bridge.py` (Window 23) pushes this aggregated value to the Sheet.

### C. Data Flow Diagram

```mermaid
graph TD
    A[Scrapers & Streamers] -->|Write JSON| B(JSON State Files)
    B -->|Read & Merge| C{Market Bridge V2}
    C -->|Write Coalesced State| D[market_state.json]
    D -->|Read Context| E(Gemini Auditor)
    E -->|Analyze & Alert| F[Discord / Triggers]
    E -->|Analyze & Alert| F[Discord / Triggers]

### D. Stability & Logic Fixes (Jan 26, 2026)

**1. Auditor Scheduling (Quarter-Hour Alignment)**
- **Issue**: Standard `sleep(900)` caused execution drift (e.g. 12:00 -> 12:17 -> 12:35) due to processing time.
- **Fix**: `gemini_market_auditor.py` now calculates the exact seconds to the next **:00, :15, :30, or :45** mark.
- **Behavior**: Execution is consistently aligned to market clock quarters.

**2. SPX Profiler & GEX Pipeline**
- **Issue**: GEX data was displaying as "N/A" due to `fetch_gex=False` hardcoded loop and cache variable mismanagement.
- **Fixes**:
    - Re-enabled ORATS fetch in `run_scan`.
    - Patched variable mapping to ensure fresh data updates `nexus_gex_static.json`.
    - Robustified TUI renderer against Pandas Series ambiguity.
- **Key Changes**: Output keys are now `short_gamma_wall_above`, `short_gamma_wall_below`, `volume_poc_strike`.

**3. Bridge Key Mapping (Data Flow Healing)**
- **Issue**: `market_bridge_v2.py` looked for legacy keys (`call_wall`) while Profiler output new keys.
- **Fix**: Implemented explicit mapping in Bridge:
    - `call_wall` <- `short_gamma_wall_above`
    - `magnet` <- `volume_poc_strike` (Proxy)
    - `zero_gamma` <- `gex_flip_point`


## 4. System Launch & Process Management

### E. Jan 30, 2026: Sentiment & Wall Fixes

**1. Sentiment Reset Behavior**
- **Issue**: Sentiment breadth flatlined at 0 for SPX/SPY.
- **Root Cause**: `spx_sentiment_state.json` corrupted (Reset to 0, but contained old trade history).
- **Fix**: Deleted corrupted files. System now correctly accumulates sentiment intraday. **Note**: Sentiment resets to 0 daily and on service restart.

**2. Sheets Bridge Wall Premium**
- **Issue**: "Call Wall" and "Put Wall" strings missing Premium data (e.g., `[$2.2B Δ]`).
- **Technical**: `nexus_sheets_bridge.py` failure to handle Float vs Dict types in GEX Profiler output.
- **Architecture**: Patched `nexus_sheets_bridge.py` with robust float handling and fuzzy key matching for Dictionary lookups.

### A. The "Cockpit" Philosophy (24-Window Architecture)

The Nexus System is constructed as a **24-Window Tmux Session** named `nexus`. This architecture serves as the "Flight Deck," providing immediate visibility and manual control over every active service.

> [!NOTE]
> **Construction Logic**:
>
> - **Session**: Created via `tmux new-session -d -s nexus`.
> - **Self-Defense**: Services use `nexus_lock.enforce_singleton()` (File Locks) instead of brittle PID killing.
> - **Signal Propagation**: `robust_wrapper.py` traps SIGTERM/SIGINT and forwards them to child processes.

### B. Window Map (The Canonical Layout)

| ID | Name | Script | Role |
| :--- | :--- | :--- | :--- |
| **0** | **CONTROL** | `htop` | System Resource Monitoring |
| **1** | **TS_NEXUS** | `ts_nexus.py --headless` | **Core**: Execution & **Momentum Engine** (Headless Backend) |
| **2** | **WATCHTOWER** | `watchtower_engine.py` | **Core**: Stop-Loss & Anomaly Monitor |
| **2** | **WATCHTOWER** | `watchtower_engine.py` | **Core**: Stop-Loss & Anomaly Monitor |
| **3** | **NOTIFICATIONS**| `nexus_notifications.py`| **System**: ZMQ->Discord Router |
| **4** | **BRIDGE** | `market_bridge_v2.py` | **System**: Metric Unification & Persistence |
| **5** | **SPX_PROF** | `spx_profiler_nexus.py` | **Data**: SPX Profile (Read-Only TUI) |
| **6** | **SPY_PROF** | `spy_profiler_nexus_v2.py` | **Data**: SPY Market Profile TUI |
| **7** | **STRUCTURE** | `structure_nexus.py` | **Data**: Gamma Walls & **RVOL Calc** |
| **8** | **ALERTS** | `alert_manager.py` | **Logic**: Alert Manager |
| **9** | **HISTORY** | `analyze_snapshots.py` | **Logic**: Trap Analysis & **RVOL HUD** |
| **10** | **(VACANT)**| `-` | (Bridge moved to Window 4) |
| **11** | **HUNTER** | `nexus_hunter.py` | **Logic**: Opportunity Scanner |
| **12** | **AUDITOR** | `gemini_market_auditor.py` | **AI**: Gemini Market Analyst |
| **13** | **UW_NEXUS** | `uw_nexus.py` | **Data**: Unusual Whales Streamer |
| **14** | **DASHBOARD**| `trader_dashboard_v3.py` | **UI**: Manual Trading Interface |
| **15** | **VIEWER_DASH**| `viewer_dash_nexus.py` | **UI**: Read-Only Dashboard Mirror |
| **16** | **SPREADS** | `nexus_spreads.py` | **Logic**: Spread Management Engine |
| **17** | **DEBIT_SNIPER**| `nexus_debit.py` | **Logic**: Debit Spread Bot |
| **18** | **MTF_NEXUS** | `mtf_nexus.py` | **System**: Multi-Timeframe Analysis |
| **19** | **SWEEPS_V3** | `nexus_sweeps_v3.py` | **Data**: Sweeps Stream (IV Filtered) |
| **20** | **GREEKS** | `nexus_greeks.py` | **Math**: Portfolio Delta/Gamma Engine |
| **21** | **HEDGE** | `nexus_hedge.py` | **Logic**: Dynamic Delta Hedging |
| **22** | **WATCHDOG** | `system_watchdog.py` | **System**: Health Monitor |
| **23** | **SHEETS_BRIDGE** | `nexus_sheets_bridge.py` | **Reporting**: Google Sheets Report (Weekdays Only) |
| **24** | **GEX_WORKER** | `gex_worker_nexus.py` | **System**: Background GEX Calculator |

## 5. Discord Notification Architecture (Decoupled)

To prevent cosmetic or network failures from crashing critical trading logic, the system uses an **Event-Driven "Fire-and-Forget" Protocol** via Window 19 (`NOTIFICATIONS`).

1. **Senders (Publishers)**: `gemini_market_auditor.py`, `alert_manager.py`.
2. **Receiver**: `nexus_notifications.py` (Listen Port `5575`).
3. **Resilience**: Implements "500 Patch" (Delete & Retry) to handle Discord API errors gracefully.

## 6. Recent Stability Upgrades (Jan 25, 2026)

### A. ZMQ & API Stability

- **Resilient Listeners**: `nexus_sweeps_tui_v1.py` now uses a `while True` retry loop with exponential backoff for ZMQ connections, preventing termination on network blips.
- **API Guardrails**:
  - **Unusual Whales**: Main feed moved to WebSockets (Safe). Polling scripts staggered to ~850 calls/day (Limit: 15k).
  - **ORATS**: Polling intervals optimized to ~1 call/min (Limit: 400/min).

### B. Logic Enhancements

- **Sheets Bridge (Window 23)**: Replaced blind append with **"Next Row" Calculation** (`len(A:A) + 1`) to ensure intraday updates stack vertically without overwriting data.
- **Auditor Intelligence (Window 12)**:
  - **P/C Ratios**: Integrated P/C Volume & OI Ratios from `spx_profiler_nexus.py`.
  - **Contextualization**: Explicitly instructs AI that **High P/C (>1.0)** indicates Dealer Hedging (Support), preventing false bearish narratives.

### C. Critical Repairs (Jan 25, 2026 - Part 2)

- **Sheets Data integrity**:
  - **Escaping**: Added `'` prefix to all metric strings starting with `+` or `-` (e.g. `'+1.2%`, `'+/- $5`) to prevent Google Sheets from interpreting them as broken formulas (`#ERROR!`).
  - **Resilience**: Added global `try/except` loop to `nexus_sheets_bridge.py` preventing cascade failures.
- **Service Recovery**:
  - **Bridge (Window 10)**: explicitly restored `market_bridge_v2.py` to Window 10, resolving Watchdog crash loops.

## 7. Logic Alignment & Stability (Jan 26, 2026 - Critical)

### A. GEX Methodology Alignment (SPX vs SPY)

A critical discrepancy was identified and fixed in the GEX calculation logic:

- **Old SPY Logic**: Used "Gross Short" assumption (`-1 * (Call + Put)`), resulting in inflated, lopsided values.
- **New SPY Logic**: Aligned to match **SPX Netting** (`Call - Put`).
- **Result**: `viewer_dash_nexus.py` (generating `nexus_spy_profile.json`) now produces data directly comparable to the SPX Profiler.

### B. Gemini Auditor Robustness

To prevent "Silent Failures" where the Auditor misses market updates:

- **Timeout Extension**: Increased API timeout from **30s** to **120s** to accommodate complex "Gentle Mode" chain-of-thought generation.
- **Retry Loop**: Implemented a **3-Attempt Retry** with exponential backoff for `504` and `500` errors.
- **Hard Reset Protocol**: Documented that `nexus:AUDITOR` requires a full `kill-window` / `new-window` cycle for reliable restarts, rather than `respawn-window`.

### C. Weekly Expiry Logic

- **Dynamic Date Selection**: Both SPX and SPY now explicitly target the **"Next Friday"** expiry for the "NEXT" row in the Structural Framework, scrubbing the nested GEX objects to find the correct date.

### D. Viewer Dashboard Logic (Jan 26, 2026)

- **Implied Futures Pricing**:
  - The Dashboard Header now displays an **"Implied SPY Price"** derived from `MESH26` futures performance.
  - **Formula**: `SPY_Prev_Close * (1 + MESH_Pct_Change)`.
  - **Purpose**: Provides a theoretical "gap" indication when the equity market is closed (e.g., Sunday Night).

- **GEX Logic Alignment (Pin/Flip)**:
  - **Flip Logic**: Switched from "Cumulative Zero Crossing" (which fails in deep short gamma) to **"Local Zero Crossing"** (Pivot Point).
  - **Wall Logic**: Switched from "Closest Strike" to **"Max Magnitude"** selection.
  - **Result**: Ensures "Pin" and "Flip" data in the dashboard matches the trusted Profiler engine.

### D. GEX Physics Override (Hallucination Fix)

To prevent the LLM from hallucinating incorrect market mechanics (e.g., claiming Negative GEX = Stability):

- **Mandatory Physics Block**: A hardcoded instruction block has been injected into the `gemini_market_auditor.py` System Prompt.
- **Rules**:
  1. **Positive GEX**: Dealers are Long Gamma -> Pinning/Stability.
  2. **Negative GEX**: Dealers are Short Gamma -> Volatility/Acceleration.
  3. **Override**: Explicitly forbids the model from associating Negative GEX with "Stability".

### E. GEX Profiler & Viewer Repairs (Jan 26, 2026 - Critical)

- **Backend/Frontend Synchronization**:
  - Identified "Split Brain" issue where `viewer_dash_nexus.py` (Frontend) was re-calculating statistics locally, ignoring fixes in `gex_worker_nexus.py` (Backend).
  - **Resolution**: Ported fixed logic to the Viewer to ensure data consistency.

- **Column Logic Definitions**:
  - **Accel (R)**: Redefined from "Velocity" to **"Major Resistance Strike"**.
    - **Logic**: Primary = Short Gamma Wall (Red). Fallback = Long Gamma Wall (Green/Call Resist) if Short Gamma is absent.
  - **Vol POC (Point of Control)**: Switched from **Raw Volume** to **Notional Volume** (`Volume * Strike * 100`).
    - **Purpose**: Filters out cheap, deep OTM "lottery ticket" volume (e.g., $650 Puts) that skewed the POC away from Spot ($700).

- **UI Stabilization**:
  - **Duplicate Prevention**: Identified and terminated a rogue dashboard instance in Window 0 (`CONTROL`), ensuring `nexus:15` (`VIEWER_DASH`) is the sole UI source.
  - **Crash Fix**: Patched `viewer_dash_nexus.py` to handle empty Pandas Series gracefully, preventing `ValueError` crashes during data loading.

### F. Debit Sniper Execution Upgrade (Jan 26, 2026)

- **Smart Execution Logic**:
  - **Problem**: Default execution prioritized "Midpoint" fills, which often hanged on wide spreads.
  - **Fix**: Implemented **"Best Bid/Ask" Prioritization** for critical entries.
  - **Logic**: If `spread_width > threshold`, the sniper now targets the aggressive side (Ask for Buy, Bid for Sell) to ensure immediate fill, preventing "chasing" the price.

### G. Delta & Structural Enhancements (Jan 26, 2026)

- **Delta Premium Architecture**:
  - **Source**: `spx_profiler_nexus.py` now calculates Total Notional Delta (`contracts * 100 * delta`) for each key strike (Calls/Puts).
  - **Persistence**: Writes purely to `nexus_walls_context.json` (New Artifact).
  - **Consumption**: `nexus_sheets_bridge.py` reads this artifact to append `[+$4.2B Δ]` tags to the Sheet.
  - **Resilience**: Implemented **Fuzzy Matching** (`abs(key - strike) < 0.1`) in the Bridge to handle float formatting discrepancies ("7000" vs "7000.0").

- **"No Fly Zone" Logic Definition**:
  - **Type 1: Compression (Tight Walls)**
    - **Trigger**: `Call Wall - Put Wall < $5.00`.
    - **Effect**: Google Sheet displays `ACTIVE (Tight $X.XX)`.
  - **Type 2: Market Regime (Chop)**
    - **Trigger**: Upstream State (`momentum_score`) calculates Momentum Label as "NEUTRAL" or explicitly "CHOP".
    - **Effect**: Google Sheet displays `ACTIVE (CHOP)`.

- **Momentum Engine ("Jard's Tape")**:
  - **Location**: `ts_nexus.py` (Line 1123).
  - **Artifact**: Exports high-frequency state to `nexus_tape.json` for consumption by `market_bridge_v2.py`.

### H. Final System Stabilization (Jan 26, 2026 - Part 3)

#### 1. Zombie Process Elimination (Auditor)
- **Problem**: `gemini_market_auditor.py` continued to display "N/A" for GEX Framework despite verifying the fix on disk.
- **Root Cause**: The running process (PID 2983472) was stale (3+ hours old) and ignoring file updates.
- **Resolution**: Implemented **Hard Restart Protocol** (`tmux respawn-window -k`) to forcefully kill the zombie process and reload the new code.
- **Verification**: Logs confirmed immediate ingestion of the "Flip/Pin" data after restart.

#### 2. Sweeps V2 Crash (DuplicateKey)
- **Problem**: `nexus_sweeps_tui_v2.py` crashed with `DuplicateKey` error in the Textual DataTable.
- **Root Cause**: Overlap between "Backfill Data" (API) and "Live Data" (ZMQ) resulted in identical Trade UIDs (`Chain_Premium_Time`) confusing the UI key tracker.
- **Resolution**:
  - **Deduplication**: Added explicitly `if uid in SEEN_IDS: return` check before processing.
  - **Defensive UI**: Wrapped `add_row` in a `try/except` block to silently ignore any collisions that slip through.
- **Window Map Correction**: Updated `context.md` to reflect server reality:
  - **Window 4**: BRIDGE
  - **Window 19**: SWEEPS_V2 (Primary)

#### 3. SPX Profiler "Price Zero" Fallback
- **Problem**: SPX Profiler TUI showed "N/A" for GEX stats despite valid backend logic.
- **Root Cause**: ORATS API intermittently returned `stockPrice: 0` for SPX, causing GEX calculations (Spot Gamma, Flip Point) to fail mathematically (Divide by Zero).
- **Resolution**: Implemented **Robust Price Proxy**:
  - Logic: `If SPX_Price <= 0: Use (SPY_Price * 10) + 30`.
  - Result: Ensures GEX engine always has a valid reference price to calculate levels.

#### 4. Data Freshness Audit
- **Verified**: All snapshot engines (`spx_profiler`, `nexus_sweeps`, `spy_profiler`) are successfully dumping data to disk on their scheduled cadence (Real-time or Hourly).

#### 5. TS Nexus Migration to Headless (Jan 26, 2026)
- **Problem**: `ts_nexus.py` consumed **5GB+ RAM** due to TUI/Textual widget accumulation over days, checking the OOM Killer which destabilized the Market Auditor.
- **Resolution**: Permanently migrated Window 1 to **Headless Mode** (`--headless`).
- **Impact**: Reduced memory footprint by ~90%, eliminating the "Sequential Crash" loop.

## 8. System Health & Safety Architecture (Jan 26, 2026 - Critical Upgrade)

To address the "Zombie Process" failure mode where services (like SPX Profiler or Bridge) appeared running but ceased data output, a new dual-layer safety system was deployed.

### A. Nexus Guardian (`nexus_guardian.py`)
> **Window**: 10 (GUARDIAN)
> **Role**: Passive Heartbeat Monitor

A dedicated watchdog service that replaces simple process checking with **File Liveness Monitoring**. It assumes that if a critical file hasn't been touched in $X$ minutes, the writer process is dead/hung, regardless of its PID status.

| Target Service | Monitored File | Max Age (Threshold) | Action |
| :--- | :--- | :--- | :--- |
| **SPX Profiler** | `nexus_spx_profile.json` | **15 Minutes** | `tmux respawn-window -k -t nexus:SPX_PROF` |
| **Market Bridge** | `market_state.json` | **5 Minutes** | `tmux respawn-window -k -t nexus:BRIDGE` |
| **Sheets Bridge** | `sheets_bridge.log` | **60 Minutes** | `tmux respawn-window -k -t nexus:SHEETS_BRIDGE` |

### B. Bridge Safety Parsing (Zero-Data Defense)
> **Engine**: `market_bridge_v2.py`
> **Goal**: Prevent "Flashing Zeros" on the Dashboard.

Previous iterations blindly propagated "0" values if a source file was empty or corrupt (creating the "Missing GEX" bug). The V2 Bridge implements strict semantic validation:

1.  **Persistence**: Loads `bridge_persistence.json` on startup to recall the last known valid state.
2.  **Semantic Validation**:
    - **Logic**: If incoming data implies `Net GEX == 0` AND the previous state had valid GEX, the update is **REJECTED**.
    - **Outcome**: The Bridge flags the feed as `STALE (SEMANTIC FAIL)` but continues to serve the **Last Known Valid Value** to the dashboard/Sheets.
3.  **Result**: Prevents transient API failures or calculation errors from wiping out critical decision-making data on the user's screen.

### C. Sweeps V3 (The "Immutable Filter" Release)
- **Version**: `nexus_sweeps_v3.py` (Replaces `_v2`)
- **Core Feature**: **Implied Move Filtering**
    - **Logic**: Calculates active Implied Move Range ($Spot \pm IV_{30d} \times \sqrt{DTE/365}$).
    - **Enforcement**: **Hard Rejects** any trade outside this range.
    - **Robustness**:
        - **Startup**: Forces synchronous IV load (blocks race condition).
        - **Missing Data**: Falls back to Global Spot Price if trade lacks price info (catches 99% of backfill errors).

### D. Robust Wrapper (Signal Propagation)
> **Engine**: `robust_wrapper.py`
> **Goal**: Prevent Zombie Processes and Lock Contention.

The wrapper now acts as a **Signal Proxy**:
1. **Traps Signals**: Intercepts `SIGTERM` and `SIGINT`.
2. **Forwards**: Immediately sends the signal to the child process.
3. **Waits**: Blocks until the child exits gracefully.
4. **Force Kill**: If child hangs > 5s, sends `SIGKILL`.

**Anti-Lock Logic**:
- If a script exits with `Code 1` (Lock Error) within <2 seconds of launch, the wrapper assumes a **Zombie Lock** exists and executes `pkill -f [script_name]` to free the resource before retrying.
### I. System Audit & Integrity Repairs (Jan 26, 2026 - Part 4)

#### 1. Money Flow Integrity (Auditor)
- **Problem**: Auditor Discord messages showed inflated, nonsensical "Money Flow" values (e.g., -$1.3B).
- **Root Cause**:
    1.  **Stale Data**: Merging expired `nexus_sweeps_v1.json` data.
    2.  **Unit Mismatch**: Adding **Premium ($)** to **Delta Exposure (Share Esq)**.
- **Resolution**:
    -   **Purged**: Removed V1 integration.
    -   **Standardized**: Auditor now calculates **Net Premium ($)** directly from live V3 lists.
    -   **Display**: Discord label updated to **"SWEEPS (NET PREMIUM)"** with 0DTE listed first.
  
#### 2. Sheets Bridge Resilience
- **Guardian Conflict**: `nexus_guardian.py` was killing the Sheets Bridge because `sheets_bridge.log` appeared stale.
    - **Fix**: Implemented **File-Based Heartbeat** in `nexus_sheets_bridge.py` (writes timestamp every 10s).
- **Data Fallback**: `market_state.json` occasionally broadcasted "0" for Magnets/Walls.
    - **Fix**: Bridge now strictly checks for zeros and **Falls Back** to `nexus_spx_profile.json` (Source of Truth) if State is invalid.

#### 3. Zombie Defense
- **Sweeps V2**: Discovery of "Ghost Processes" required a "Nuke and Pave" strategy.
#### 4. SPX Profiler IV Filtering (Jan 26, 2026)
- **Feature**: Implemented **30-Day Implied Move Filtering** to purge deep OTM noise.
- **Formula**: `Range = Spot ± (Spot * IV_30d * sqrt(30/365))`.
- **Constraint**: Filter uses **1.0x Standard Deviation** (Strict) to match the visual header display exactly.
- **Implementation**:
    - **Header**: Displays active range (e.g., `Range: 6715-7190`).
    - **Logic**: `spx_profiler_nexus.py` (Line 588) hard-rejects any trade (`stk < lower` or `stk > upper`) before processing.

#### 5. SPY Profiler IV Filtering (Jan 26, 2026)
- **Feature**: Ported the **30-Day Implied Move Filtering** to the SPY Profiler.
- **Formula**: `Range = Spot ± (Spot * IV_30d * sqrt(30/365))`.
- **Constraint**: Filter uses **1.0x Standard Deviation** (Strict).
- **Implementation**:
    - **Header**: Displays active range (matched to SPX logic).
    - **Logic**: `spy_profiler_nexus_v2.py` filters early in the `process_data` loop.

### J. Critical Logic Repairs (Jan 26, 2026 - Part 5)

#### 1. SPX Persistence Bug (Zero Data)
- **Symptom**: `nexus_spx_profile.json` intermittently displayed zeros for Spot Gamma/Max Pain despite valid debug logs.
- **Root Cause**: A race condition where `spx_profiler_nexus.py` would calculate fresh data, write it to disk, and immediately **overwrite its own memory** by loading a potentially stale/empty file (`nexus_gex_static.json`) from disk.
- **Fix**: Modified loader logic to **ONLY** load from disk if the in-memory cache is empty.
- **Protocol**: Prioritize **Live Memory** > **Disk Snapshot**.

#### 2. Auditor Money Flow Inflation
- **Symptom**: Discord Money Flow reported inflated values (e.g. -$1.3B) with mixed units.
- **Root Cause**: Old code merged expired V1 data and added "Delta Share Equivalent" to "Premium Dollars".
- **Fix**: Purged V1 logic. Auditor now sums **Net Premium ($)** directly from V3 lists.

#### 3. TS NEXUS Headless Revert
- **Symptom**: `system_watchdog.py` kept restarting `ts_nexus.py` or launching the TUI version.
- **Root Cause**: Hardcoded legacy command string in Watchdog `WATCH_LIST`.
- **Fix**: Updated `WATCH_LIST` to explicitly include `--headless` flag.

### K. Dashboard Stabilization (Jan 27, 2026 - Critical)

#### 1. Greeks Monitor Starvation (Dedicated Thread)
- **Problem**: Greek metrics would update for ~60s then freeze permanently.
- **Root Cause**: The `monitor_greeks` loop used the default `asyncio` loop executor for file I/O. Other heavy dashboard tasks (subscribers, UI renders) starved the thread pool, causing the file reader to hang indefinitely.
- **Fix**: Implemented **Dedicated Thread Pool** (`ThreadPoolExecutor(max_workers=1)`) exclusively for the Greek monitor.
- **Outcome**: Loop beats reliably at 1Hz, immune to main thread load.

#### 2. Position Table Flickering (Layout Shift)
- **Problem**: The Position Table would flash empty every few seconds.
- **Root Cause**:
    1. **Layout Shift**: `group_positions` logic caused key instability (flip-flopping keys).
    2. **Zero-Qty Noise**: Server transitions sent frames with `Quantity: 0`. The code treated these as "Valid Data" (passing debounce) but then filtered them out as "Empty", resulting in an empty table render.
- **Fix**:
    - **Diff-Based Update**: Replaced `table.clear()` with granular `add_row` / `remove_row` / `update_cell` (checking equality) logic.
    - **Pre-Debounce Filtering**: Explicitly filters zero-quantity positions *before* the debounce check. Frames with only zero-qty rows are now safely treated as "Empty" and ignored (debounced) for 3 seconds.

#### 3. Anti-Flashing Persistence (State Retention)
- **Problem**: Greeks (Gamma/Delta) headers flashing to `0.00` during high I/O load.
- **Root Cause**: `nexus_greeks.py` file reads occasionally timed out (1.5s limit). The Dashboard blindly defaulted to `0.00` on any exception.
- **Fix**: Implemented **State Retention System**:
    - **Memory**: Dashboard now retains `last_known_valid_value` if a read fails.
    - **Indicator**: Values dim to **Grey** if stale (>10s) but do *not* flash to zero.
    - **Version**: Validated `trader_dashboard_v3.py` is the canonical script (Window 14).

### L. Flip/Pin Data Re-Implementation (Jan 27, 2026)

#### 1. SPX/SPY Structural Framework Alignment
- **Objective**: Ensure Auditor displays **Gamma Flip** and **Pin (POC)** for both 0DTE and Next Expiry (Friday).
- **Updates**:
    - **SPX**: Removed broken try/except blocks in `spx_profiler_nexus.py` causing sentiment failures. Auditor framework updated to extract `gex_flip_point` and `volume_poc_strike` explicitly.
    - **SPY**: 
        - Updated `gemini_market_auditor.py` to extract `d1` (Next Expiry) Flip/Pin data.
        - **Critical Fix**: Updated `viewer_dash_nexus.py` (Helper `analyze_gamma_exposure`) to injected explicit `date` field into GEX summaries. This resolved the "Ghost Expiry" issue where Auditor couldn't identify the Friday expiry row.
    - **Result**: Discord Alert now correctly displays Flip/Pin for SPY Next Expiry.

#### 2. Viewer Dashboard GEX Table
- **Feature**: Added/Verified columns "Flip Pt" and "Pin (S)" (Support Pin) in the Weekly GEX Table (Window 15).
- **Source**: Directly linked to `analyze_gamma_exposure` logic matching the Auditor's data source.

## 9. Troubleshooting & Recovery

| Symptom | Diagnosis | Recovery Action |
| :--- | :--- | :--- |
| **Dashboard Flashing Zeros** | Bridge Semantic Fail / Read Timeout | `tmux respawn-window -k -t nexus:BRIDGE` (or check V3 Patch) |
| **SPX Profiler Stuck ("N/A")** | Zombie Process (PID Mismatch) | `pkill -f spx_profiler` then let Watchdog restart |
| **Sheets Bridge Not Updating** | Google API / Guardian Kill | Check `sheets_bridge.log` timestamp. Restart Window 23. |
| **TS_NEXUS High Memory** | TUI Memory Leak | Ensure running with `--headless` flag. |
| **Dashboard UI Freezing** | Main Thread Blocking / Starvation | Check logs for "Tick". Ensure Dedicated Executor is active. |
| **Position Table Flickering** | Zero-Qty Data / Key Instability | Check "Empty Payload" logs. Ensure Zero-Qty Filter is active. |

### M. Critical Logic Repairs (Jan 29, 2026)

#### 1. Sweeps V3 API Schema & Filter Patch
- **Problem**: `nexus_sweeps_v3.py` rejected all trades due to API Schema change (`ticker` -> `underlying_symbol`) and effectively zeroed out IV data.
- **Root Cause**: Keys mismatched in `process_row`.
- **Resolution**:
    - **Schema Patch**: Updated key access to support both `ticker` and `underlying_symbol`.
    - **Filter Logic**: Capped DTE at **50 Days** (User Request).
    - **Header Visibility**: Compacted IV Range display (`[SPX:6673-7207]`) to prevent layout clipping.
    - **Thresholds**: Restored Production Filters ($250k+).

#### 2. Trader Dashboard Single Leg Positions
- **Problem**: Single leg options missing from Positions Table (Window 14).
- **Root Cause**: `sub_acct` loop calculated row values for non-spread positions but lacked the `tbl.add_row()` instruction.
- **Resolution**: Restored table update logic. Single leg positions now display immediately.

### N. VRP Tool Integration (Jan 31, 2026)

**Objective**: Calculate and display the **Volatility Risk Premium (VRP)** Spread (`IV30 - HV30`) to identify when risk is overpriced (Sell Premium) or underpriced (Buy Premium).

#### 1. Architecture & Data Flow
- **Source**: `spy_profiler_nexus_v2.py` (Window 6).
- **API Optimization**: The VRP data point is **piggybacked** onto the existing ORATS `live/summaries` call by adding parameters to the `fields` list.
- **Persistence**: Writes to `nexus_vrp_context.json` (New Artifact).
  - Schema: `{"ticker": "SPY", "iv30": 0.12, "hv30": 0.10, "vrp_spread": 0.02, "signal": "SELL_PREMIUM"}`.
- **Consumption**:
  - **Discord**: `gemini_market_auditor.py` reads JSON to inject "⚡ Volatility Risk Premium" field.
  - **Sheets**: `nexus_sheets_bridge.py` reads JSON to append Column W (`VRP Spread`).

#### 2. Critical ORATS Mapping (The "hv30" Trap)
- **Problem**: The ORATS API `live/summaries` endpoint does **NOT** return a field named `hv30`, causing initial implementation failures (KeyError/Null).
- **Discovery**: Verification debug scripts revealed the correct field for 30-Day Historical Volatility is **`rVol30`** (Realized Volatility).
- **Implementation**:
  - **Request**: `fields=...,iv30d,rVol30,...`
  - **Mapping**: `hv30 = float(data.get('rVol30') or 0)`
  - **Result**: Zero cost data addition (No extra API calls).

#### 3. Stability Note
- **Deploy Protocol**: Requires restarting **SPY Profiler**, **Auditor**, and **Sheets Bridge** to propagate changes.
- **Fail-Safe**: If `nexus_vrp_context.json` is missing/stale, consumers default to "N/A" rather than crashing.
