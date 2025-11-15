# AuroQA AI Agent Transformation Plan - Part 1

**Objective**: Transform AuroQA from prompt-based to true AI agent with self-correction and learning.

**Timeline**: 8 weeks | **Priority**: High | **Target Stability**: 70% → 95%+

---

## Current State Analysis

### Pain Points
- Single-shot generation: No feedback loops
- No validation: Hardcoded selectors fail silently
- No learning: Repeats same mistakes
- Low stability: ~70% first-time success
- No recovery: Manual intervention needed
- No reasoning traces: Can't debug decisions

### Success Metrics to Improve
- First-time success: 70% → 95%+
- Manual intervention: 30% → 5%
- Time to fix: 30 min → 5 min
- Consistency: Variable → Predictable

---

## Phase 1: Foundation (Weeks 1-2) - completed -

### 1.1 Validation Agent - completed -
**File**: `/auroqa/Services/ValidationAgent.py`

**Validates**:
- Selectors exist in HTML
- Actions match element types
- Data types are correct
- No hardcoded values
- API schemas valid

**Key Methods**:
```python
class ValidationAgent:
    def validate_selector(selector, html, by_type) → ValidationResult
    def validate_action(action, element_type) → ValidationResult
    def validate_data_type(value, expected_type) → ValidationResult
    def validate_no_hardcoding(value, context) → ValidationResult
    def validate_api_schema(request, schema) → ValidationResult
```

**ValidationResult**:
```python
@dataclass
class ValidationResult:
    is_valid: bool
    confidence: float  # 0-100
    issues: List[str]
    suggestions: List[str]
    severity: str  # 'critical', 'warning', 'info'
```

**Integration**: After step generation, before storage

### 1.2 Execution Feedback Collector - completed -
**File**: `/auroqa/Services/ExecutionFeedbackCollector.py`

**Failure Categories**:
- `selector_not_found`: Element selector didn't match
- `element_not_clickable`: Element exists but not clickable
- `wrong_element_clicked`: Clicked wrong element
- `data_type_mismatch`: Data type doesn't match field
- `api_error`: API returned error status
- `timeout`: Operation timed out
- `stale_element`: Element became stale
- `hardcoded_value_failed`: Hardcoded value doesn't exist

**Feedback Format for AI**:
```
Step 11 failed: "Element not found"
Attempted: //tr[1]//a[@title='Delete']
Context: Table sorted descending, new item at index 8
Suggestion: Use variable: //tr[td/a[text()='%unique_name:Group%']]//a[@title='Delete']
Similar success: Test 1847 step 9 (95% confidence)
```

### 1.3 Confidence Scoring System - completed -
**File**: `/auroqa/Services/ConfidenceScorer.py`

**Scoring Factors** (0-100):
- Selector specificity: 10 pts
- Action appropriateness: 15 pts
- Data type correctness: 15 pts
- No hardcoding: 15 pts
- Pattern match: 20 pts
- Historical success: 25 pts

**Thresholds**:
- 90-100: Execute immediately
- 70-89: Execute with monitoring
- 50-69: Validate before execution
- <50: Regenerate with feedback

### 1.4 Retry Mechanism with Feedback - completed - 

**Logic**:
```python
for attempt in range(max_retries):
    step = ai_helper.generate_step(prompt + feedback)
    validation = validator.validate_step(step)
    
    if validation.is_valid and confidence > 70:
        return step
    
    feedback = f"\nPrevious failed: {validation.issues}\n"
    feedback += f"Suggestions: {validation.suggestions}\n"
```

### 1.5 Database Schema - Phase 1 - completed -

**Migration**: `/auroqa/migrations/20251115_agent_foundation.sql`

```sql
CREATE TABLE validation_results (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id),
    step_number INTEGER NOT NULL,
    is_valid BOOLEAN NOT NULL,
    confidence FLOAT NOT NULL,
    issues TEXT[],
    suggestions TEXT[],
    severity VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE execution_feedback (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL,
    step_number INTEGER NOT NULL,
    failure_type VARCHAR(50),
    error_message TEXT,
    error_context JSONB,
    ai_feedback TEXT,
    resolution_suggested TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE confidence_scores (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL,
    step_number INTEGER NOT NULL,
    selector_score FLOAT,
    action_score FLOAT,
    data_score FLOAT,
    pattern_score FLOAT,
    overall_score FLOAT,
    threshold_met BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE retry_attempts (
    id SERIAL PRIMARY KEY,
    test_case_id INTEGER NOT NULL,
    step_number INTEGER NOT NULL,
    attempt_number INTEGER,
    feedback_provided TEXT,
    result_valid BOOLEAN,
    result_confidence FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_validation_results_test_case ON validation_results(test_case_id);
CREATE INDEX idx_execution_feedback_test_case ON execution_feedback(test_case_id);
CREATE INDEX idx_confidence_scores_test_case ON confidence_scores(test_case_id);
```

### 1.6 Phase 1 Deliverables - completed -
- [ ] ValidationAgent service
- [ ] ExecutionFeedbackCollector service
- [ ] ConfidenceScorer service
- [ ] Retry mechanism integrated
- [ ] Database migration applied
- [ ] Unit tests for validation
- [ ] Integration tests for feedback loop
- [ ] Monitoring dashboard
- [ ] Documentation

- [x] ### 1.7 Phase 1 Success Metrics
- Validation catches 90%+ invalid steps
- Confidence scores correlate with success (>0.85)
- Retry improves success rate by 15-20%
- No performance degradation (<100ms per validation)

---

## Phase 2: Learning System (Weeks 3-4)

### 2.1 Vector Database Setup

**Technology**: PostgreSQL pgvector (start simple, migrate to Pinecone if needed)

**File**: `/auroqa/Services/VectorStore.py`

**Pattern Types**:
1. Selectors: XPath/CSS with success rates
2. API Flows: Common interaction patterns
3. Error Resolutions: How to fix errors
4. UI Components: How to interact with elements

**Key Methods**:
```python
class VectorStore:
    def store_pattern(pattern_type, pattern_data, embedding) → str
    def search_similar_patterns(query_embedding, top_k=5) → List[Pattern]
    def update_pattern_success_rate(pattern_id, success) → None
    def get_patterns_by_type(pattern_type, min_success_rate=0.7) → List[Pattern]
```

### 2.2 Embedding Generation
**File**: `/auroqa/Services/EmbeddingGenerator.py`

Use Gemini's embedding API or open-source models

**Key Methods**:
```python
class EmbeddingGenerator:
    def embed_selector(selector, context) → List[float]
    def embed_api_flow(flow) → List[float]
    def embed_error_resolution(error, resolution) → List[float]
    def embed_ui_component(component_type, interaction) → List[float]
```

### 2.3 Few-Shot Learning

**Approach**:
1. Search for similar successful tests
2. Include 2-3 examples in prompt
3. Show AI what worked in similar scenarios

**Implementation**:
```python
def generate_step_with_few_shot(test_case_id, step_description, html_context):
    similar_tests = vector_store.search_similar_tests(
        query=test_case_id,
        top_k=3,
        min_success_rate=0.9
    )
    
    few_shot_examples = "\n\nSimilar successful examples:\n"
    for test in similar_tests:
        few_shot_examples += f"- {test['step_description']}\n"
        few_shot_examples += f"  Generated: {test['generated_step']}\n"
        few_shot_examples += f"  Success: {test['success_rate']}%\n"
    
    prompt = base_prompt + few_shot_examples
    return ai_helper.generate_step(prompt)
```

### 2.4 Pattern Library Builder
**File**: `/auroqa/Services/PatternLibraryBuilder.py`

**Responsibilities**:
- Extract patterns from successful tests
- Categorize and tag
- Calculate success rates
- Generate embeddings
- Store in vector DB

**Pattern Structure**:
```python
@dataclass
class Pattern:
    id: str
    pattern_type: str  # 'selector', 'api_flow', 'error_resolution'
    pattern_data: dict
    embedding: List[float]
    success_rate: float
    usage_count: int
    tags: List[str]
    created_at: datetime
    last_used: datetime
```

### 2.5 Database Schema - Phase 2

**Migration**: `/auroqa/migrations/20251120_learning_system.sql`

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE patterns (
    id SERIAL PRIMARY KEY,
    pattern_type VARCHAR(50) NOT NULL,
    pattern_data JSONB NOT NULL,
    embedding vector(1536),
    success_rate FLOAT DEFAULT 0.5,
    usage_count INTEGER DEFAULT 0,
    tags TEXT[],
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used TIMESTAMP,
    created_by INTEGER REFERENCES users(id)
);

CREATE TABLE pattern_usage (
    id SERIAL PRIMARY KEY,
    pattern_id INTEGER NOT NULL REFERENCES patterns(id),
    test_case_id INTEGER NOT NULL REFERENCES test_cases(id),
    step_number INTEGER,
    success BOOLEAN,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE similar_tests (
    id SERIAL PRIMARY KEY,
    test_case_id_1 INTEGER NOT NULL REFERENCES test_cases(id),
    test_case_id_2 INTEGER NOT NULL REFERENCES test_cases(id),
    similarity_score FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE few_shot_examples (
    id SERIAL PRIMARY KEY,
    category VARCHAR(50),
    example_input TEXT,
    example_output JSONB,
    success_rate FLOAT,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_patterns_type ON patterns(pattern_type);
CREATE INDEX idx_patterns_embedding ON patterns USING ivfflat (embedding vector_cosine_ops);
CREATE INDEX idx_pattern_usage_pattern ON pattern_usage(pattern_id);
```

### 2.6 Similarity Search
**File**: `/auroqa/Services/SimilaritySearch.py`

**Key Methods**:
```python
class SimilaritySearch:
    def find_similar_selectors(selector, top_k=5) → List[Pattern]
    def find_similar_api_flows(flow, top_k=5) → List[Pattern]
    def find_similar_tests(test_case_id, top_k=3) → List[dict]
    def find_error_resolutions(error_type, top_k=5) → List[Pattern]
    def calculate_similarity(embedding1, embedding2) → float
```

### 2.7 Phase 2 Deliverables
- [ ] Vector database setup
- [ ] EmbeddingGenerator service
- [ ] VectorStore service
- [ ] PatternLibraryBuilder service
- [ ] SimilaritySearch service
- [ ] Few-shot learning integrated
- [ ] Database migration applied
- [ ] Pattern extraction from existing tests
- [ ] Similarity search tests
- [ ] Pattern library dashboard

### 2.8 Phase 2 Success Metrics
- Few-shot improves success rate by 20-25%
- Pattern library has 500+ high-quality patterns
- Similarity search returns relevant examples 90%+
- Pattern success rates tracked and improving

---

## Next: See Part 2 for Phases 3-4
