import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.text import Text
from rich.align import Align
from rich import box

class RecallTUI:
    """Rich-based TUI for the recall package."""

    def __init__(self):
        self.console = Console()
        self.layout = Layout()
        self.logs = []
        self._setup_layout()
        self._setup_logging()

    def _setup_layout(self):
        """Initialize the dashboard layout."""
        self.layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main"),
            Layout(name="footer", size=3)
        )
        self.layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=2)
        )
        self.layout["right"].split_column(
            Layout(name="top_right", ratio=1),
            Layout(name="bottom_right", ratio=1)
        )

        self.layout["header"].update(
            Panel(
                Align.center(Text("RECALL: Multi-platform Session Correlator", style="bold cyan")),
                box=box.ROUNDED,
                style="blue"
            )
        )
        self.layout["footer"].update(
            Panel(
                Align.center(Text("Press Ctrl+C to exit", style="dim")),
                box=box.ROUNDED
            )
        )
        
        # Default empty panels
        self.layout["top_right"].update(Panel(Text("Waiting for activity...", style="dim"), title="Activity", border_style="blue"))
        self.layout["bottom_right"].update(Panel(Text("No insights generated yet.", style="dim"), title="Logs", border_style="white"))

    def _setup_logging(self):
        """Setup a logging handler to capture logs for the TUI."""
        class TUIHandler(logging.Handler):
            def __init__(self, tui):
                super().__init__()
                self.tui = tui

            def emit(self, record):
                msg = self.format(record)
                self.tui.logs.append(msg)
                if len(self.tui.logs) > 100:
                    self.tui.logs.pop(0)

        handler = TUIHandler(self)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.getLogger("recall").addHandler(handler)

    def render_logs(self):
        """Render the captured logs in the bottom right panel."""
        log_text = Text()
        for log in self.logs[-15:]:  # Last 15 logs
            if "Error" in log or "error" in log.lower():
                log_text.append(f" {log}\n", style="red")
            elif "Processing" in log or "Extracting" in log or "Analyzing" in log:
                log_text.append(f" {log}\n", style="cyan")
            else:
                log_text.append(f" {log}\n", style="dim")
        
        self.layout["bottom_right"].update(Panel(log_text, title="Debug Logs", border_style="white"))

    def render_extraction(self, platforms_data: Dict[str, List[Any]]):
        """Render the extraction results in a table."""
        table = Table(title="Extracted Sessions", box=box.SIMPLE, expand=True)
        table.add_column("Platform", style="cyan")
        table.add_column("Count", style="green", justify="right")
        table.add_column("Latest", style="magenta")

        for platform, items in platforms_data.items():
            latest = "N/A"
            if items:
                # Find latest timestamp
                latest_ts = None
                for item in items:
                    ts = getattr(item, 'started_at', getattr(item, 'updated_at', None))
                    if ts and (not latest_ts or ts > latest_ts):
                        latest_ts = ts
                if latest_ts:
                    latest = latest_ts.strftime("%Y-%m-%d %H:%M")
            
            table.add_row(platform, str(len(items)), latest)

        self.layout["left"].update(Panel(table, title="Sources", border_style="green"))

    def render_timeline(self, timeline: List[Dict]):
        """Render a mini-timeline of recent events."""
        table = Table(box=box.MINIMAL, expand=True)
        table.add_column("Time", style="dim", width=12)
        table.add_column("Type", style="bold")
        table.add_column("Summary")

        for event in timeline[-15:]:  # Last 15 events
            ts = event.get("timestamp")
            ts_str = ts.strftime("%H:%M") if ts else "??:??"
            
            etype = event["type"]
            style = "cyan"
            if etype == "commit": style = "yellow"
            elif etype == "note": style = "green"
            
            table.add_row(
                ts_str,
                Text(etype.upper(), style=style),
                event.get("summary", "")[:60]
            )

        self.layout["top_right"].update(Panel(table, title="Recent Activity Timeline", border_style="blue"))

    def render_correlation(self, correlation: Dict):
        """Render the AI correlation narrative and next actions."""
        narrative = correlation.get("narrative", "No narrative generated.")
        workstreams = correlation.get("workstreams", [])
        next_actions = correlation.get("next_actions", [])

        content = Text()
        content.append("\n[bold]Narrative:[/bold]\n", style="cyan")
        content.append(f"{narrative}\n\n")
        
        if workstreams:
            content.append("[bold]Workstreams:[/bold] ", style="green")
            content.append(f"{', '.join(workstreams)}\n\n")
            
        if next_actions:
            content.append("[bold]Next Actions:[/bold]\n", style="magenta")
            for action in next_actions:
                content.append(f" • {action}\n")

        self.layout["bottom_right"].update(Panel(content, title="AI Insights & Next Actions", border_style="magenta"))

    def display_extraction_progress(self, correlator, days: int, platforms: Optional[List[str]] = None, analyze: bool = False, overwrite: bool = False, enhance_context: bool = False):
        """Run extraction with a live progress display."""
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        )
        
        task = progress.add_task("[cyan]Initializing...", total=100)
        
        def update_progress(description: str, progress_val: float = 0.0, **kwargs):
            # The callback might be called with 'progress' keyword
            p = kwargs.get('progress', progress_val)
            progress.update(task, description=description, completed=p * 100)
            # Update logs in the layout
            self.render_logs()

        with Live(self.layout, refresh_per_second=4, screen=True):
            self.layout["left"].update(Panel(progress, title="Progress", border_style="yellow"))
            
            # Execute extraction
            results = correlator.extract_all(
                days=days,
                platforms=platforms,
                analyze=analyze,
                overwrite=overwrite,
                enhance_with_context=enhance_context,
                callback=update_progress
            )
            
            self.render_extraction(results)
            self.render_logs()
            time.sleep(1)
            return results

    def display_correlation(self, correlator, sessions, days: int, github_repo: Optional[str] = None):
        """Run correlation with live updates."""
        with Live(self.layout, refresh_per_second=4, screen=True):
            # Fetch git data
            self.layout["footer"].update(Panel(Align.center(Text("Fetching Git data...", style="yellow"))))
            
            local_commits = correlator.fetch_local_git_data(days)
            github_data = None
            if github_repo:
                github_data = correlator.fetch_github_data(github_repo, days)
                
            timeline = correlator.build_timeline(sessions, github_data, local_commits)
            self.render_timeline(timeline)
            
            # Correlate
            self.layout["footer"].update(Panel(Align.center(Text("Generating AI Narrative...", style="magenta"))))
            result = correlator.correlate_with_dspy(timeline)
            
            self.render_correlation(result)
            self.layout["footer"].update(Panel(Align.center(Text("Correlation Complete", style="green"))))
            
            # Wait for user input to exit or just stay until Ctrl+C
            while True:
                self.render_logs()
                time.sleep(1)
