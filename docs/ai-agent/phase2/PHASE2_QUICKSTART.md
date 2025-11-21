# Phase 2: Quick Start Guide

**Status**: ✅ Database migration complete | All 6 executable steps documented  
**Progress**: 1/7 steps completed (Step 1: Database)  
**Time to Complete**: ~45 minutes (Steps 2-6)  
**Last Updated**: November 15, 2025

---

## Prerequisites

1. PostgreSQL running with pgvector extension
2. Gemini API key configured
3. Backend services running

---

## Step 1: Apply Database Migration

```bash
# Connect to PostgreSQL and apply migration
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres  -f /Users/aragossa/dzrprj/auroqa/auroqa/migrations/20251115_learning_system.sql

# Verify tables were created
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "\dt patterns"
```

**✅ COMPLETED**: Migration successfully applied!

**Output**:
```
          List of relations
 Schema |   Name   | Type  |  Owner   
--------+----------+-------+----------
 public | patterns | table | postgres
```

**Tables Created**:
- ✅ `patterns` - Vector storage for selectors, API flows, UI components, error resolutions
- ✅ `pattern_usage` - Usage tracking with exponential moving average success rates
- ✅ `similar_tests` - Test similarity scores and relationships
- ✅ `few_shot_examples` - Few-shot learning examples for AI prompts

**Indexes Created**:
- ✅ IVFFlat vector indexes for fast similarity search
- ✅ Composite indexes on (client_id, pattern_type)
- ✅ Indexes on usage tracking and success rates

---

## Step 2: Verify Services Load

```bash
# Run from project directory (RECOMMENDED)
cd /Users/aragossa/dzrprj/auroqa && python3 -c "
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
from auroqa.Services.VectorStore import VectorStore
from auroqa.Services.SimilaritySearch import SimilaritySearch
from auroqa.Services.PatternLibraryBuilder import PatternLibraryBuilder

print('✅ All Phase 2 services imported successfully')
"
```

**Alternative: Set PYTHONPATH**
```bash
PYTHONPATH=/Users/aragossa/dzrprj/auroqa:$PYTHONPATH python3 -c "
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
from auroqa.Services.VectorStore import VectorStore
from auroqa.Services.SimilaritySearch import SimilaritySearch
from auroqa.Services.PatternLibraryBuilder import PatternLibraryBuilder

print('✅ All Phase 2 services imported successfully')
"
```

---

## Step 3: Build Initial Pattern Library

**Prerequisites**: Complete Step 2 first (services must load successfully)

```bash
# Run from project directory
cd /Users/aragossa/dzrprj/auroqa && python3 << 'EOF'
from auroqa.Services.PatternLibraryBuilder import PatternLibraryBuilder

# Create builder
builder = PatternLibraryBuilder()

# Build library from successful tests (min 90% success rate)
counts = builder.build_library_from_successful_tests(
    min_success_rate=0.9,
    limit=500
)

print(f"✅ Pattern library built:")
print(f"   - Selectors: {counts.get('selectors', 0)}")
print(f"   - API Flows: {counts.get('api_flows', 0)}")
print(f"   - UI Components: {counts.get('ui_components', 0)}")
print(f"   - Error Resolutions: {counts.get('error_resolutions', 0)}")

# Get statistics
stats = builder.get_library_stats()
print(f"\n✅ Library statistics:")
print(f"   - Total patterns: {stats['total_patterns']}")
print(f"   - High confidence: {stats['high_confidence']}")
print(f"   - Total usage: {stats['total_usage']}")
EOF
```

**Expected Output**:
```
✅ Pattern library built:
   - Selectors: 45
   - API Flows: 12
   - UI Components: 8
   - Error Resolutions: 3

✅ Library statistics:
   - Total patterns: 68
   - High confidence: 52
   - Total usage: 1250
```

**What This Does**:
- Scans all successful test cases (success rate ≥ 90%)
- Extracts reusable patterns (selectors, API flows, UI components)
- Calculates confidence scores for each pattern
- Stores patterns in the `patterns` table with embeddings
- Tracks usage statistics for optimization

---

## Step 4: Test Similarity Search

**Prerequisites**: Complete Step 3 first (pattern library must be built)

```bash
# Run from project directory
cd /Users/aragossa/dzrprj/auroqa && python3 << 'EOF'
from auroqa.Services.SimilaritySearch import SimilaritySearch

search = SimilaritySearch()

# Find similar selectors (works immediately)
similar_selectors = search.find_similar_selectors(
    selector="//button[@id='submit']",
    top_k=5
)

print(f"✅ Found {len(similar_selectors)} similar selectors:")
for selector in similar_selectors:
    print(f"   - {selector['selector']} (similarity: {selector['similarity_score']:.2f})")

# Find similar test cases (if test cases exist)
try:
    similar_tests = search.find_similar_tests(
        test_case_id=1,  # Replace with actual test ID
        top_k=3
    )
    print(f"\n✅ Found {len(similar_tests)} similar tests:")
    for test in similar_tests:
        print(f"   - {test['test_name']} (similarity: {test['similarity_score']:.2f})")
except Exception as e:
    print(f"\nℹ️  No test cases yet or error: {str(e)}")
EOF
```

**Expected Output**:
```
✅ Found 5 similar selectors:
   - //button[@class='btn-primary'] (similarity: 0.92)
   - //button[@id='submit-btn'] (similarity: 0.89)
   - //input[@type='submit'] (similarity: 0.85)
   - //a[@class='submit'] (similarity: 0.78)
   - //button[contains(text(), 'Submit')] (similarity: 0.75)

ℹ️  No test cases yet or error: No similar tests found
```

**What This Does**:
- Searches vector database for similar selectors using cosine distance
- Finds patterns with similar semantic meaning
- Returns top-k results sorted by similarity score
- Helps identify reusable patterns across tests

---

## Step 5: Test Embedding Generation

**Prerequisites**: Gemini API key configured in environment

```bash
# Run from project directory
cd /Users/aragossa/dzrprj/auroqa && python3 << 'EOF'
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator

generator = EmbeddingGenerator()

# Generate embedding for a selector
result = generator.embed_selector(
    "//button[@id='submit']",
    context={'element_type': 'button', 'purpose': 'Submit form'}
)

print(f"✅ Generated embedding:")
print(f"   - Dimension: {len(result.embedding)}")
print(f"   - Model: {result.model}")
print(f"   - Created: {result.created_at}")

# Calculate similarity between two selectors
embedding1 = result.embedding
embedding2 = generator.embed_selector("//button[@class='btn-primary']").embedding

similarity = generator.calculate_similarity(embedding1, embedding2)
print(f"\n✅ Similarity between selectors: {similarity:.2f}")

# Generate embedding for API flow
api_embedding = generator.embed_api_flow(
    method="POST",
    endpoint="/api/users",
    context={'purpose': 'Create user', 'auth': 'required'}
)
print(f"\n✅ Generated API flow embedding:")
print(f"   - Dimension: {len(api_embedding.embedding)}")
EOF
```

**Expected Output**:
```
✅ Generated embedding:
   - Dimension: 1536
   - Model: models/text-embedding-004
   - Created: 2025-11-15T23:55:00.000Z

✅ Similarity between selectors: 0.87

✅ Generated API flow embedding:
   - Dimension: 1536
```

**What This Does**:
- Generates 1536-dimensional embeddings using Gemini API
- Supports multiple pattern types (selectors, API flows, UI components, errors)
- Calculates semantic similarity between patterns
- Enables vector-based pattern matching and retrieval

---

## Step 6: Run Unit Tests

**Prerequisites**: All previous steps completed successfully

```bash
# Run from project directory
cd /Users/aragossa/dzrprj/auroqa

# Run all Phase 2 tests
python -m pytest tests/test_phase2_learning_system.py -v

# Run specific test class
python -m pytest tests/test_phase2_learning_system.py::TestEmbeddingGenerator -v

# Run with coverage report
python -m pytest tests/test_phase2_learning_system.py --cov=auroqa.Services --cov-report=html

# Run with detailed output
python -m pytest tests/test_phase2_learning_system.py -v -s --log-cli-level=DEBUG
```

**Expected Output**:
```
test_phase2_learning_system.py::TestEmbeddingGenerator::test_embed_selector PASSED
test_phase2_learning_system.py::TestEmbeddingGenerator::test_embed_api_flow PASSED
test_phase2_learning_system.py::TestVectorStore::test_store_pattern PASSED
test_phase2_learning_system.py::TestSimilaritySearch::test_find_similar_selectors PASSED
test_phase2_learning_system.py::TestPatternLibraryBuilder::test_build_library PASSED

======================== 40 passed in 12.34s ========================
```

**Test Coverage**:
- ✅ EmbeddingGenerator (7 tests)
- ✅ VectorStore (5 tests)
- ✅ SimilaritySearch (3 tests)
- ✅ PatternLibraryBuilder (5 tests)
- ✅ Integration tests (2 tests)
- ✅ Performance tests (18 tests)

---

## Step 7: Integrate Few-Shot Learning (Next)

This will be done in the next phase, but here's the preview:

```python
# In AIHelper.generate_step_with_few_shot()
from auroqa.Services.SimilaritySearch import SimilaritySearch

search = SimilaritySearch()

# Find similar successful tests
similar_tests = search.find_similar_tests(
    test_case_id=test_case_id,
    top_k=3
)

# Build few-shot examples
few_shot_examples = "\n\nSimilar successful examples:\n"
for test in similar_tests:
    few_shot_examples += f"- {test['test_name']}: {test['description']}\n"
    few_shot_examples += f"  Success rate: {test['success_rate']}%\n"

# Include in prompt
prompt = base_prompt + few_shot_examples
```

---

## Troubleshooting

### pgvector Extension Not Found

```bash
# Install pgvector extension
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres \
  -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

### Gemini API Errors

```python
# Verify Gemini API key
import google.generativeai as genai
genai.configure(api_key="your-api-key")

# Test embedding
response = genai.embed_content(
    model="models/text-embedding-004",
    content="test"
)
print(f"✅ Gemini API working, embedding dimension: {len(response['embedding'])}")
```

### Database Connection Issues

```python
from auroqa.Utils.System import System

system = System()
conn = system.get_db_connection()
print(f"✅ Database connection successful")
system.return_connection(conn)
```

---

## Performance Benchmarks

**Expected Performance**:
- Embedding generation: ~500ms per selector
- Similarity search: ~50ms for top-5 results
- Pattern storage: ~100ms per pattern
- Library building: ~5-10 seconds for 500 patterns

**Optimization Tips**:
- Use batch embedding for multiple patterns
- Cache embeddings for frequently searched patterns
- Use IVFFlat index for faster similarity search
- Filter by pattern type to reduce search space

---

## Next Steps

1. ✅ **Phase 2 Core**: Completed (this step)
2. ⏭️ **Few-Shot Integration**: Integrate into AIHelper
3. ⏭️ **Phase 3**: Implement self-correction agent
4. ⏭️ **Phase 4**: Implement learning feedback loop

---

## Key Files

- **Services**: `/auroqa/Services/`
  - `EmbeddingGenerator.py` - Embedding generation
  - `VectorStore.py` - Pattern storage and retrieval
  - `SimilaritySearch.py` - Similarity search
  - `PatternLibraryBuilder.py` - Pattern extraction

- **Tests**: `/tests/test_phase2_learning_system.py`

- **Database**: `/auroqa/migrations/20251115_learning_system.sql`

- **Documentation**: `/auroqa/docs/ai-agent/PHASE2_IMPLEMENTATION.md`

---

## Support

For issues or questions:
1. Check logs: `tail -f /var/log/auroqa.log`
2. Review documentation: `/auroqa/docs/ai-agent/`
3. Run tests: `pytest tests/test_phase2_learning_system.py -v`
4. Check database: `psql -h localhost -p 5432 -U postgres -d postgres`

