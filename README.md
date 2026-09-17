# Live Market Data System

Continuously tracks live market/option price data and automatically converts the price stream into **1-minute, 5-minute, and 15-minute OHLC candles**, with **ATM strike identification** from the option chain.

## Features

- **Live price polling** from NSE India (or simulated mock data for development)
- **Option chain parsing** — Calls, Puts, strike prices, Greeks (Delta), OI, volume
- **Delta-based ATM strike detection** (default) — strike whose Call/Put Delta is closest to a configurable threshold (default 0.50), with automatic fallback to nearest-to-spot when a chain carries no Greeks; the nearest-to-spot strike is always attached for on-screen comparison
- **Price Calculator** — modular component for derived price calculations (currently mock: Combined Value = ATM Call LTP + ATM Put LTP)
- **Real-time candle building** — OHLC updates on every tick; candles finalize at interval boundaries
- **Structured JSON logging** — logs price ticks, completed candles, ATM updates, and calculated prices
- **Data-quality & reliability indicators** — source, connection status, tick count, last-tick age, stale-data detection, duplicate/out-of-order tick rejection, and market-session status (OPEN/PRE_OPEN/CLOSED/WEEKEND)
- **Persistence (SQLite)** — completed candles and option chain/ATM snapshots optionally written to disk, readable back via `/api/history/*`
- **Live terminal dashboard** — spot price, ATM panel, active and completed candles
- **Web dashboard** — browser UI with candlestick chart, option chain, and WebSocket live updates
- **Environment variable configuration** — flexible configuration via `.env` file
- **Comprehensive test suite** — tests for ATM selection, candle calculation, invalid data, persistence, data quality, and end-to-end flows
- **RRG Analytics** — Relative Rotation Graph tracking for option strikes against benchmark (custom implementation)

## Quick Start

```bash
# 1. Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure (optional)
# Copy .env.example to .env and customize
cp .env.example .env

# 4. Run the web dashboard (recommended)
python -m src.api
# Open http://127.0.0.1:8000

# 5. Run terminal dashboard with simulated data
python -m src.main

# 6. Run with live NSE data (market hours, network required)
python -m src.main --source nse --underlying NIFTY

# 7. Run with RRG analytics enabled
# Set enable_rrg: true in config.yaml
python -m src.main

# 8. Run tests
pytest tests/
```

Press `Ctrl+C` to stop.

## Configuration

Configuration can be done via `config.yaml` or environment variables (`.env` file).

### config.yaml

| Key | Description | Default |
|-----|-------------|---------|
| `underlying` | Index symbol (NIFTY, BANKNIFTY, FINNIFTY) | `NIFTY` |
| `data_source` | `mock` or `nse` | `mock` |
| `poll_interval_seconds` | Seconds between price fetches | `5` |
| `candle_intervals` | Minute intervals for OHLC | `[1, 5, 15]` |
| `price_calculator` | Calculation method (`mock`, `black_scholes`, `delta_neutral`) | `mock` |
| `log_level` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) | `INFO` |
| `enable_rrg` | Enable RRG analytics | `false` |
| `rrg_timeframe` | RRG calculation timeframe | `1min` |
| `rrg_rolling_window` | Rolling window for RRG statistics | `14` |
| `rrg_momentum_period` | Momentum/ROC period for RRG | `1` |
| `rrg_strikes` | Specific strikes to track (null = all) | `null` |
| `rrg_expiry` | Expiry for RRG analysis (null = current) | `null` |

### Environment Variables (.env)

| Variable | Description | Default |
|----------|-------------|---------|
| `UNDERLYING` | Index symbol | `NIFTY` |
| `DATA_SOURCE` | Data source | `mock` |
| `POLL_INTERVAL_SECONDS` | Poll interval | `5` |
| `PRICE_CALCULATOR` | Calculator method | `mock` |
| `CANDLE_INTERVALS` | Comma-separated intervals | `1,5,15` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `ENABLE_RRG` | Enable RRG analytics | `false` |
| `RRG_TIMEFRAME` | RRG calculation timeframe | `1min` |
| `RRG_ROLLING_WINDOW` | Rolling window for RRG statistics | `14` |
| `RRG_MOMENTUM_PERIOD` | Momentum/ROC period for RRG | `1` |
| `RRG_STRIKES` | Specific strikes to track (null = all) | `null` |
| `RRG_EXPIRY` | Expiry for RRG analysis (null = current) | `null` |

CLI overrides: `--source`, `--underlying`, `--poll`

## Architecture

```
Market Data Provider
           │
           ▼
┌──────────────────┐     ┌─────────────────────┐
│  Data Source     │────▶│  Option Chain       │
│  (NSE / Mock)    │     │  → ATM Strike       │
└────────┬─────────┘     └─────────────────────┘
         │
         ▼
┌──────────────────┐
│ ATM Strike       │
│ Resolver         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Price Calculator │──▶ Derived Prices
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Candle Aggregator│──▶ 1m / 5m / 15m OHLC
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Structured Logger│──▶ JSON Output
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ Console / Web UI │
└──────────────────┘
```

## Pipeline Components

### MarketDataProvider
Abstract base class for market data sources. Implementations:
- `MockDataSource` — Simulated market data for development
- `NSEDataSource` — Live NSE India option chain data

### ATM Strike Selection
`find_atm_strike_delta()` (`src/option_chain/atm.py`) is the default (`atm_method: delta` in config): it selects the strike whose Call Delta and/or Put Delta is closest to `delta_threshold` (default 0.50, configurable via `config.yaml` or `DELTA_THRESHOLD` env var). It automatically falls back to `find_atm_strike()` — price proximity, minimum `|strike - spot|` — if the chain carries no Greeks (e.g. a provider that doesn't supply delta) or if `atm_method: price` is set explicitly. Either way, the nearest-to-spot strike is attached to the result (`price_based_strike`) for on-screen comparison, and both functions coexist so callers/tests can use either directly.

### PriceCalculator
Modular component for calculating derived prices from ATM data. Implementations:
- `MockPriceCalculator` — Temporary mock calculation: **Combined Value = ATM Call LTP + ATM Put LTP** (returned as both `combined_value` and `straddle_premium` for compatibility). The formula lives in one isolated method (`_combined_value`) so it can be swapped without touching callers.
- `BlackScholesCalculator` — Placeholder for Black-Scholes implementation
- `DeltaNeutralCalculator` — Placeholder for Delta-neutral strategies

### CandleAggregator
Converts price ticks into OHLC candles at multiple intervals (1m, 5m, 15m). Handles real-time candle building and completion at interval boundaries.

### StructuredLogger
Outputs structured JSON logs for:
- Price ticks
- Completed candles
- ATM updates
- Calculated prices
- System events and errors

### RRG Calculator (Relative Rotation Graph)
Tracks relative performance of option strikes against a benchmark. Features:
- Custom RRG implementation based on prototype formulas (not verified JdK methodology)
- Calculates RS (Relative Strength), RS-Ratio, and RS-Momentum
- Configurable timeframe, rolling window, and momentum period
- Quadrant classification (Leading, Weakening, Lagging, Improving)
- Visualization with matplotlib charts
- Integration with real market data stream

Note: This is a custom prototype implementation. Mathematical semantics should be validated with the client before production use.

## Paper Trading (Simulation Only)

A **simulation-only** position engine rides the same tick pipeline (ticks → option chain → ATM → candles) to track hypothetical CE/PE trades. It never places a real Dhan/broker order — every position and trade-history row is flagged `"simulated": true`.

- Open a long CE/PE position at a chosen (or ATM-default) strike and quantity.
- Every tick marks open positions to market and computes P&L (₹ and %).
- Configurable **Take Profit %** and **Stop Loss %** (temporary defaults: TP=10%, SL=5%) trigger an automatic simulated exit the moment P&L crosses the threshold — tagged `TAKE_PROFIT` or `STOP_LOSS`. Manual exits are tagged `MANUAL`.
- Config can be set in `config.yaml` (`paper_trading:`), via env vars (`PAPER_TAKE_PROFIT_PERCENT`, `PAPER_STOP_LOSS_PERCENT`, `PAPER_DEFAULT_QUANTITY`), or live via the API/UI.

| Endpoint | Description |
|----------|-------------|
| `GET /api/paper/state` | Open positions, trade history, current TP/SL config |
| `POST /api/paper/open` | Open a simulated position `{option_type, strike?, quantity}` |
| `POST /api/paper/close/{id}` | Manually exit a simulated position |
| `POST /api/paper/config` | Update `{take_profit_percent?, stop_loss_percent?}` |

Implementation: `src/paper_trading.py` (engine + tests in `tests/test_paper_trading.py`), wired into `MarketEngine._tick_worker` in `src/engine.py`.

## Data Quality & Persistence

- **`data_quality` block** in every snapshot (`/api/snapshot`, WebSocket): `source`, `connection_status`, `tick_count`, `last_tick_time`, `last_tick_age_seconds`, `is_stale`, `stale_threshold_seconds`, `persistence_enabled`. `is_stale` flips true whenever no tick has arrived within `stale_threshold_seconds` (config: `stale_threshold_seconds`, default `max(10, poll_interval_seconds * 3)`), independent of whatever the connection badge reports — a source can claim "connected" while it has silently stopped sending ticks.
- The web dashboard shows a pulsing **STALE** badge next to the connection status, plus "Last tick: Ns ago" and a Storage indicator.
- **Persistence** (`persistence:` in `config.yaml`, stdlib `sqlite3` — no new dependency) writes every completed candle and a throttled option-chain/ATM snapshot to `data/market_data.db`. It is purely additive: candle, ATM, and paper-trading logic have no dependency on it, so it can be disabled (`persistence.enabled: false`) without touching pipeline behavior.
- Read back via `GET /api/history/candles?interval=1&limit=200` and `GET /api/history/option-chain?limit=200`.

## Web Frontend

| URL | Description |
|-----|-------------|
| `http://127.0.0.1:8000` | Dashboard (spot, ATM, chart, option chain) |
| `http://127.0.0.1:8000/api/snapshot` | Current state JSON |
| `http://127.0.0.1:8000/api/config` | Current configuration |
| `ws://127.0.0.1:8000/ws` | Live WebSocket stream |

The dashboard includes:
- Real-time underlying LTP with change indicator, source, and connection status
- ATM strike, Call, Put, and straddle premium cards
- Candlestick chart with 1m / 5m / 15m interval switcher
- Option chain table (strikes around ATM highlighted)
- Paper trading panel — open/close simulated CE/PE positions, live P&L, TP/SL config, trade history with clear TAKE PROFIT / STOP LOSS / MANUAL exit badges
- A persistent "SIMULATED MARKET DATA" banner whenever running on mock data
- Toast notifications when candles close and when a paper position auto-exits on TP/SL

Change `data_source` in `config.yaml` to `nse` before starting the web server for live NSE data.

## Dashboard v2 — Trading Terminal Upgrade

The web dashboard (`frontend/`) is a professional dark trading-terminal UI organized into tabs, all riding the existing pipeline (no rebuild of candles/ATM/CE+PE/TP-SL — purely additive):

| Tab | Contents |
|-----|----------|
| **Overview** | Market Overview strip (LTP, change, ATM, CE, PE, CE+PE, tick count, timestamp), candlestick chart (1m/5m/15m, zoom, crosshair OHLC tooltip), Option Chain (Strike/CE LTP/CE Δ/PE Δ/PE LTP/**CE+PE**, ATM highlighted), Paper Trading (position, entry, current, qty, TP, SL, **distance to TP/SL**, P&L ₹/%, exit reason) and Trade History with **win rate, total P&L, average win/loss, max drawdown** |
| **RRG** | Relative Rotation Graph as its own tab — quadrant scatter plot (inline SVG) + per-strike RS/RS-Ratio/RS-Momentum table, reusing the existing `RRGCalculator` (custom prototype methodology, not JdK-verified — labeled as such in the UI) |
| **Data Quality** | Connection, source, tick count/rate, last tick, stale-data warning, market session, duplicate/rejected ticks, Option Chain status, persistence |
| **System Logs** | Recent structured log entries (in-memory ring buffer, `GET /api/logs`), level filter, auto-follow |
| **Settings** | Data source (including Replay/Test Mode), expiry (read-only), ATM method + Delta tolerance, Take Profit / Stop Loss, candle price basis |

### Deterministic MOCK Replay/Test Mode

`src/data_sources/replay.py` (`ReplayDataSource`) plays back a **named, hand-authored, fully deterministic** tick sequence — `trend_up`, `trend_down`, `choppy_range`, `gap_and_reversal` — instead of the process-global-random `MockDataSource`. Same sequence + same seed always reproduces the same path, useful for demos and UI testing. Controllable from the Settings tab (or `POST /api/settings/data-source`) with an optional playback **speed** multiplier (0.5×–10×); switching sources live does not lose candle history, open paper positions, or trade history. Still 100% simulated — no real broker connection, same as `mock`.

### Candle Price Basis

`candle_price_basis` (config.yaml / `CANDLE_PRICE_BASIS` env / Settings tab) chooses which price series feeds the candle aggregator and chart: `underlying` (spot, default) or `combined_value` (ATM CE+PE). Pure display choice — the aggregator itself, and the CE+PE formula, are untouched.

### New API Endpoints

| Endpoint | Description |
|----------|--------------|
| `GET /api/settings` | Current data source, ATM method/threshold, TP/SL, candle basis, replay config |
| `POST /api/settings/atm` | Update `{atm_method?, delta_threshold?}` |
| `POST /api/settings/candle-basis` | Update `{candle_price_basis}` |
| `POST /api/settings/data-source` | Switch `{data_source, sequence?, speed?}` (e.g. into Replay/Test Mode) — no real orders |
| `GET /api/logs?limit=200&level=` | Recent structured log entries, newest first |

## Testing

The system includes a comprehensive test suite:

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/test_atm_selection.py

# Run with verbose output
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Test Coverage

- **ATM Selection**: Tests for exact matches, closest strikes, tie-breakers, empty chains
- **Candle Calculation**: Tests for OHLC updates, interval boundaries, multiple intervals
- **Price Calculator**: Tests for mock calculations, error handling, factory methods
- **Invalid Data**: Tests for missing fields, zero/negative prices, invalid timestamps
- **End-to-End**: Tests for complete pipeline with mock data, multiple intervals, error recovery
- **RRG Analytics**: Tests for RRG calculation, RS/RS-Ratio/RS-Momentum formulas, quadrant determination, timeframe configuration, synthetic data, integration with market data stream, visualization
- **Paper Trading**: Tests for TP/SL auto-exit thresholds (default and configurable), manual close, P&L calculation, missing-strike handling, state serialization
- **Data Quality**: Tests for staleness computation (fresh/at-threshold/past-threshold/no-tick-yet), default threshold derivation, end-to-end snapshot exposure
- **Persistence**: Tests for candle upsert/read-back, interval isolation, option-chain/ATM snapshot storage, durability across reopen, end-to-end engine integration
- **Dashboard v2** (`test_dashboard_upgrade.py`): trade stats (win rate, avg win/loss, max drawdown), TP/SL price levels & distance, option-chain per-row CE+PE, candle aggregator fed an alternate price basis, deterministic Replay/Test Mode (reproducibility, looping, fallback, speed clamping)

## ATM & Combined Value Logic

- **ATM strike** (default) = strike whose Call Delta and/or Put Delta is closest to `delta_threshold` (default 0.50); falls back to minimum `|strike − spot|` if the chain has no Greeks, or if `atm_method: price` is configured
- **Nearest-to-spot strike** = minimum `|strike − spot|`, always computed and attached for comparison regardless of which method is active
- **Combined Value (ATM CE + PE)** = ATM Call LTP + ATM Put LTP
- **Call/Put Ratio** = ATM Call LTP / ATM Put LTP
- **Synthetic Price** = ATM Call LTP - ATM Put LTP

Note: The Delta-based ATM method and the Combined Value formula are both isolated/configurable — the exact business formula for the CE+PE calculation is still pending final client confirmation (currently simple addition). See `CLIENT_CLARIFICATIONS.md` for details.

## Reliability

- **Stale-data detection**: `data_quality.is_stale` flips true when no tick has arrived within `stale_threshold_seconds` (config, default `max(10, poll_interval_seconds*3)`) — independent of the connection badge.
- **Timestamp validation**: every tick is checked (`src/tick_validation.py`) before it reaches the candle aggregator — a missing timestamp or non-positive price is rejected outright.
- **Duplicate tick handling**: a tick with the exact same timestamp as the last accepted one is counted (`data_quality.duplicate_tick_count`) and dropped, not re-processed.
- **Out-of-order tick handling**: a tick timestamped earlier than the last accepted one is counted (`data_quality.rejected_tick_count`) and dropped, so it can't corrupt OHLC ordering.
- **Market-session handling**: `data_quality.market_session` reports `OPEN` / `PRE_OPEN` / `CLOSED` / `WEEKEND` based on `session_start`/`session_end`/`timezone` config. Informational only — MOCK ticks are not gated by session hours (dev/demo convenience).

## Extending

- **Broker WebSocket**: Implement `DataSource` in `src/data_sources/base.py` for tick-by-tick feeds (Zerodha Kite, Angel One, etc.)
- **Custom Price Calculator**: Implement `PriceCalculator` interface for the confirmed business formula
- **Persistence**: `src/persistence.py` already writes completed candles and option chain/ATM snapshots to SQLite; swap in a different backend behind the same two methods if needed
- **Admin/Editor Table**: Interface marked as TODO pending client clarification on purpose and schema

## Client Clarifications

This system is a working implementation of the core pipeline, but certain business requirements need client clarification before production deployment:

1. **Exact Call/Put calculation formula** — Currently using mock calculation (Combined Value = Call LTP + Put LTP)
2. **Editor/Admin table purpose and schema** — Interface exists but not implemented
3. **Exact meaning of "print"** — Currently using structured JSON logging
4. **Final market-data provider** — Currently supports NSE, Dhan (pending Data API subscription), and mock data
5. **Expiry-selection rule** — Currently uses nearest expiry
6. **Delta threshold tuning** — ATM selection now uses Delta ≈ `delta_threshold` (default 0.50); the exact target value is configurable but not yet client-confirmed

See `CLIENT_CLARIFICATIONS.md` for detailed information and architecture readiness notes.

## Notes

- NSE API may block requests outside market hours or without valid session cookies; use `mock` for off-hours development.
- Poll-based fetching treats each snapshot as a tick; true sub-second candles require a WebSocket data source.
- The system is not production-ready until unresolved client requirements are implemented and live-data reliability is verified.
- Environment variables override config.yaml settings for flexible deployment.

## License

This is a development implementation for client demonstration and testing purposes.
