"""CLI viewer for Kafka translator — real-time monitoring and management."""

import asyncio
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Optional

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("rich is required. Install with: pip install rich")
    sys.exit(1)

try:
    from aiohttp import ClientSession, ClientTimeout
except ImportError:
    print("aiohttp is required. Install with: pip install aiohttp")
    sys.exit(1)

logger = logging.getLogger("kafka_translator_cli")

__version__ = "0.1.0"

# ============================================================================
# Configuration
# ============================================================================


class ViewerConfig:
    """Configuration via environment variables or defaults."""

    def __init__(self):
        self.api_url = "http://localhost:8000"
        self.refresh_interval = 2.0  # seconds
        self.max_history_lines = 10

    def load_from_env(self):
        """Override defaults with environment variables."""
        import os
        self.api_url = os.environ.get("TRANSLATOR_API_URL", self.api_url)
        self.refresh_interval = float(
            os.environ.get("TRANSLATOR_REFRESH_INTERVAL", self.refresh_interval)
        )


config = ViewerConfig()

# ============================================================================
# API client
# ============================================================================


async def fetch_json(session: ClientSession, endpoint: str) -> dict:
    """Fetch JSON from the API endpoint."""
    url = f"{config.api_url}{endpoint}"
    try:
        async with session.get(url, timeout=ClientTimeout(total=5)) as resp:
            return await resp.json()
    except Exception as e:
        logger.error(f"API error on {endpoint}: {e}")
        return {}


# ============================================================================
# UI helpers
# ============================================================================


def format_timestamp(dt: Optional[datetime]) -> str:
    """Format timestamp in local time."""
    if dt is None:
        return "N/A"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def create_status_table(data: dict) -> Table:
    """Create a formatted status table."""
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value")

    table.add_row("Status", "✅ Running" if data.get("running") else "❌ Stopped")
    table.add_row("Version", data.get("version", "N/A"))
    table.add_row(
        "Uptime",
        f"{data.get('uptime_seconds', 0):.1f}s"
        if data.get("uptime_seconds")
        else "N/A",
    )
    table.add_row(
        "Messages Transferred", str(data.get("messages_transferred", 0))
    )
    table.add_row(
        "Bytes Transferred", str(data.get("bytes_transferred", 0))
    )
    table.add_row("Errors", str(data.get("errors", 0)))
    if data.get("last_error"):
        table.add_row("Last Error", Text(data["last_error"], style="red"))

    return table


def create_config_panel(data: dict) -> Panel:
    """Create a config panel."""
    lines = [
        f"Source Topic: {data.get('source_topic', 'N/A')}",
        f"Dest Topic: {data.get('dest_topic', 'N/A')}",
        f"Source Brokers: {data.get('source_bootstrap_servers', 'N/A')}",
        f"Dest Brokers: {data.get('dest_bootstrap_servers', 'N/A')}",
        f"Group ID: {data.get('group_id', 'N/A')}",
    ]
    return Panel("\n".join(lines), title="Configuration", border_style="green")


# ============================================================================
# Main viewer loop
# ============================================================================


async def run_viewer():
    """Run the interactive CLI viewer."""
    console = Console()
    config.load_from_env()

    async with ClientSession() as session:
        while True:
            try:
                # Fetch data
                status_data = await fetch_json(session, "/status")
                metrics_data = await fetch_json(session, "/metrics")

                # Clear screen
                console.clear()

                # Title
                console.print(
                    Panel.fit(
                        f" Kafka Translator CLI Viewer v{__version__} "
                        + f"| API: {config.api_url}",
                        title="-status-",
                        border_style="blue",
                    )
                )

                # Status table
                if status_data:
                    console.print(create_status_table(status_data))
                    console.print(create_config_panel(status_data))

                    # Metrics summary
                    if metrics_data:
                        console.print(
                            Panel(
                                f"Errors: {metrics_data.get('errors', 0)} "
                                + f"| Last Error: {metrics_data.get('last_error', 'N/A')}",
                                title="Metrics",
                                border_style="yellow",
                            )
                        )
                else:
                    console.print(
                        Panel(
                            "⚠️ Could not connect to API.",
                            title="Connection Error",
                            border_style="red",
                        )
                    )

                # Footer
                console.print(
                    Panel.fit(
                        "Press Ctrl+C to quit | Refresh interval: "
                        + f"{config.refresh_interval}s",
                        border_style="dim",
                    )
                )

                # Wait
                await asyncio.sleep(config.refresh_interval)

            except KeyboardInterrupt:
                console.print("\n[bold green]👋 Quitting...[/]")
                break
            except Exception as e:
                logger.error(f"Viewer error: {e}")
                console.print(
                    Panel(
                        f"[red]Error:[/] {e}",
                        title="Error",
                        border_style="red",
                    )
                )


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="kafka-translator-cli",
        description="CLI viewer for Kafka Translator service",
    )
    parser.add_argument(
        "--url",
        "-u",
        default=None,
        help="API URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=None,
        help="Refresh interval in seconds (default: 2.0)",
    )
    parser.add_argument(
        "--version", "-v", action="store_true", help="Show version and exit"
    )

    args = parser.parse_args()

    if args.version:
        print(f"kafka-translator-cli v{__version__}")
        sys.exit(0)

    if args.url:
        config.api_url = args.url
    if args.interval is not None:
        config.refresh_interval = args.interval

    print(
        f"[bold]Kafka Translator CLI Viewer v{__version__}[/]"
    )
    print(f"API URL: {config.api_url}")
    print(f"Refresh interval: {config.refresh_interval}s")
    print()

    # Run viewer
    asyncio.run(run_viewer())


if __name__ == "__main__":
    main()
