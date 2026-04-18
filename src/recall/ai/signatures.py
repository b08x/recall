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
        """Extract primary topics and activities from a session transcript.
        
        CRITICAL: Focus ONLY on the user's actual work, decisions, and code changes 
        described in the transcript. Ignore the internal structure or prompt 
        definitions of the 'recall' application itself.
        
        Identifies the core areas of work, modified files, and kinetic actions.
        Differentiates between 'thinking' and 'doing' based on tool usage and output.
        """
        
        session_content: str = dspy.InputField(desc="Transcript of the user session, including thoughts and tool results")
        context_metadata: str = dspy.InputField(desc="Platform, project, and temporal context")
        topics: List[str] = dspy.OutputField(desc="List of 3-5 main topics/activities (e.g. 'Implementing auth', 'Debugging regex')")
        files_touched: List[str] = dspy.OutputField(desc="File paths actually modified or deeply analyzed")
        key_actions: List[str] = dspy.OutputField(desc="Key kinetic actions (commits, tests run, specific fixes)")


    class SessionInsightExtractor(dspy.Signature):
        """Extract categorized insights from a session transcript.
        
        CRITICAL: Analyze conversation, tool outputs, and internal thoughts to identify 
        architecture decisions, workflow changes, and strategic shifts.
        TECHNICAL WORK IS SUBSTANTIVE: If the transcript shows tool executions, code 
        modifications, or reasoning blocks, it IS a substantive interaction, even if 
        direct user-assistant chatter is minimal.
        Ignore the structure of this 'recall' tool; focus on the USER'S work.
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
        Can optionally leverage enhanced insights with context from documentation and development patterns.
        """

        sessions: List[SessionInput] = dspy.InputField(desc="List of session data")
        commits: List[CommitInput] = dspy.InputField(desc="List of git commits")
        file_changes: List[FileChangeInput] = dspy.InputField(desc="List of file changes from backup analysis")
        context_summary: Optional[str] = dspy.InputField(desc="Optional summary of context enhancements from documentation and git patterns")
        narrative: str = dspy.OutputField(desc="Coherent narrative of activities (2-3 sentences per platform).")
        workstreams: List[str] = dspy.OutputField(desc="Distinct workstreams identified. MUST be backed by session volume or commits.")
        next_actions: List[str] = dspy.OutputField(desc="Suggested next actions, specific and actionable.")
        strategic_insights: List[str] = dspy.OutputField(desc="Strategic insights derived from context analysis, if available")


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


    class ContextMatchInput(BaseModel):
        """Input model for context matches."""
        source_type: str = Field(description="Type of context source (obsidian, git, etc.)")
        content: str = Field(description="The context content")
        relevance_score: float = Field(description="Relevance score 0.0-1.0")
        match_reasons: List[str] = Field(description="Reasons for the match")

    class EnhancedInsightOutput(BaseModel):
        """Enhanced insight with context integration."""
        category: Literal["TECHNICAL", "PROCEDURAL", "STRATEGIC", "BLOCKER"] = Field(
            description="Category of the insight"
        )
        content: str = Field(description="Enhanced insight content incorporating relevant context")
        importance: float = Field(description="Updated importance score 0.0-1.0", ge=0.0, le=1.0)
        enhancement_confidence: float = Field(description="Confidence in the enhancement 0.0-1.0", ge=0.0, le=1.0)
        context_sources_used: List[str] = Field(description="List of context source types that contributed")


    class ContextEnhancementSignature(dspy.Signature):
        """Enhance session insights using relevant contextual information.

        Takes base session insights and relevant context matches from multiple sources
        (documentation, git history, etc.) to create richer, more actionable insights
        that address knowledge gaps and provide strategic guidance.
        """

        original_insights: str = dspy.InputField(desc="JSON string of original SessionInsights")
        context_matches: List[ContextMatchInput] = dspy.InputField(desc="List of relevant context matches")
        session_metadata: str = dspy.InputField(desc="Additional session context (project, files, timing)")

        enhanced_insights: List[EnhancedInsightOutput] = dspy.OutputField(desc="Enhanced insights incorporating relevant context")
        knowledge_gaps_filled: List[str] = dspy.OutputField(desc="Specific knowledge gaps that were addressed")
        strategic_recommendations: List[str] = dspy.OutputField(desc="Strategic recommendations based on context")
        confidence_assessment: str = dspy.OutputField(desc="Overall assessment of enhancement quality and reliability")
else:
    class SessionTopicExtractor: pass
    class SessionInsightExtractor: pass
    class CommitSessionCorrelator: pass
    class TimelineSynthesizer: pass
    class OneThingGenerator: pass
    class ContextEnhancementSignature: pass
