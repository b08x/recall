# Context Sources Architecture Design

## Overview
Convert Obsidian and GitHub providers into pluggable ContextSource implementations that enhance SessionInsights with relevant documentation and development context through a two-stage analysis process.

## Core Architecture

### Plugin-Style ContextSource Interface
```python
class ContextSource(ABC):
    @abstractmethod
    async def find_relevant_content(self, insights: SessionInsights, 
                                   session_context: Dict) -> List[ContextMatch]
    
class ContextMatch:
    source_type: str  # "obsidian", "git", "slack", etc.
    content: str
    relevance_score: float
    match_reasons: List[str]  # ["semantic_similarity", "file_overlap", etc.]
```

### Two-Stage Analysis Process
1. **Stage 1: Initial Analysis** - Current `SessionInsightExtractor` generates base insights from session content
2. **Stage 2: Contextual Enhancement** (optional) - `ContextEnhancementModule` enriches insights using ContextSource plugins

## Data Flow

```
Sessions → SessionInsights → [Optional] ContextEnhancement → EnhancedSessionInsights
```

### Enhanced Pipeline
1. Extract sessions via existing providers (Gemini, Claude, etc.)
2. Analyze sessions → generate base `SessionInsights`
3. **Enhance** (optional) → query ContextSources → produce `EnhancedSessionInsights`

## Provider Migration

### Obsidian Context Source
```python
class ObsidianContextSource(ContextSource):
    async def find_relevant_content(self, insights: SessionInsights, 
                                   session_context: Dict) -> List[ContextMatch]:
        # Hybrid matching: semantic + keyword + temporal + file-path
        # Match insights.topics, insights.primary_theme against:
        # - Note titles, tags, content embeddings
        # - Recent note modifications
        # - File path overlaps
```

### Git Context Source  
```python
class GitContextSource(ContextSource):
    async def find_relevant_content(self, insights: SessionInsights,
                                   session_context: Dict) -> List[ContextMatch]:
        # Match against:
        # - files_touched in insights
        # - Commit messages containing similar topics
        # - Branch patterns and recent development activity
```

## Enhanced Data Models

### Extended Insights Structure
```python
@dataclass
class ContextualInsight(SessionInsight):
    """Enhanced insight with supporting context."""
    supporting_context: List[ContextMatch] = None
    context_sources_used: List[str] = None
    enhancement_confidence: float = 0.0

@dataclass  
class EnhancedSessionInsights(SessionInsights):
    """SessionInsights enhanced with contextual information."""
    contextual_insights: List[ContextualInsight]
    knowledge_gaps_filled: List[str]  # Topics that got context support
    suggested_references: List[ContextMatch]  # Additional relevant materials
    enhancement_metadata: Dict[str, Any]  # Processing stats, sources used
```

### AI Enhancement Module
```python
class ContextEnhancementSignature(dspy.Signature):
    """Enhance session insights using relevant contextual information."""
    
    original_insights: SessionInsights = dspy.InputField()
    context_matches: List[ContextMatch] = dspy.InputField()
    session_metadata: str = dspy.InputField()
    
    enhanced_insights: List[ContextualInsight] = dspy.OutputField()
    knowledge_gaps_filled: List[str] = dspy.OutputField()
    strategic_recommendations: List[str] = dspy.OutputField()
```

## Implementation Architecture

### Context Source Manager
```python
class ContextSourceManager:
    def __init__(self, settings: Settings):
        self.sources: Dict[str, ContextSource] = {}
        self._load_configured_sources(settings.context_sources)
    
    async def enhance_insights(self, insights: SessionInsights, 
                              session_context: Dict) -> EnhancedSessionInsights:
        # Parallel context gathering with timeouts
        # Graceful degradation if sources fail  
        # Relevance scoring and filtering
```

### Configuration
```python
# In Settings
enable_context_enhancement: bool = True
context_sources: List[str] = ["obsidian", "git"] 
max_context_matches_per_source: int = 3
context_relevance_threshold: float = 0.7
```

## Hybrid Matching Strategy

### Multi-dimensional Relevance Scoring
1. **Semantic Matching** - Embeddings/vector similarity between session content and context
2. **Keyword/Topic Overlap** - Match extracted topics with note titles, tags, commit messages
3. **Temporal Correlation** - Recent notes/commits get higher relevance scores
4. **File Path Matching** - Strong signals for file-based correlations
5. **Weighted Combination** - Configurable weights for different matching strategies

## Error Handling & Performance

### Graceful Degradation
- Context source failures don't break insight generation
- Network timeouts for git/obsidian operations (30s max)
- Fallback to original insights if enhancement fails
- Detailed logging for context source performance

### Performance Optimizations
- Async context source queries for parallelism
- Embedding caching for semantic matching
- Configurable timeouts and result limits
- Optional background enhancement for real-time use

## Migration Strategy

### Phase 1: Core Infrastructure
- Implement ContextSource interface and ContextMatch models
- Create ContextSourceManager with basic registry
- Add optional enhancement flag to existing analysis pipeline

### Phase 2: Initial Context Sources
- Convert ObsidianProvider → ObsidianContextSource
- Convert LocalGitProvider → GitContextSource  
- Implement basic hybrid matching

### Phase 3: AI Enhancement
- Create ContextEnhancementModule and DSPy signature
- Integrate with existing SessionInsight pipeline
- Add EnhancedSessionInsights models

### Phase 4: Optimization & Extension
- Performance tuning and caching
- Additional context sources (Slack, Jira, etc.)
- Advanced matching algorithms

## Testing Strategy

### Unit Testing
- Mock context sources for isolated testing
- Test hybrid matching algorithms
- Verify graceful degradation

### Integration Testing  
- Test with sample Obsidian vault and git repositories
- End-to-end enhancement pipeline testing
- Performance benchmarks with large datasets

### Quality Assurance
- A/B testing framework for enhancement quality
- Human evaluation of context relevance
- Monitoring context source performance

## Benefits

### Immediate Value
- Richer insights with supporting documentation
- Automated discovery of related development patterns
- Knowledge gap identification and filling

### Future Extensibility  
- Plugin architecture supports unlimited context sources
- Clean separation of concerns
- Backward compatibility maintained

### User Control
- Optional enhancement (performance vs. richness trade-off)  
- Configurable relevance thresholds
- Source-specific enable/disable controls