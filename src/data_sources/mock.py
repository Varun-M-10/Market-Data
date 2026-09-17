import math
import random
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from src.data_sources.base import DataSource
from src.models import PriceTick
from src.option_chain.expiry import resolve_mock_expiry


class MockDataSource(DataSource):
    """
    Simulated market data for development and demos.
    Generates realistic NIFTY-like prices and option chain structure.
    """

    def __init__(
        self,
        underlying: str = "NIFTY",
        poll_interval: float = 5.0,
        timezone: str = "Asia/Kolkata",
        expiry: str | None = None,
    ):
        self.underlying = underlying
        self.poll_interval = poll_interval
        self.tz = ZoneInfo(timezone)
        self._spot = 24_850.0
        self._drift = 0.0
        # `expiry` (config.yaml's `expiry` key / `EXPIRY` env var) pins the
        # date reported below; leave it unset (None) to auto-compute the next
        # weekly expiry instead of a hard-coded, ever-staler date — see
        # resolve_mock_expiry(). Resolved once per instance so it stays
        # consistent (Option Chain / Paper Trading / Straddle Chart all read
        # the same value) for the life of this data source.
        self.expiry = resolve_mock_expiry(expiry, timezone)

    def fetch_option_chain(self) -> dict:
        self._spot += random.uniform(-15, 15)
        spot = round(self._spot, 2)
        atm_strike = round(spot / 50) * 50
        strikes = []
        for i in range(-5, 6):
            strike = atm_strike + i * 50
            distance = abs(strike - spot)
            call_ltp = max(5, 200 - distance * 0.8 + random.uniform(-5, 5))
            put_ltp = max(5, 200 - distance * 0.8 + random.uniform(-5, 5))

            # Mock Greeks: a logistic curve centered on spot gives Call Delta ~0.5
            # (and Put Delta ~-0.5) right at the money, decaying toward 0/1 as the
            # strike moves ITM/OTM — good enough to exercise Delta-based ATM
            # selection without a full pricing model.
            signed_distance = strike - spot
            call_delta = round(1.0 / (1.0 + math.exp(signed_distance / 100.0)), 4)
            put_delta = round(call_delta - 1.0, 4)

            strikes.append(
                {
                    "strikePrice": strike,
                    "CE": {
                        "lastPrice": round(call_ltp, 2),
                        "openInterest": random.randint(10000, 500000),
                        "totalTradedVolume": random.randint(1000, 50000),
                        "delta": call_delta,
                    },
                    "PE": {
                        "lastPrice": round(put_ltp, 2),
                        "openInterest": random.randint(10000, 500000),
                        "totalTradedVolume": random.randint(1000, 50000),
                        "delta": put_delta,
                    },
                }
            )

        now = datetime.now(self.tz)
        return {
            "records": {
                "underlyingValue": spot,
                "expiryDates": [self.expiry],
                "timestamp": now.strftime("%d-%b-%Y %H:%M:%S"),
                "data": strikes,
            }
        }

    def get_underlying_ltp(self) -> float:
        return float(self.fetch_option_chain()["records"]["underlyingValue"])

    def stream_ticks(self):
        while True:
            chain = self.fetch_option_chain()
            spot = float(chain["records"]["underlyingValue"])
            now = datetime.now(self.tz)
            yield PriceTick(
                symbol=self.underlying,
                price=spot,
                timestamp=now,
            )
            time.sleep(self.poll_interval)
