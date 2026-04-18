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
    p_extract.add_argument("--model", help="DSPy model identifier")
    p_extract.add_argument("--output", help="Output JSON file")
    
    # Correlate command
    p_correlate = sub.add_parser("correlate", help="Correlate sessions with GitHub and generate timeline")
    p_correlate.add_argument("--days", type=int, default=7)
    p_correlate.add_argument("--github-repo", help="GitHub repo (owner/name)")
    p_correlate.add_argument("--model", help="DSPy model identifier")
    p_correlate.add_argument("--output", help="Output JSON file")
    
    # Search command
    p_search = sub.add_parser("search", help="Search sessions by topic")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--days", type=int, default=30)
    p_search.add_argument("--platforms", help="Comma-separated platforms")
    
    args = parser.parse_args()
    
    settings = Settings()
    correlator = MultiSourceCorrelator(settings=settings)
    
    if args.tui:
        from recall.tui import RecallTUI
        tui = RecallTUI()
        
        if args.command == "extract":
            platforms = args.platforms.split(",") if args.platforms else None
            tui.display_extraction_progress(correlator, args.days, platforms, args.analyze)
        
        elif args.command == "correlate":
            platforms = None # Default all
            sessions = correlator.extract_all(args.days, platforms)
            tui.display_correlation(correlator, sessions, args.days, args.github_repo)
            
        sys.exit(0)

    if args.command == "extract":
        platforms = args.platforms.split(",") if args.platforms else None
        results = correlator.extract_all(args.days, platforms, analyze=args.analyze, model=args.model)
        
        output = {}
        for platform, items in results.items():
            output[platform] = [serialize_item(s) for s in items]
        
        if args.output:
            with open(args.output, "w") as f:
                json.dump(output, f, indent=2)
            print(f"\n✓ Saved to {args.output}")
        else:
            print(json.dumps(output, indent=2))
    
    elif args.command == "correlate":
        sessions = correlator.extract_all(args.days)
        
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
        platforms = args.platforms.split(",") if args.platforms else None
        sessions = correlator.extract_all(args.days, platforms)
        
        results = []
        query_lower = args.query.lower()
        
        for platform, platform_sessions in sessions.items():
            for session in platform_sessions:
                if not hasattr(session, 'messages'): continue
                
                title_match = hasattr(session, 'generated_title') and session.generated_title and query_lower in session.generated_title.lower()
                content_match = any(
                    query_lower in m.content.lower() 
                    for m in session.messages
                )
                
                if title_match or content_match:
                    results.append({
                        "platform": platform,
                        "session_id": session.id,
                        "title": getattr(session, 'generated_title', "Untitled") or "Untitled",
                        "started_at": session.started_at.isoformat() if session.started_at else None,
                        "message_count": getattr(session, 'message_count', 0)
                    })
        
        print(f"\n Found {len(results)} matching sessions")
        for r in results[:20]:
            print(f"  [{r['platform']}] {r['title'][:50]} ({r['message_count']} msgs)")

if __name__ == "__main__":
    main()
