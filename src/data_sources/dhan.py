from __future__ import annotations

import asyncio
import os
import queue
import threading
import time
from datetime import datetime
from typing import Optional

import websockets
from dhanhq import dhanhq
from dhanhq.marketfeed import DhanFeed, IDX, Ticker, Quote, Full

from src.data_sources.base import DataSource
from src.models import PriceTick
from src.logging import get_logger
from src.timeutil import now_ist


from pathlib import Path
from dotenv import load_dotenv


def _ensure_env_loaded() -> None:
    root_dir = Path(__file__).resolve().parent.parent.parent
    root_env = root_dir / ".env"
    example_env = root_dir / ".env.example"
    
    # If .env doesn't exist but .env.example exists with credentials, copy/sync
    if not root_env.exists() and example_env.exists():
        try:
            content = example_env.read_text(encoding="utf-8")
            root_env.write_text(content, encoding="utf-8")
        except Exception:
            pass

    for name in [".env", ".env.example"]:
        env_file = root_dir / name
        if env_file.exists():
            load_dotenv(env_file)

    cwd = Path.cwd()
    for name in [".env", ".env.example"]:
        cwd_file = cwd / name
        if cwd_file.exists():
            load_dotenv(cwd_file)

    load_dotenv()


class DhanMarketDataProvider(DataSource):
    """
    Live market data provider using DhanHQ API v2.0.2.
    
    Uses WebSocket (DhanFeed v2) for real-time tick data and REST API for option chain.
    Requires DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN environment variables.
    """

    NIFTY_SECURITY_ID = 13
    NIFTY_SEGMENT = "IDX_I"
    NIFTY_SEGMENT_NUM = IDX  # 0 for IDX
    
    OPTION_CHAIN_RATE_LIMIT = 3.0  # seconds between REST requests
    
    def __init__(self, underlying: str = "NIFTY", poll_interval: float = 5.0):
        self.underlying = underlying.upper()
        self.poll_interval = poll_interval
        self._logger = get_logger("INFO")
        
        # Ensure .env file is loaded before reading environment variables
        _ensure_env_loaded()
        
        self._client_id = os.getenv("DHAN_CLIENT_ID")
        self._access_token = os.getenv("DHAN_ACCESS_TOKEN")
        
        client_id_present = bool(
            self._client_id and self._client_id.strip() and self._client_id != "your_client_id_here"
        )
        access_token_present = bool(
            self._access_token and self._access_token.strip() and self._access_token != "your_access_token_here"
        )
        
        # Safe diagnostic reporting (never exposing credential values)
        self._logger.log_system_event(
            "dhan_credential_diagnostic",
            {
                "Client ID present": "yes" if client_id_present else "no",
                "Access token present": "yes" if access_token_present else "no",
            }
        )

        if not client_id_present or not access_token_present:
            diag_msg = f"Client ID present: {'yes' if client_id_present else 'no'}, Access token present: {'yes' if access_token_present else 'no'}"
            raise ValueError(
                f"DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN environment variables are required for Dhan data source. Diagnostic: [{diag_msg}]"
            )
        
        self.client_id_masked = self._mask_client_id(self._client_id)
        
        # State tracking
        self._is_authenticated = False
        self._is_connected = False
        self._has_received_tick = False
        self._latest_tick: Optional[PriceTick] = None

        # REST client initialization
        self._dhan: Optional[dhanhq] = None
        self._initialize_rest_client()
        
        # State for option chain caching & expiry
        self._last_chain: dict | None = None
        self._last_chain_fetch_time: float = 0.0
        self._current_expiry: str | None = None
        self._initialize_expiry()
        
        # WebSocket thread management
        self._feed: Optional[DhanFeed] = None
        self._tick_queue: queue.Queue = queue.Queue(maxsize=1000)
        self._ws_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _mask_client_id(self, client_id: str) -> str:
        """Mask client ID for safe logging."""
        if len(client_id) <= 4:
            return "****"
        return client_id[:2] + "****" + client_id[-2:]

    def _initialize_rest_client(self) -> None:
        """Initialize Dhan REST API client."""
        try:
            self._dhan = dhanhq(
                client_id=self._client_id,
                access_token=self._access_token
            )
            self._is_authenticated = True
            self._logger.log_system_event(
                "dhan_auth_success",
                {"client_id": self.client_id_masked, "status": "authenticated"}
            )
        except Exception as e:
            self._is_authenticated = False
            self._logger.log_error(e, {"context": "dhan_rest_init", "client_id": self.client_id_masked})
            raise ConnectionError(f"Failed to authenticate Dhan client: {e}") from e

    def _initialize_expiry(self) -> None:
        """Fetch and set the nearest expiry for the underlying."""
        if not self._dhan:
            return
        try:
            expiry_list = self._dhan.expiry_list(
                under_security_id=self.NIFTY_SECURITY_ID,
                under_exchange_segment=self.NIFTY_SEGMENT
            )
            
            if isinstance(expiry_list, list) and len(expiry_list) > 0:
                self._current_expiry = expiry_list[0]
                self._logger.log_system_event("dhan_expiry_set", {"expiry": self._current_expiry})
            elif isinstance(expiry_list, dict) and expiry_list.get("status") == "failure":
                err_data = str(expiry_list.get("data", {}))
                if "808" in err_data or "Authentication Failed" in err_data:
                    self._logger.log_system_event(
                        "dhan_auth_error",
                        {
                            "error_code": 808,
                            "message": "Dhan Authentication Failed: Client ID or Access Token invalid/expired. Check credentials in .env file."
                        }
                    )
                elif "806" in err_data or "Data APIs not Subscribed" in err_data:
                    self._logger.log_system_event(
                        "dhan_subscription_error",
                        {
                            "error_code": 806,
                            "message": "Dhan Data APIs not Subscribed. Enable Data API Access in your DhanHQ portal."
                        }
                    )
                else:
                    self._logger.log_system_event("dhan_expiry_warning", {"message": f"Expiry fetch failed: {expiry_list}"})
            else:
                self._logger.log_system_event("dhan_expiry_warning", {"message": "No expiry dates found"})
        except Exception as e:
            self._logger.log_error(e, {"context": "dhan_expiry_fetch"})
            self._current_expiry = None

    def fetch_option_chain(self) -> dict:
        """
        Fetch option chain from Dhan REST API with rate limiting.
        """
        current_time = time.time()
        time_since_last_fetch = current_time - self._last_chain_fetch_time
        
        if time_since_last_fetch < self.OPTION_CHAIN_RATE_LIMIT:
            sleep_time = self.OPTION_CHAIN_RATE_LIMIT - time_since_last_fetch
            time.sleep(sleep_time)
        
        try:
            if not self._current_expiry:
                self._initialize_expiry()
                if not self._current_expiry:
                    raise ValueError("Cannot fetch option chain: no expiry available")
            
            assert self._dhan is not None
            response = self._dhan.option_chain(
                under_security_id=self.NIFTY_SECURITY_ID,
                under_exchange_segment=self.NIFTY_SEGMENT,
                expiry=self._current_expiry
            )
            
            self._last_chain_fetch_time = time.time()
            normalized = self._normalize_option_chain(response)
            self._last_chain = normalized
            return normalized
            
        except Exception as e:
            self._logger.log_error(e, {"context": "dhan_option_chain_fetch"})
            if self._last_chain:
                return self._last_chain
            raise ConnectionError(f"Dhan option chain fetch failed: {e}") from e

    def _normalize_option_chain(self, dhan_response: dict) -> dict:
        """
        Normalize Dhan option chain response to standard NSE-like format.
        """
        try:
            if isinstance(dhan_response, dict) and dhan_response.get("status") == "failure":
                raise ValueError(f"Dhan API option chain failed: {dhan_response.get('data')}")
            
            data = dhan_response.get("data", {})
            underlying_ltp = data.get("last_price", 0.0)
            oc_data = data.get("oc", {})
            
            strikes = []
            for strike_str, strike_data in oc_data.items():
                try:
                    strike = float(strike_str)
                    
                    ce_data = strike_data.get("ce", {})
                    ce_ltp = float(ce_data.get("last_price", 0.0))
                    ce_oi = int(ce_data.get("oi", 0))
                    ce_volume = int(ce_data.get("volume", 0))
                    
                    pe_data = strike_data.get("pe", {})
                    pe_ltp = float(pe_data.get("last_price", 0.0))
                    pe_oi = int(pe_data.get("oi", 0))
                    pe_volume = int(pe_data.get("volume", 0))
                    
                    if ce_ltp > 0 or pe_ltp > 0:
                        strikes.append({
                            "strikePrice": strike,
                            "CE": {
                                "lastPrice": ce_ltp,
                                "openInterest": ce_oi,
                                "totalTradedVolume": ce_volume,
                            },
                            "PE": {
                                "lastPrice": pe_ltp,
                                "openInterest": pe_oi,
                                "totalTradedVolume": pe_volume,
                            },
                        })
                except (ValueError, TypeError):
                    continue
            
            strikes.sort(key=lambda x: x["strikePrice"])
            
            return {
                "records": {
                    "underlyingValue": float(underlying_ltp),
                    "expiryDates": [self._current_expiry] if self._current_expiry else [],
                    "timestamp": now_ist().strftime("%d-%b-%Y %H:%M:%S"),
                    "data": strikes,
                }
            }
            
        except Exception as e:
            self._logger.log_error(e, {"context": "dhan_normalization"})
            raise ValueError(f"Failed to normalize Dhan option chain: {e}") from e

    def get_underlying_ltp(self) -> float:
        """Return latest underlying LTP."""
        if self._latest_tick:
            return self._latest_tick.price
        if self._last_chain is None:
            self.fetch_option_chain()
        assert self._last_chain is not None
        return float(self._last_chain["records"]["underlyingValue"])

    def stream_ticks(self):
        """
        Yield PriceTick objects continuously via Dhan WebSocket.
        """
        self._stop_event.clear()
        
        # Start WebSocket background thread
        if not self._ws_thread or not self._ws_thread.is_alive():
            self._ws_thread = threading.Thread(
                target=self._run_websocket_loop,
                daemon=True
            )
            self._ws_thread.start()
        
        while not self._stop_event.is_set():
            try:
                tick = self._tick_queue.get(timeout=1.0)
                if tick is None:
                    break
                yield tick
            except queue.Empty:
                if self._ws_thread and not self._ws_thread.is_alive() and not self._stop_event.is_set():
                    self._logger.log_system_event("dhan_ws_restarting", {"reason": "thread_died"})
                    self._ws_thread = threading.Thread(
                        target=self._run_websocket_loop,
                        daemon=True
                    )
                    self._ws_thread.start()
                continue

    def _run_websocket_loop(self) -> None:
        """Background thread executing async WebSocket event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        
        try:
            self._loop.run_until_complete(self._async_websocket_handler())
        except Exception as e:
            self._logger.log_error(e, {"context": "dhan_ws_loop_fatal"})
        finally:
            self._is_connected = False
            self._loop.close()
            self._loop = None

    async def _async_websocket_handler(self) -> None:
        """Async handler for DhanFeed WebSocket connection and continuous tick processing."""
        instruments = [(self.NIFTY_SEGMENT_NUM, str(self.NIFTY_SECURITY_ID), Ticker)]
        
        retry_delay = 2
        max_retry_delay = 30

        while not self._stop_event.is_set():
            try:
                self._logger.log_system_event(
                    "dhan_ws_connecting",
                    {
                        "client_id": self.client_id_masked,
                        "instruments": f"NIFTY (SecID: {self.NIFTY_SECURITY_ID}, Segment: {self.NIFTY_SEGMENT})",
                        "version": "v2"
                    }
                )

                self._feed = DhanFeed(
                    client_id=self._client_id,
                    access_token=self._access_token,
                    instruments=instruments,
                    version="v2"
                )

                await self._feed.connect()
                self._is_connected = True
                retry_delay = 2  # reset delay on successful connection
                
                self._logger.log_system_event(
                    "dhan_ws_connected",
                    {
                        "status": "connected",
                        "client_id": self.client_id_masked,
                        "subscribed_symbols": ["NIFTY 50 Index"]
                    }
                )

                # Continuous receive loop
                while not self._stop_event.is_set():
                    data = await self._feed.get_instrument_data()
                    
                    if getattr(self._feed, "on_close", False):
                        self._logger.log_system_event("dhan_ws_closed_by_server", {"status": "disconnected"})
                        self._is_connected = False
                        break
                    
                    if data and isinstance(data, dict):
                        ltp_val = data.get("LTP") or data.get("last_price")
                        if ltp_val is not None:
                            try:
                                price = float(ltp_val)
                                sec_id = str(data.get("security_id", self.NIFTY_SECURITY_ID))
                                ltt = str(data.get("LTT", ""))
                                tick_ts = now_ist()
                                
                                tick = PriceTick(
                                    symbol=self.underlying,
                                    price=price,
                                    timestamp=tick_ts
                                )
                                
                                self._latest_tick = tick
                                self._has_received_tick = True
                                
                                self._logger.log_price_tick(
                                    tick,
                                    {
                                        "source": "dhan",
                                        "instrument_id": sec_id,
                                        "ltp": price,
                                        "ltt": ltt,
                                        "connected": True
                                    }
                                )
                                
                                try:
                                    self._tick_queue.put_nowait(tick)
                                except queue.Full:
                                    pass
                            except ValueError as ve:
                                self._logger.log_error(ve, {"context": "dhan_tick_parse_value"})

            except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException) as ws_err:
                self._is_connected = False
                self._logger.log_error(ws_err, {"context": "dhan_ws_connection_closed", "reconnect_in": retry_delay})
            except Exception as exc:
                self._is_connected = False
                self._logger.log_error(exc, {"context": "dhan_ws_error", "reconnect_in": retry_delay})

            if not self._stop_event.is_set():
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * 2, max_retry_delay)

    def disconnect(self) -> None:
        """Clean disconnect of Dhan WebSocket connection."""
        self._stop_event.set()
        try:
            self._tick_queue.put_nowait(None)
        except queue.Full:
            pass

        if self._feed and self._feed.ws:
            try:
                if self._loop and self._loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._feed.ws.close(), self._loop)
                self._logger.log_system_event("dhan_ws_disconnected", {"status": "clean"})
            except Exception as e:
                self._logger.log_error(e, {"context": "dhan_disconnect"})

        if self._ws_thread and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=2)
            self._ws_thread = None

        self._is_connected = False


    @property
    def is_authenticated(self) -> bool:
        return self._is_authenticated

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def has_received_tick(self) -> bool:
        return self._has_received_tick

    @property
    def latest_tick(self) -> Optional[PriceTick]:
        return self._latest_tick


# Alias for backward compatibility
DhanDataSource = DhanMarketDataProvider
