from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from src.models import ATMResult, Candle


class ConsoleDisplay:
    """Real-time terminal dashboard for prices, ATM, and candles."""

    def __init__(self):
        self.console = Console()
        self._last_price: float | None = None
        self._last_atm: ATMResult | None = None
        self._active_candles: dict[int, Candle] = {}
        self._recent_completed: dict[int, list[Candle]] = {}
        self._tick_count = 0
        self._started_at = datetime.now()

    def update(
        self,
        price: float,
        atm: ATMResult | None,
        active_candles: dict[int, Candle],
        completed: list[Candle] | None = None,
    ) -> None:
        self._last_price = price
        self._last_atm = atm
        self._active_candles = active_candles
        self._tick_count += 1

        if completed:
            for candle in completed:
                bucket = self._recent_completed.setdefault(candle.interval_minutes, [])
                bucket.append(candle)
                if len(bucket) > 5:
                    self._recent_completed[candle.interval_minutes] = bucket[-5:]

    def render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
        )
        layout["body"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2),
        )

        uptime = datetime.now() - self._started_at
        header = Text(
            f"Live Market Data  |  Ticks: {self._tick_count}  |  "
            f"Uptime: {str(uptime).split('.')[0]}",
            style="bold cyan",
            justify="center",
        )
        layout["header"].update(Panel(header, border_style="cyan"))

        layout["left"].update(Panel(self._price_panel(), title="Spot & ATM", border_style="green"))
        layout["right"].update(Panel(self._candle_table(), title="Candles (OHLC)", border_style="yellow"))
        return layout

    def _price_panel(self) -> Table:
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="dim")
        table.add_column("Value", style="bold white")

        if self._last_price is not None:
            table.add_row("Underlying LTP", f"{self._last_price:,.2f}")

        if self._last_atm:
            atm = self._last_atm
            method_label = f"Delta (Δ≈{atm.delta_threshold:.2f})" if atm.method == "delta" else "Price"
            table.add_row("ATM Strike", f"{atm.strike:,.0f}  [{method_label}]")
            if atm.method == "delta" and atm.price_based_strike is not None and atm.price_based_strike != atm.strike:
                table.add_row("  Nearest to Spot", f"{atm.price_based_strike:,.0f}")
            table.add_row("ATM Call (CE)", f"{atm.call_ltp:,.2f}" + (f"  Δ{atm.call_delta:+.2f}" if atm.call_delta is not None else ""))
            table.add_row("ATM Put (PE)", f"{atm.put_ltp:,.2f}" + (f"  Δ{atm.put_delta:+.2f}" if atm.put_delta is not None else ""))
            table.add_row("Combined Value (CE+PE)", f"{atm.straddle_premium:,.2f}")
            table.add_row("Dist from Spot", f"{atm.distance_from_spot:,.2f}")
        else:
            table.add_row("ATM", "—")

        return table

    def _candle_table(self) -> Table:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Interval")
        table.add_column("Status")
        table.add_column("Open")
        table.add_column("High")
        table.add_column("Low")
        table.add_column("Close")
        table.add_column("Ticks")

        for interval in sorted(self._active_candles.keys()):
            candle = self._active_candles[interval]
            table.add_row(
                f"{interval}m",
                "[yellow]building[/]",
                f"{candle.open:,.2f}",
                f"{candle.high:,.2f}",
                f"{candle.low:,.2f}",
                f"{candle.close:,.2f}",
                str(candle.tick_count),
            )

        for interval, candles in sorted(self._recent_completed.items()):
            for candle in reversed(candles[-3:]):
                table.add_row(
                    f"{interval}m",
                    "[green]closed[/]",
                    f"{candle.open:,.2f}",
                    f"{candle.high:,.2f}",
                    f"{candle.low:,.2f}",
                    f"{candle.close:,.2f}",
                    str(candle.tick_count),
                )

        if not self._active_candles and not self._recent_completed:
            table.add_row("—", "waiting for ticks", "—", "—", "—", "—", "—")

        return table

    def print_completed_candle(self, candle: Candle) -> None:
        self.console.print(
            f"[green]✓[/] {candle.interval_minutes}m candle closed  "
            f"O={candle.open:,.2f} H={candle.high:,.2f} "
            f"L={candle.low:,.2f} C={candle.close:,.2f}  "
            f"({candle.open_time.strftime('%H:%M')}–{candle.close_time.strftime('%H:%M')})"
        )

    def run_live(self, refresh_callback):
        """Run Rich Live display; refresh_callback returns updated layout."""
        with Live(self.render(), refresh_per_second=2, console=self.console) as live:
            while True:
                refresh_callback()
                live.update(self.render())
