from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Dict, List, Optional, Any, Literal

@dataclass
class SessionUsage:
    """Unified usage metrics across providers."""
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0
    estimated_cost_usd: float = 0.0
    models_used: List[str] = None
    primary_model: str = "unknown"
    usage_source: str = "session"  # 'session' | 'message'

    def __post_init__(self):
        if self.models_used is None:
            self.models_used = []


@dataclass
class ToolCall:
    """Unified tool call structure."""
    id: str
    name: str
    input: Dict[str, Any]


@dataclass  
class ToolResult:
    """Unified tool result structure."""
    tool_use_id: str
    output: str


@dataclass
class ParsedMessage:
    """Unified message structure."""
    id: str
    session_id: str
    type: Literal['user', 'assistant', 'system']
    content: str
    thinking: Optional[str] = None
    tool_calls: List[ToolCall] = None
    tool_results: List[ToolResult] = None
    usage: Optional[Dict[str, Any]] = None
    timestamp: datetime = None
    parent_id: Optional[str] = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        if self.tool_results is None:
            self.tool_results = []


@dataclass
class ParsedNote:
    """Unified structure for notes (e.g., Obsidian)."""
    id: str
    title: str
    path: str
    content: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    tags: List[str] = None
    source: str = "obsidian"

    def __post_init__(self):
        if self.tags is None:
            self.tags = []


@dataclass
class ParsedSession:
    """Unified session schema matching TypeScript implementation."""
    id: str
    project_path: str
    project_name: str
    summary: Optional[str] = None
    generated_title: Optional[str] = None
    title_source: Optional[str] = None  # 'insight' | 'first_message'
    session_character: Optional[str] = None
    started_at: datetime = None
    ended_at: datetime = None
    message_count: int = 0
    user_message_count: int = 0
    assistant_message_count: int = 0
    tool_call_count: int = 0
    compact_count: int = 0
    auto_compact_count: int = 0
    slash_commands: List[str] = None
    git_branch: Optional[str] = None
    claude_version: Optional[str] = None
    source_tool: str = "unknown"
    usage: SessionUsage = None
    messages: List[ParsedMessage] = None

    def __post_init__(self):
        if self.slash_commands is None:
            self.slash_commands = []
        if self.messages is None:
            self.messages = []
        if self.usage is None:
            self.usage = SessionUsage()


@dataclass
class SessionAnalysis:
    """Structured analysis for a single session."""
    session_id: str
    topics: List[str]
    files_touched: List[str]
    key_actions: List[str]
    analyzed_at: datetime = None

    def __post_init__(self):
        if self.topics is None:
            self.topics = []
        if self.files_touched is None:
            self.files_touched = []
        if self.key_actions is None:
            self.key_actions = []


@dataclass
class SessionInsight:
    """A single categorized insight from a session."""
    category: str  # e.g., 'technical', 'procedural', 'strategic', 'blocker'
    content: str
    importance: float = 0.5  # 0.0 to 1.0


@dataclass
class SessionInsights:
    """Container for multiple insights and meta-analysis of a session."""
    session_id: str
    insights: List[SessionInsight]
    primary_theme: str
    confidence: float = 0.0
    generated_at: datetime = None

    def __post_init__(self):
        if self.insights is None:
            self.insights = []


@dataclass
class CorrelationResult:
    """Synthesized narrative across multiple sessions/sources."""
    id: str  # UUID or timestamp-based
    start_date: datetime
    end_date: datetime
    narrative: str
    workstreams: List[str]
    next_actions: List[str]
    one_thing: str
    one_thing_reasoning: str
    session_ids: List[str]  # References to sessions used in this synthesis
    created_at: datetime = None

    def __post_init__(self):
        if self.workstreams is None:
            self.workstreams = []
        if self.next_actions is None:
            self.next_actions = []
        if self.session_ids is None:
            self.session_ids = []


# Context Sources Models

@dataclass
class ContextMatch:
    """A piece of relevant context found by a ContextSource."""
    source_type: str  # e.g., "obsidian", "git", "slack"
    content: str
    relevance_score: float  # 0.0 to 1.0
    match_reasons: List[str]  # e.g., ["semantic_similarity", "file_overlap"]
    metadata: Dict[str, Any] = None  # Source-specific metadata

    def __post_init__(self):
        if self.match_reasons is None:
            self.match_reasons = []
        if self.metadata is None:
            self.metadata = {}


@dataclass
class ContextualInsight(SessionInsight):
    """Enhanced insight with supporting context."""
    supporting_context: List[ContextMatch] = None
    context_sources_used: List[str] = None
    enhancement_confidence: float = 0.0

    def __post_init__(self):
        if self.supporting_context is None:
            self.supporting_context = []
        if self.context_sources_used is None:
            self.context_sources_used = []


@dataclass
class EnhancedSessionInsights:
    """SessionInsights enhanced with contextual information."""
    session_id: str
    base_insights: SessionInsights  # Original insights before enhancement
    contextual_insights: List[ContextualInsight]
    knowledge_gaps_filled: List[str]  # Topics that got context support
    suggested_references: List[ContextMatch]  # Additional relevant materials
    enhancement_metadata: Dict[str, Any] = None  # Processing stats, sources used
    enhanced_at: datetime = None

    def __post_init__(self):
        if self.contextual_insights is None:
            self.contextual_insights = []
        if self.knowledge_gaps_filled is None:
            self.knowledge_gaps_filled = []
        if self.suggested_references is None:
            self.suggested_references = []
        if self.enhancement_metadata is None:
            self.enhancement_metadata = {}
        if self.enhanced_at is None:
            self.enhanced_at = datetime.now()
