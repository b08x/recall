try:
    import dspy
    from pydantic import BaseModel, Field
    DSPY_AVAILABLE = True
except ImportError:
    DSPY_AVAILABLE = False
    class BaseModel: pass
    def Field(*args, **kwargs): pass

from typing import List, Dict, Optional, Any, Literal

if DSPY_AVAILABLE:
    class Insight(BaseModel):
        """A single categorized insight from a session."""
        category: Literal["TECHNICAL", "PROCEDURAL", "STRATEGIC", "BLOCKER"] = Field(
            description="Category of the insight"
        )
        content: str = Field(description="Descriptive string (2-3 sentences)")
        importance: float = Field(description="Importance score between 0.0 and 1.0", ge=0.0, le=1.0)

    class SessionTopicExtractor(dspy.Signature):
        """Extract primary topics and activities from session content.
        
        Identifies the core areas of work, modified files, and kinetic actions.
        Differentiates between 'thinking' and 'doing' based on tool usage and output.
        """
        
        session_content: str = dspy.InputField(desc="Combined text content from session messages")
        context_metadata: str = dspy.InputField(desc="Platform, project, and temporal context")
        topics: List[str] = dspy.OutputField(desc="List of 3-5 main topics/activities, ranked by importance")
        files_touched: List[str] = dspy.OutputField(desc="File paths actually modified or deeply analyzed")
        key_actions: List[str] = dspy.OutputField(desc="Key kinetic actions (commits, tests run, specific fixes)")


    class SessionInsightExtractor(dspy.Signature):
        """Extract categorized insights from session content.
        
        Identifies deep patterns including architecture decisions, workflow changes,
        strategic shifts, and blockers.
        """
        
        session_content: str = dspy.InputField(desc="Combined text content from session messages")
        context_metadata: str = dspy.InputField(desc="Platform, project, and temporal context for this session")
        insights: List[Insight] = dspy.OutputField(desc="List of categorized insight objects")
        primary_theme: str = dspy.OutputField(desc="The core theme unifying these specific insights")
        confidence: float = dspy.OutputField(desc="Overall confidence in the insight extraction (0.0-1.0)")


    class SessionInput(BaseModel):
        platform: str
        summary: str
        timestamp: str

    class CommitInput(BaseModel):
        message: str
        sha: str

    class FileChangeInput(BaseModel):
        path: str
        change_type: str

    class TimelineSynthesizer(dspy.Signature):
        """Synthesize a coherent narrative from multiple data sources.
        
        Combines sessions from multiple AI platforms, GitHub commits,
        and file changes into a unified timeline with actionable insights.
        """
        
        sessions: List[SessionInput] = dspy.InputField(desc="List of session data")
        commits: List[CommitInput] = dspy.InputField(desc="List of git commits")
        file_changes: List[FileChangeInput] = dspy.InputField(desc="List of file changes from backup analysis")
        narrative: str = dspy.OutputField(desc="Coherent narrative of activities (2-3 sentences per platform).")
        workstreams: List[str] = dspy.OutputField(desc="Distinct workstreams identified. MUST be backed by session volume or commits.")
        next_actions: List[str] = dspy.OutputField(desc="Suggested next actions, specific and actionable.")


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
