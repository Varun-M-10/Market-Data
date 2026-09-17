# Client Clarifications Needed

This document lists the unresolved requirements that need client clarification before the system can be considered production-ready.

## 1. Call/Put Price Calculation Formula

**Current Status:** Using temporary mock calculation (Call + Put = Straddle Premium)

**Question:** What is the exact business formula for calculating the Call/Put prices? The requirements specify creating a separate `PriceCalculator` component, but the exact formula is not confirmed.

**Options for consideration:**
- Black-Scholes model
- Binomial tree model
- Monte Carlo simulation
- Proprietary formula
- External API calculation

**Impact:** This is critical for the core business logic and affects all downstream calculations.

---

## 2. Editor/Admin Table Purpose and Schema

**Current Status:** Unresolved interface marked as TODO

**Question:** What is the purpose of the "editor table/admin column" mentioned in the requirements? What schema and business logic should it implement?

**Possible interpretations:**
- Manual override/adjustment of ATM strike selection
- Configuration of calculation parameters
- Manual entry of option prices
- Audit/tracking of ATM selections
- Risk management parameters
- Something else entirely

**Impact:** Cannot implement without understanding the business purpose and data structure.

---

## 3. Exact Meaning of "Print"

**Current Status:** Currently logs to console in structured JSON format

**Question:** What is the exact requirement for "print/log incoming prices and completed candles"?

**Options:**
- Console output (current implementation)
- File logging
- Database storage
- API endpoint
- WebSocket broadcast
- Combination of above

**Format preferences:**
- JSON (current)
- CSV
- Human-readable text
- Custom format

**Impact:** Affects logging infrastructure and output format.

---

## 4. Final Market-Data Provider/API

**Current Status:** Supports both NSE India (live) and Mock (simulated) data sources

**Question:** Which market-data provider should be used in production?

**Current options:**
- NSE India (currently implemented)
- Zerodha Kite
- Angel One
- Upstox
- 5Paisa
- Other broker API
- Proprietary data feed

**Considerations:**
- API rate limits
- Authentication requirements
- Data quality and latency
- Cost implications
- Reliability during market hours

**Impact:** Requires integration with specific broker API and authentication handling.

---

## 5. Expiry-Selection Rule

**Current Status:** Currently selects nearest expiry automatically

**Question:** What is the business rule for selecting which option chain expiry to use?

**Options:**
- Nearest expiry (current implementation)
- Weekly expiry
- Monthly expiry
- Specific day of week
- Custom offset from current date
- Manual selection via configuration

**Impact:** Affects which option chain data is used for ATM selection and calculations.

---

## 6. ATM Selection Method — Delta Threshold Tuning

**Current Status:** ✅ Implemented. Delta-based selection (`find_atm_strike_delta()`) is now the default (`atm_method: delta`): the strike whose Call Delta and/or Put Delta is closest to `delta_threshold` (default **0.50**) is used. It automatically falls back to price proximity (`min(|strike - spot|)`) if a chain carries no Greeks, or if `atm_method: price` is configured explicitly. The nearest-to-spot strike is always attached to the result for on-screen comparison.

**Remaining question:** Is `delta_threshold = 0.50` the correct target, or should it be a different value (or vary by product/expiry)? The threshold is fully configurable (`config.yaml: delta_threshold`, or `DELTA_THRESHOLD` env var) so this is a tuning input, not a code change, once confirmed.

**Impact:** Low — the mechanism is built and tested; only the exact threshold value is open.

---

## 7. RRG Mathematical Semantics

**Current Status:** Custom RRG implementation based on prototype formulas

**Question:** Should the RRG implementation use standard JdK (Julius de Kempenaer) methodology, or is the custom prototype formula acceptable?

**Current implementation:**
- RS = (Option Premium / Benchmark Spot) × 100
- RS-Ratio = 100 + z-score(RS) × 10
- RS-Momentum = 100 + z-score(ROC(RS-Ratio)) × 10

**Note:** This is explicitly labeled as a custom/prototype implementation. The actual JdK RRG methodology has not been verified.

**Options:**
- Validate and use the current custom formulas
- Implement standard JdK RRG methodology
- Client-provided specific formulas
- Use external RRG calculation library

**Impact:** Affects RRG calculation accuracy and quadrant classification. The current implementation may not match standard RRG behavior.

---

## Implementation Notes

### Current Temporary Solutions

1. **PriceCalculator:** Currently using simple addition (Call + Put = Combined Value / Straddle Premium)
2. **Editor Table:** Interface exists but not implemented
3. **Logging:** Console JSON output for prices and candles
4. **ATM Method:** ✅ Delta-based (Call/Put Delta ≈ `delta_threshold`, default 0.50) is now the default, with automatic fallback to price-proximity; exact threshold value still open (see item 6 above)
5. **Expiry:** Automatic nearest expiry selection

### Architecture Readiness

The system architecture is designed to accommodate these clarifications:

- **PriceCalculator:** Isolated component ready for business formula
- **ATMStrikeResolver:** Modular design supports multiple ATM selection methods
- **MarketDataProvider:** Abstract base class allows easy provider switching
- **Logging:** Structured output can be redirected to files, databases, or APIs
- **Configuration:** Environment variable support for runtime configuration

### Next Steps

Once client clarifications are received:

1. Implement final PriceCalculator formula
2. Design and implement editor/admin table
3. Configure logging based on output requirements
4. Integrate with final market-data provider
5. Implement expiry-selection business rules
6. Confirm the correct `delta_threshold` value for Delta-based ATM (mechanism is already implemented)
7. Validate RRG mathematical semantics and formulas
8. Update tests to reflect final business logic
9. Performance and reliability testing with live data

---

**Document Version:** 1.0  
**Last Updated:** 2026-08-23  
**Status:** Awaiting Client Response
