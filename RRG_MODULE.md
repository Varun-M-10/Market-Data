# RRG Analytics Module

## Overview

The RRG (Relative Rotation Graph) analytics module tracks the relative performance of option strikes against a benchmark (e.g., Nifty 50 Spot). This is a **custom prototype implementation** based on the formulas provided by the user. It has **not** been verified against the standard JdK (Julius de Kempenaer) RRG methodology.

## Installation

The RRG module requires the following dependencies (already included in `requirements.txt`):
- pandas
- numpy
- matplotlib

## Architecture

### Components

1. **RRGConfig** (`src/rrg/models.py`)
   - Configuration for RRG calculations
   - Parameters: benchmark symbol, timeframe, rolling window, momentum period, strikes, expiry

2. **RRGCalculator** (`src/rrg/calculator.py`)
   - Core calculation engine
   - Processes market data and calculates RS, RS-Ratio, RS-Momentum
   - Maintains history for rolling statistics
   - Determines quadrant classification

3. **RRGVisualizer** (`src/rrg/visualization.py`)
   - Creates matplotlib charts
   - Renders four-quadrant background
   - Plots data points with color-coded quadrants
   - Generates quadrant summaries

4. **RRGSnapshot / RRGDataPoint** (`src/rrg/models.py`)
   - Data structures for RRG output
   - Serializable to dict for API transmission

## Formulas

### Relative Strength (RS)
```
RS = (Option Premium / Benchmark Spot) × 100
```

### RS-Ratio
```
z_score = (current_RS - rolling_mean_RS) / rolling_std_RS
RS-Ratio = 100 + z_score × 10
```

### RS-Momentum
```
ROC = percentage_change(RS-Ratio, momentum_period)
z_score = (current_ROC - rolling_mean_ROC) / rolling_std_ROC
RS-Momentum = 100 + z_score × 10
```

### Quadrant Classification
- **Leading**: RS-Ratio > 100, RS-Momentum > 100
- **Weakening**: RS-Ratio > 100, RS-Momentum < 100
- **Lagging**: RS-Ratio < 100, RS-Momentum < 100
- **Improving**: RS-Ratio < 100, RS-Momentum > 100

## Configuration

Add to `config.yaml`:

```yaml
enable_rrg: true
rrg_timeframe: "1min"  # 1min, 5min, 15min, daily
rrg_rolling_window: 14  # Number of periods for rolling statistics
rrg_momentum_period: 1  # Period for rate of change
rrg_strikes: null  # null = all strikes, or [25000.0, 25100.0]
rrg_expiry: null  # null = current expiry
```

## Integration with Market Engine

The RRG calculator is integrated into `MarketEngine` in `src/engine.py`:

1. When `enable_rrg: true`, the engine initializes an `RRGCalculator`
2. On each tick with option chain data, the calculator is updated
3. RRG calculations are performed and stored in the snapshot
4. RRG data is serialized and included in WebSocket/API responses

## Usage

### With Market Engine

```python
from src.config import load_config
from src.engine import MarketEngine

cfg = load_config()
cfg["enable_rrg"] = True
cfg["rrg_timeframe"] = "1min"
cfg["rrg_rolling_window"] = 14

engine = MarketEngine(cfg)
engine.start()
```

### Standalone Calculation

```python
from src.rrg import RRGCalculator, RRGConfig
from src.models import PriceTick, OptionChainSnapshot

config = RRGConfig(
    benchmark_symbol="NIFTY",
    timeframe="1min",
    rolling_window=14,
    momentum_period=1,
)

calculator = RRGCalculator(config)

# Update with market data
calculator.update(tick, option_chain)

# Calculate RRG
snapshot = calculator.calculate_rrg()
```

### Visualization

```python
from src.rrg.visualization import RRGVisualizer

visualizer = RRGVisualizer()
fig = visualizer.create_rrg_chart(snapshot, title="My RRG Chart")
fig.show()
```

Or from raw data:

```python
from src.rrg.visualization import create_rrg_chart_from_data

fig = create_rrg_chart_from_data(
    rs_ratios=[105.2, 98.5, 92.3],
    rs_momentums=[102.5, 104.2, 96.8],
    labels=["24500 CE", "24100 PE", "24900 CE"],
    title="Custom RRG Chart"
)
fig.show()
```

## Testing

Run RRG-specific tests:

```bash
# Core calculation tests
pytest tests/test_rrg.py -v

# Integration with market data
pytest tests/test_rrg_integration.py -v

# Visualization tests
pytest tests/test_rrg_visualization.py -v

# All RRG tests
pytest tests/test_rrg*.py -v
```

## Test Coverage

- Initialization and configuration
- Market data updates
- RS, RS-Ratio, RS-Momentum calculations
- Quadrant determination
- Timeframe configuration
- Insufficient history handling
- Serialization
- Strike filtering
- Integration with real market data stream
- Visualization and quadrant rendering

## Important Notes

1. **Custom Implementation**: This is not the standard JdK RRG methodology. The formulas are based on a prototype provided by the user. The mathematical semantics should be validated with the client before production use.

2. **Timeframe Semantics**: The timeframe parameter (e.g., "1min") determines how data is resampled for rolling statistics. A rolling window of 14 with a 1-minute timeframe means 14 minutes of data, not 14 days.

3. **Data Requirements**: RRG calculations require sufficient history. With a rolling window of 14, at least 14 data points are needed before RS-Ratio and RS-Momentum can be calculated.

4. **Strike Filtering**: The calculator can be configured to track specific strikes or all strikes. Filtering is done at update time.

5. **Performance**: RRG calculations are performed on each tick. For high-frequency data, consider increasing the update frequency or using a larger rolling window.

## API Response Format

When RRG is enabled, the snapshot API includes:

```json
{
  "rrg": {
    "benchmark_symbol": "NIFTY",
    "benchmark_ltp": 25000.0,
    "timeframe": "1min",
    "timestamp": "2026-08-24T14:30:00",
    "data_points": [
      {
        "strike": 25000.0,
        "option_type": "CE",
        "rs": 0.8,
        "rs_ratio": 105.2,
        "rs_momentum": 102.5,
        "quadrant": "LEADING",
        "timestamp": "2026-08-24T14:30:00",
        "option_ltp": 200.0,
        "benchmark_ltp": 25000.0
      }
    ]
  }
}
```

## Files

- `src/rrg/__init__.py` - Package initialization
- `src/rrg/models.py` - Data models and configuration
- `src/rrg/calculator.py` - Calculation engine
- `src/rrg/visualization.py` - Chart generation
- `tests/test_rrg.py` - Core calculation tests
- `tests/test_rrg_integration.py` - Integration tests
- `tests/test_rrg_visualization.py` - Visualization tests

## Version History

- **v1.0** (2026-08-24): Initial implementation
  - Custom RRG formulas based on prototype
  - Integration with market data stream
  - Visualization with matplotlib
  - Comprehensive test suite (17 tests, all passing)
