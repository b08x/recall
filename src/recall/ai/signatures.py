try:
    import dspy
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False

from typing import List, Dict, Optional, Any

if DSPY_AVAILABLE:
    class SessionTopicExtractor(dspy.Signature):
        """Extract primary topics and activities from session content.
        
        Analyzes session messages to identify the main areas of work,
        files that were touched, and key actions taken during the session.
        """
        
        session_content: str = dspy.InputField(desc="Combined text content from session messages, truncated to key exchanges")
        topics: List[str] = dspy.OutputField(desc="List of 3-5 main topics/activities in the session, prioritized by time spent")
        files_touched: List[str] = dspy.OutputField(desc="File paths mentioned or modified during the session")
        key_actions: List[str] = dspy.OutputField(desc="Key actions taken (commits, edits, tests run, bugs fixed)")


    class SessionInsightExtractor(dspy.Signature):
        """Extract categorized insights from session content.
        
        Analyzes session messages to find deeper insights like architectural 
        decisions, technical debt, blockers, or process improvements.
        """
        
        session_content: str = dspy.InputField(desc="Combined text content from session messages")
        insights: List[Dict[str, Any]] = dspy.OutputField(desc="List of objects with keys: category, content, importance (0.0-1.0)")
        primary_theme: str = dspy.OutputField(desc="The core theme of this specific insight set")
        confidence: float = dspy.OutputField(desc="Overall confidence in the insight extraction (0.0-1.0)")


    class CommitSessionCorrelator(dspy.Signature):
        """Correlate a git commit with the most relevant session(s).
        
        Uses commit message and changed files to find sessions that likely
        relate to this commit, enabling temporal correlation of work.
        """
        
        commit_message: str = dspy.InputField(desc="Git commit message")
        commit_files: List[str] = dspy.InputField(desc="Files changed in commit")
        session_summaries: List[str] = dspy.InputField(desc="List of session summaries to compare against, each with platform and title")
        relevant_session_indices: List[int] = dspy.OutputField(desc="Indices of most relevant sessions (0-based)")
        confidence_scores: List[float] = dspy.OutputField(desc="Confidence scores (0.0-1.0) for each match")


    class TimelineSynthesizer(dspy.Signature):
        """Synthesize a coherent narrative from multiple data sources.
        
        Combines sessions from multiple AI platforms, GitHub commits,
        and file changes into a unified timeline with actionable insights.
        
        STRICT REQUIREMENT: Identify workstreams ONLY if backed by a commit,
        multiple file changes, or substantial session content in the current window.
        Do NOT hype new directories or untracked artifacts (??) as "Initiatives."
        """
        
        sessions: List[Dict] = dspy.InputField(desc="List of session data with platform, summary, and timestamp")
        commits: List[Dict] = dspy.InputField(desc="List of git commits with message and sha")
        file_changes: List[Dict] = dspy.InputField(desc="List of file changes from backup analysis")
        narrative: str = dspy.OutputField(desc="Coherent narrative of activities (2-3 sentences per platform). Focus on kinetic energy (work done), not potential (new folders).")
        workstreams: List[str] = dspy.OutputField(desc="Distinct workstreams identified. MUST be backed by session volume or commits. Label untracked folders as 'Untracked Artifacts'.")
        next_actions: List[str] = dspy.OutputField(desc="Suggested next actions, specific and actionable. Derived from current momentum.")


    class OneThingGenerator(dspy.Signature):
        """Generate the single highest-leverage next action.
        
        Analyzes recent activity across platforms to determine the one
        action that would provide the most value given current momentum.
        """
        
        recent_activity: str = dspy.InputField(desc="Summary of recent work across platforms (3-5 sentences)")
        workstreams: List[str] = dspy.InputField(desc="Active workstreams identified")
        open_questions: List[str] = dspy.InputField(desc="Unresolved questions or blockers (empty list if none)")
        one_thing: str = dspy.OutputField(desc="Single most important next action (specific, actionable, complete sentence)")
        reasoning: str = dspy.OutputField(desc="Why this action is highest leverage (1-2 sentences)")
else:
    class SessionTopicExtractor: pass
    class SessionInsightExtractor: pass
    class CommitSessionCorrelator: pass
    class TimelineSynthesizer: pass
    class OneThingGenerator: pass
