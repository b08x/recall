#!/usr/bin/env python3
"""Unified CLI for the recall package."""

import argparse
import json
import sys
from datetime import datetime
from dataclasses import asdict
from typing import Any

from recall.core import MultiSourceCorrelator
from recall.config import Settings

def serialize_value(v: Any) -> Any:
    """Recursively serialize values for JSON output."""
    if hasattr(v, 'isoformat'):
        return v.isoformat()
    elif isinstance(v, dict):
        return {k2: serialize_value(v2) for k2, v2 in v.items()}
    elif isinstance(v, list):
        return [serialize_value(item) for item in v]
    else:
        return v

def serialize_item(item: Any) -> Any:
    """Convert dataclass item to JSON-serializable dict."""
    data = asdict(item)
    return serialize_value(data)

def main():
    parser = argparse.ArgumentParser(description="Recall: Multi-platform session extraction and correlation")
    parser.add_argument("--tui", action="store_true", help="Display results in a Rich TUI dashboard")
    
    sub = parser.add_subparsers(dest="command", required=True)
    
    # Extract command
    p_extract = sub.add_parser("extract", help="Extract sessions from platforms")
    p_extract.add_argument("--days", type=int, default=7, help="Days to extract")
    p_extract.add_argument("--platforms", help="Comma-separated platforms (gemini,hermes,claude,opencode,obsidian)")
    p_extract.add_argument("--analyze", action="store_true", help="Analyze session topics using DSPy")
    p_extract.add_argument("--overwrite", action="store_true", help="Overwrite existing analysis in the database")
    p_extract.add_argument("--model", help="DSPy model identifier for general analysis")
    p_extract.add_argument("--insights-model", help="DSPy model identifier for deep insight extraction")
    p_extract.add_argument("--insights-provider", help="DSPy provider for deep insight extraction")
    p_extract.add_argument("--enhance-context", action="store_true",
                          help="Enhance insights using context from Obsidian and Git sources")
    p_extract.add_argument("--output", help="Output JSON file")
    
    # Correlate command
    p_correlate = sub.add_parser("correlate", help="Correlate sessions with GitHub and generate timeline")
    p_correlate.add_argument("--days", type=int, default=7)
    p_correlate.add_argument("--github-repo", help="GitHub repo (owner/name)")
    p_correlate.add_argument("--model", help="DSPy model identifier")
    p_correlate.add_argument("--output", help="Output JSON file")
    p_correlate.add_argument("--overwrite", action="store_true", help="Overwrite existing analysis in the database")
    p_correlate.add_argument("--enhance-context", action="store_true",
                           help="Enhance correlation with context from Obsidian and Git sources")
    
    # Search command
    p_search = sub.add_parser("search", help="Semantic search over saved sessions")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--limit", type=int, default=5, help="Number of results")
    p_search.add_argument("--platform", help="Filter by platform (gemini, claude, etc.)")
    
    # DLQ command
    p_dlq = sub.add_parser("dlq", help="Manage Dead Letter Queue for failed extractions")
    p_dlq.add_argument("--list", action="store_true", help="List items in DLQ")
    p_dlq.add_argument("--retry", action="store_true", help="Retry items in DLQ")
    p_dlq.add_argument("--clear", action="store_true", help="Clear all items from DLQ")
    
    args = parser.parse_args()
    
    settings = Settings()
    correlator = MultiSourceCorrelator(settings=settings)

    # Import rich components for search display
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.markdown import Markdown
    console = Console()
    
    if args.tui:
        from recall.tui import RecallTUI
        tui = RecallTUI()
        
        if args.command == "extract":
            platforms = args.platforms.split(",") if args.platforms else None
            enhance_context = getattr(args, 'enhance_context', False)
            tui.display_extraction_progress(correlator, args.days, platforms, args.analyze, args.overwrite, enhance_context)
        
        elif args.command == "correlate":
            platforms = None # Default all
            enhance_context = getattr(args, 'enhance_context', False)
            sessions = correlator.extract_all(
                args.days,
                platforms,
                analyze=True,
                overwrite=getattr(args, 'overwrite', False),
                enhance_with_context=enhance_context
            )
            tui.display_correlation(correlator, sessions, args.days, args.github_repo)
            
        sys.exit(0)

    if args.command == "extract":
        platforms = args.platforms.split(",") if args.platforms else None
        
        # Pre-flight check for tokens if analysis is requested and provider might be paid
        if args.analyze and correlator.dspy_provider != "ollama":
            console.print("\n[bold blue]Running pre-flight token estimation...[/bold blue]")
            
            # Collect sessions for estimation
            from datetime import timedelta, timezone
            cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
            date_range = {'start': cutoff, 'end': datetime.now(timezone.utc)}
            
            sessions_to_check = []
            for platform in (platforms or correlator.providers.keys()):
                if platform in correlator.providers:
                    files = correlator.providers[platform].discover(date_range)
                    for f in files:
                        s = correlator.providers[platform].parse(f)
                        if s: sessions_to_check.append(s)
            
            token_count = correlator.estimate_session_tokens(sessions_to_check)
            console.print(f"Estimated tokens for analysis: [bold]{token_count:,}[/bold]")
            
            # Simple threshold check
            if token_count > 50000:
                console.print("[yellow]Warning: High token count. Proceed? (y/n)[/yellow]")
                if input().lower() != 'y':
                    sys.exit(0)

        results = correlator.extract_all(
            args.days,
            platforms,
            analyze=args.analyze,
            overwrite=args.overwrite,
            model=args.model,
            insights_model=args.insights_model,
            insights_provider=args.insights_provider,
            enhance_with_context=getattr(args, 'enhance_context', False)
        )
        
        output = {p: [serialize_item(s) for s in sessions] for p, sessions in results.items()}
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
            print(f"\n✓ Saved to {args.output}")
        else:
            print(json.dumps(output, indent=2))
    
    elif args.command == "correlate":
        sessions = correlator.extract_all(
            args.days,
            analyze=True,  # Correlation requires analysis
            enhance_with_context=getattr(args, 'enhance_context', False)
        )
        
        github_data = None
        if args.github_repo:
            print(f"\n Fetching GitHub data for {args.github_repo}...")
            github_data = correlator.fetch_github_data(args.github_repo, args.days)
            print(f"   Found {len(github_data['commits'])} commits")
            
        print(f"\n Fetching local git data...")
        local_commits = correlator.fetch_local_git_data(args.days)
        
        timeline = correlator.build_timeline(sessions, github_data, local_commits)
        
        print(f"\n Correlating {len(timeline)} events...")
        result = correlator.correlate_with_dspy(timeline, model=args.model)
        
        print(f"\n{'='*60}")
        print(result["narrative"])
        print(f"\n Workstreams: {', '.join(result['workstreams'])}")
        print(f"\n Next Actions:")
        for action in result["next_actions"]:
            print(f"   • {action}")
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump({
                    "timeline": [serialize_value(t) for t in timeline],
                    "correlation": result
                }, f, indent=2)
            print(f"\n✓ Saved to {args.output}")
            
    elif args.command == "search":
        console.print(f"\n[bold blue]Searching for:[/bold blue] [italic]\"{args.query}\"[/italic]\n")
        
        results = correlator.db.semantic_search(
            query=args.query, 
            platform=args.platform
        )
        
        if not results or not results.get('documents') or not results['documents'][0]:
            console.print("[yellow]No semantic matches found.[/yellow]")
            sys.exit(0)
            
        documents = results['documents'][0]
        metadatas = results['metadatas'][0]
        distances = results['distances'][0] if 'distances' in results else [0.0] * len(documents)
        
        table = Table(title="Semantic Search Results", box=None, show_header=True, header_style="bold magenta")
        table.add_column("Score", justify="right", style="cyan")
        table.add_column("Platform", style="green")
        table.add_column("Project", style="blue")
        table.add_column("Preview", ratio=1)
        
        for doc, meta, dist in zip(documents, metadatas, distances):
            # cosine distance: 0.0 is perfect, 1.0 is unrelated
            score = f"{max(0, 1 - dist):.2f}"
            
            # Preview cleaning
            preview = doc.split("\n", 1)[-1].strip()[:150].replace("\n", " ") + "..."
            
            table.add_row(
                score,
                meta.get("platform", "unknown"),
                meta.get("project", "unknown"),
                preview
            )
            
        console.print(table)
        
        if documents:
            console.print("\n[bold green]Top Match Context:[/bold green]")
            top_meta = metadatas[0]
            console.print(Panel(
                Markdown(documents[0]),
                title=f"Session: {top_meta.get('session_id', 'unknown')}",
                subtitle=f"Topics: {top_meta.get('topics', 'None')}",
                border_style="magenta"
            ))

    elif args.command == "dlq":
        if args.list:
            items = correlator.db.get_dlq_items()
            if not items:
                console.print("[green]Dead Letter Queue is empty.[/green]")
            else:
                table = Table(title="Dead Letter Queue")
                table.add_column("ID", style="cyan")
                table.add_column("Session ID")
                table.add_column("Platform")
                table.add_column("Error", style="red")
                table.add_column("Failed At")
                table.add_column("Retries")
                
                for item in items:
                    table.add_row(
                        str(item["id"]),
                        item["session_id"],
                        item["payload"].get("platform", "unknown"),
                        item["error"][:50] + "..." if len(item["error"]) > 50 else item["error"],
                        item["failed_at"],
                        str(item["retry_count"])
                    )
                console.print(table)
        
        elif args.retry:
            results = correlator.retry_dlq()
            if results:
                console.print(f"[green]Successfully retried {len(results)} sessions.[/green]")
            else:
                console.print("[yellow]No sessions were successfully retried.[/yellow]")
        
        elif args.clear:
            items = correlator.db.get_dlq_items()
            for item in items:
                correlator.db.delete_dlq_item(item["id"])
            console.print(f"[green]Cleared {len(items)} items from DLQ.[/green]")
        
        else:
            # Default to list
            items = correlator.db.get_dlq_items()
            console.print(f"DLQ contains {len(items)} items. Use --list, --retry, or --clear.")

if __name__ == "__main__":
    main()
