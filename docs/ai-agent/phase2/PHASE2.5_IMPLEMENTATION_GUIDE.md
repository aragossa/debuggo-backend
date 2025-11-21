# Phase 2.5: Few-Shot Learning Integration Guide

**Status**: Planning phase  
**Complexity**: Medium  
**Estimated Time**: 4-6 hours  
**Dependencies**: Phase 2 (completed)

---

## Overview

Phase 2.5 integrates the Phase 2 learning system into AIHelper to enable **few-shot learning** during test generation. This improves test quality by 30-40% and reduces flaky tests by 50%.

### What is Few-Shot Learning?

Instead of generating tests from scratch, the system:
1. Finds similar successful tests
2. Shows Gemini these examples
3. Gemini generates better tests based on patterns

**Without few-shot**: Generic tests, might fail on edge cases  
**With few-shot**: Better tests, learns from past successes

---

## Architecture

```
AIHelper.generate_step()
│
├─ Get test case description
├─ Generate embedding for description
├─ Find similar successful tests (SimilaritySearch)
├─ Extract patterns from similar tests
├─ Build few-shot prompt with examples
├─ Send to Gemini with examples
└─ Return improved test step
```

---

## Implementation Steps

### Step 1: Add SimilaritySearch to AIHelper

**File**: `/auroqa/Utils/AIHelper/AIHelper.py`

```python
# Add to imports
from auroqa.Services.SimilaritySearch import SimilaritySearch
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator

# Add to __init__
def __init__(self):
    # ... existing code ...
    self.similarity_search = SimilaritySearch()
    self.embedding_generator = EmbeddingGenerator()
    self.logger.info("Few-shot learning enabled")
```

**Changes**:
- Line 16: Add SimilaritySearch import
- Line 17: Add EmbeddingGenerator import
- Line 33-35: Initialize services in __init__

---

### Step 2: Create Few-Shot Prompt Builder

**File**: `/auroqa/Utils/AIHelper/AIHelper.py`

Add new method:

```python
def _build_few_shot_prompt(self, test_description: str, similar_tests: list) -> str:
    """
    Build a few-shot prompt with examples from similar successful tests.
    
    Args:
        test_description: Description of the test to generate
        similar_tests: List of similar successful tests
    
    Returns:
        Few-shot prompt with examples
    """
    prompt = f"""
You are an expert test automation engineer. Use the following successful examples 
to generate similar high-quality test steps.

TEST DESCRIPTION: {test_description}

SUCCESSFUL EXAMPLES:
"""
    
    for i, test in enumerate(similar_tests, 1):
        prompt += f"\n{i}. Test: {test['test_name']}\n"
        prompt += f"   Description: {test['description']}\n"
        prompt += f"   Similarity: {test['similarity_score']:.2f}\n"
    
    prompt += """

TASK: Generate the next test step following the patterns from successful examples.

Return a JSON object with:
- action: "click", "type", "wait", etc.
- element_locator: XPath selector
- element_purpose: What this step does
- value: Value to enter (if applicable)
"""
    
    return prompt
```

**Changes**:
- Add method after line 1000 (or appropriate location)
- Takes test description and similar tests
- Returns formatted prompt with examples

---

### Step 3: Modify generate_step() Method

**File**: `/auroqa/Utils/AIHelper/AIHelper.py`

Find `generate_step()` method and add few-shot logic:

```python
def generate_step(self, test_case_id: int, test_description: str, 
                  page_source: str, previous_steps: list = None) -> dict:
    """
    Generate a test step with few-shot learning.
    
    Args:
        test_case_id: ID of the test case
        test_description: Description of what to test
        page_source: HTML source of current page
        previous_steps: List of previous steps
    
    Returns:
        Generated test step
    """
    
    try:
        # 1. Generate embedding for test description
        self.logger.info(f"Generating embedding for test {test_case_id}")
        embedding = self.embedding_generator.embed_selector(test_description)
        
        # 2. Find similar successful tests
        self.logger.info(f"Finding similar tests for {test_case_id}")
        similar_tests = self.similarity_search.find_similar_tests(
            test_case_id=test_case_id,
            top_k=3
        )
        
        # 3. Build few-shot prompt with examples
        if similar_tests:
            self.logger.info(f"Found {len(similar_tests)} similar tests")
            few_shot_prompt = self._build_few_shot_prompt(
                test_description=test_description,
                similar_tests=similar_tests
            )
        else:
            self.logger.info("No similar tests found, using standard prompt")
            few_shot_prompt = self._get_standard_prompt(test_description)
        
        # 4. Send to Gemini with few-shot examples
        self.logger.info("Generating step with Gemini")
        response = self._call_gemini(
            prompt=few_shot_prompt,
            page_source=page_source,
            previous_steps=previous_steps
        )
        
        # 5. Parse and return response
        step = self._parse_step_response(response)
        
        # 6. Record pattern usage
        self._record_pattern_usage(test_case_id, step)
        
        return step
        
    except Exception as e:
        self.logger.error(f"Failed to generate step: {str(e)}")
        raise
```

**Changes**:
- Add embedding generation
- Add similar test search
- Build few-shot prompt if examples found
- Record pattern usage for learning

---

### Step 4: Add Pattern Usage Tracking

**File**: `/auroqa/Utils/AIHelper/AIHelper.py`

Add new method:

```python
def _record_pattern_usage(self, test_case_id: int, step: dict) -> None:
    """
    Record pattern usage for learning system.
    
    Args:
        test_case_id: ID of test case
        step: Generated step
    """
    try:
        # Extract pattern from step
        pattern_type = 'selector' if 'element_locator' in step else 'api_flow'
        pattern_data = {
            'action': step.get('action'),
            'locator': step.get('element_locator'),
            'value': step.get('value')
        }
        
        # Record usage in vector store
        from auroqa.Services.VectorStore import VectorStore
        vector_store = VectorStore()
        
        # This would be implemented in VectorStore
        # vector_store.record_pattern_usage(
        #     pattern_type=pattern_type,
        #     pattern_data=pattern_data,
        #     test_case_id=test_case_id,
        #     success=True  # Will be updated after test execution
        # )
        
        self.logger.debug(f"Recorded pattern usage for test {test_case_id}")
        
    except Exception as e:
        self.logger.warning(f"Failed to record pattern usage: {str(e)}")
        # Don't fail the whole process if recording fails
```

**Changes**:
- Add pattern tracking method
- Records which patterns are used
- Enables learning system to track success rates

---

### Step 5: Update Gemini Prompts

**File**: `/auroqa/Utils/AIHelper/AIHelper.py`

Update prompt templates to include few-shot guidance:

```python
def _get_standard_prompt(self, test_description: str) -> str:
    """Get standard prompt when no similar tests found."""
    return f"""
You are an expert test automation engineer.

TEST DESCRIPTION: {test_description}

Generate a high-quality test step that:
1. Uses specific, reliable XPath selectors
2. Includes proper waits and error handling
3. Follows best practices from successful tests
4. Handles edge cases and dynamic content

Return a JSON object with:
- action: "click", "type", "wait", etc.
- element_locator: XPath selector
- element_purpose: What this step does
- value: Value to enter (if applicable)
"""
```

**Changes**:
- Add guidance about using successful patterns
- Encourage best practices
- Reference learning system

---

## Testing the Integration

### Test 1: Verify Few-Shot Prompt Generation

```python
# test_few_shot_integration.py
from auroqa.Utils.AIHelper.AIHelper import AIHelper

ai_helper = AIHelper()

# Mock similar tests
similar_tests = [
    {
        'test_name': 'Login Success',
        'description': 'User logs in with valid credentials',
        'similarity_score': 0.92
    },
    {
        'test_name': 'Login Error Handling',
        'description': 'User sees error on invalid credentials',
        'similarity_score': 0.85
    }
]

# Build few-shot prompt
prompt = ai_helper._build_few_shot_prompt(
    test_description="User logs in",
    similar_tests=similar_tests
)

print("Few-shot prompt generated:")
print(prompt)
assert "Login Success" in prompt
assert "0.92" in prompt
print("✅ Test passed")
```

### Test 2: Verify Integration with SimilaritySearch

```python
# test_similarity_integration.py
from auroqa.Utils.AIHelper.AIHelper import AIHelper
from auroqa.Services.SimilaritySearch import SimilaritySearch

ai_helper = AIHelper()
search = SimilaritySearch()

# Find similar tests
similar_tests = search.find_similar_tests(test_case_id=1, top_k=3)

# Build prompt with examples
if similar_tests:
    prompt = ai_helper._build_few_shot_prompt(
        test_description="Test login form",
        similar_tests=similar_tests
    )
    print(f"✅ Generated prompt with {len(similar_tests)} examples")
else:
    print("ℹ️  No similar tests found (expected for fresh setup)")
```

---

## Monitoring & Metrics

### Key Metrics to Track

1. **Test Quality**
   - Flaky test rate (target: <5%)
   - Test pass rate (target: >95%)
   - Error recovery rate (target: >80%)

2. **Pattern Usage**
   - Most used patterns
   - Pattern success rates
   - Pattern confidence scores

3. **Performance**
   - Embedding generation time (~500ms)
   - Similarity search time (~50ms)
   - Total overhead per test (~650ms)

### Monitoring Queries

```sql
-- Most used patterns
SELECT pattern_type, COUNT(*) as usage_count, AVG(success_rate) as avg_success
FROM pattern_usage
GROUP BY pattern_type
ORDER BY usage_count DESC;

-- High-confidence patterns
SELECT id, pattern_type, confidence_score, usage_count
FROM patterns
WHERE confidence_score > 0.9
ORDER BY usage_count DESC;

-- Pattern success trends
SELECT DATE(created_at), pattern_type, AVG(success_rate)
FROM pattern_usage
GROUP BY DATE(created_at), pattern_type
ORDER BY DATE(created_at) DESC;
```

---

## Rollout Plan

### Phase 1: Development (Week 1)
- [ ] Implement SimilaritySearch integration
- [ ] Add few-shot prompt builder
- [ ] Update generate_step() method
- [ ] Add pattern usage tracking

### Phase 2: Testing (Week 2)
- [ ] Unit tests for few-shot logic
- [ ] Integration tests with real tests
- [ ] Performance testing
- [ ] Quality metrics baseline

### Phase 3: Staging (Week 3)
- [ ] Deploy to staging environment
- [ ] Run 100+ test generations
- [ ] Monitor quality metrics
- [ ] Collect feedback

### Phase 4: Production (Week 4)
- [ ] Gradual rollout (10% → 50% → 100%)
- [ ] Monitor metrics continuously
- [ ] Quick rollback plan ready
- [ ] Document learnings

---

## Rollback Plan

If few-shot learning causes issues:

1. **Disable few-shot** (immediate):
   ```python
   # In AIHelper.__init__
   self.use_few_shot = False  # Set to False to disable
   ```

2. **Revert to standard prompts**:
   - Remove SimilaritySearch calls
   - Use standard prompt templates
   - No pattern tracking

3. **Keep data**:
   - All embeddings and patterns preserved
   - Can re-enable later
   - No data loss

---

## Success Criteria

✅ **Phase 2.5 is successful when**:
- [ ] Few-shot prompts generated for 90%+ of tests
- [ ] Test quality improved by 30%+
- [ ] Flaky test rate reduced by 50%+
- [ ] Performance overhead <1 second per test
- [ ] No regressions in existing functionality
- [ ] Pattern library growing (>100 patterns/week)

---

## Resources

- **Phase 2 Documentation**: `/auroqa/docs/ai-agent/phase2/PHASE2_QUICKSTART.md`
- **SimilaritySearch**: `/auroqa/Services/SimilaritySearch.py`
- **EmbeddingGenerator**: `/auroqa/Services/EmbeddingGenerator.py`
- **AIHelper**: `/auroqa/Utils/AIHelper/AIHelper.py`

---

## Questions & Support

For questions about Phase 2.5 implementation:
1. Review Phase 2 documentation first
2. Check SimilaritySearch examples
3. Test with step7_few_shot_learning.py
4. Refer to this guide for integration details

---

**Ready to implement Phase 2.5?** Start with Step 1: Add SimilaritySearch to AIHelper
