# Phase 2: Deployment Instructions

**Status**: Ready to deploy  
**Time Required**: ~5 minutes  
**Risk Level**: Low (additive changes only)

---

## Pre-Deployment Checklist

- [ ] PostgreSQL running and accessible
- [ ] Gemini API key configured
- [ ] Backend services stopped (optional, but recommended)
- [ ] Database backup created (recommended)
- [ ] All Phase 2 files present

---

## Deployment Steps

### Step 1: Verify PostgreSQL Connection

```bash
# Test connection
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "SELECT version();"

# Expected output: PostgreSQL version info
```

### Step 2: Install pgvector Extension

```bash
# Connect to PostgreSQL
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres

# In psql shell:
CREATE EXTENSION IF NOT EXISTS vector;

# Verify installation
SELECT * FROM pg_extension WHERE extname = 'vector';

# Exit psql
\q
```

### Step 3: Apply Database Migration

```bash
# Apply migration
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres \
  -f /Users/aragossa/dzrprj/auroqa/auroqa/migrations/20251115_learning_system.sql

# Expected output: CREATE TABLE, CREATE INDEX, CREATE TRIGGER messages
```

### Step 4: Verify Tables Created

```bash
# Check tables
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "\dt patterns"

# Expected output:
# Schema |    Name    | Type  | Owner
# --------+------------+-------+----------
#  public | patterns   | table | postgres

# Check indexes
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "\di idx_patterns*"

# Check triggers
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "\dy"
```

### Step 5: Verify Vector Extension

```bash
# Check pgvector is working
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres -c "
SELECT 
    id, pattern_type, success_rate, 
    embedding::text as embedding_sample
FROM patterns 
LIMIT 1;
"

# Should return empty (no patterns yet) or show vector data
```

### Step 6: Copy Phase 2 Services to Backend

```bash
# Verify files exist
ls -la /Users/aragossa/dzrprj/auroqa/auroqa/Services/{EmbeddingGenerator,VectorStore,SimilaritySearch,PatternLibraryBuilder}.py

# Expected: All 4 files present
```

### Step 7: Restart Backend Services

```bash
# Stop backend (if running)
# Depends on your deployment method

# Restart backend
# This will load the new Phase 2 services

# Verify services loaded
curl http://localhost:8000/api/health

# Expected: 200 OK response
```

### Step 8: Test Phase 2 Services

```bash
# Run quick test
python3 << 'EOF'
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator
from auroqa.Services.VectorStore import VectorStore
from auroqa.Services.SimilaritySearch import SimilaritySearch
from auroqa.Services.PatternLibraryBuilder import PatternLibraryBuilder

print("✅ EmbeddingGenerator imported")
print("✅ VectorStore imported")
print("✅ SimilaritySearch imported")
print("✅ PatternLibraryBuilder imported")

# Test database connection
from auroqa.Utils.System import System
system = System()
conn = system.get_db_connection()
print("✅ Database connection successful")
system.return_connection(conn)

print("\n✅ All Phase 2 services ready!")
EOF
```

---

## Post-Deployment Verification

### 1. Database Schema Verification

```sql
-- Check patterns table
SELECT 
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name IN ('patterns', 'pattern_usage', 'similar_tests', 'few_shot_examples')
ORDER BY table_name, ordinal_position;
```

**Expected Columns**:
- patterns: id, pattern_type, pattern_data, embedding, success_rate, usage_count, tags, created_at, updated_at, last_used, created_by, client_id
- pattern_usage: id, pattern_id, test_case_id, step_number, success, execution_time_ms, error_message, created_at
- similar_tests: id, test_case_id_1, test_case_id_2, similarity_score, reason, created_at
- few_shot_examples: id, category, example_input, example_output, success_rate, usage_count, embedding, created_at, updated_at

### 2. Index Verification

```sql
-- Check indexes
SELECT 
    indexname,
    tablename
FROM pg_indexes
WHERE tablename IN ('patterns', 'pattern_usage', 'similar_tests', 'few_shot_examples')
ORDER BY tablename, indexname;
```

**Expected Indexes**:
- idx_patterns_type
- idx_patterns_client
- idx_patterns_created_by
- idx_patterns_success_rate
- idx_patterns_embedding (IVFFlat)
- idx_pattern_usage_pattern
- idx_pattern_usage_test_case
- idx_pattern_usage_success
- idx_pattern_usage_created
- idx_similar_tests_1
- idx_similar_tests_2
- idx_similar_tests_score
- idx_few_shot_examples_category
- idx_few_shot_examples_success

### 3. Trigger Verification

```sql
-- Check triggers
SELECT 
    trigger_name,
    event_object_table
FROM information_schema.triggers
WHERE event_object_table IN ('patterns', 'few_shot_examples')
ORDER BY event_object_table, trigger_name;
```

**Expected Triggers**:
- patterns_updated_at_trigger
- few_shot_examples_updated_at_trigger

### 4. Run Unit Tests

```bash
# Run all Phase 2 tests
pytest /Users/aragossa/dzrprj/auroqa/tests/test_phase2_learning_system.py -v

# Expected: All tests pass
```

---

## Rollback Procedure (If Needed)

```bash
# Drop Phase 2 tables (WARNING: This deletes all pattern data!)
PGPASSWORD=eYuUm57C! psql -h localhost -p 5432 -U postgres -d postgres << 'EOF'
DROP TABLE IF EXISTS pattern_usage CASCADE;
DROP TABLE IF EXISTS similar_tests CASCADE;
DROP TABLE IF EXISTS few_shot_examples CASCADE;
DROP TABLE IF EXISTS patterns CASCADE;
DROP EXTENSION IF EXISTS vector;
EOF

# Restart backend
# Services will continue working without Phase 2 features
```

---

## Performance Tuning (Optional)

### 1. Increase IVFFlat Index Size

```sql
-- For larger pattern libraries (>10,000 patterns)
REINDEX INDEX CONCURRENTLY idx_patterns_embedding;

-- Adjust IVFFlat parameters
ALTER INDEX idx_patterns_embedding SET (lists = 100);
```

### 2. Analyze Query Performance

```sql
-- Enable query analysis
EXPLAIN ANALYZE
SELECT * FROM patterns
WHERE embedding <=> '[0.1,0.2,...]'::vector
LIMIT 5;
```

### 3. Monitor Table Sizes

```sql
-- Check table sizes
SELECT 
    schemaname,
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size
FROM pg_tables
WHERE tablename IN ('patterns', 'pattern_usage', 'similar_tests', 'few_shot_examples')
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;
```

---

## Monitoring

### 1. Pattern Library Growth

```python
from auroqa.Services.PatternLibraryBuilder import PatternLibraryBuilder

builder = PatternLibraryBuilder()
stats = builder.get_library_stats()

print(f"Total patterns: {stats['total_patterns']}")
print(f"High confidence: {stats['high_confidence']}")
print(f"Total usage: {stats['total_usage']}")
print(f"By type: {stats['by_type']}")
```

### 2. Search Performance

```python
import time
from auroqa.Services.SimilaritySearch import SimilaritySearch

search = SimilaritySearch()

start = time.time()
results = search.find_similar_selectors(
    selector="//button[@id='submit']",
    top_k=5
)
elapsed = time.time() - start

print(f"Search time: {elapsed*1000:.2f}ms")
print(f"Results: {len(results)}")
```

### 3. Database Health

```sql
-- Check for bloat
SELECT 
    schemaname,
    tablename,
    round(100 * (CASE WHEN otta > 0 THEN sml_heap_size::float/otta 
        ELSE 0 END)::numeric, 2) AS table_bloat_ratio
FROM pg_stats_user_tables
WHERE schemaname = 'public'
ORDER BY table_bloat_ratio DESC;
```

---

## Troubleshooting

### Issue: pgvector Extension Not Found

```bash
# Install pgvector
sudo apt-get install postgresql-contrib

# Or in Docker
docker exec postgres_container apt-get install postgresql-contrib
```

### Issue: Embedding Dimension Mismatch

```python
# Verify Gemini embedding dimension
from auroqa.Services.EmbeddingGenerator import EmbeddingGenerator

gen = EmbeddingGenerator()
result = gen.embed_text("test")
print(f"Embedding dimension: {len(result.embedding)}")
# Should be 1536
```

### Issue: Slow Similarity Search

```sql
-- Rebuild IVFFlat index
REINDEX INDEX CONCURRENTLY idx_patterns_embedding;

-- Or check query plan
EXPLAIN ANALYZE
SELECT * FROM patterns
WHERE embedding <=> '[0.1,...]'::vector
LIMIT 5;
```

### Issue: Connection Pool Exhaustion

```python
# Check connection usage
from auroqa.Utils.System import System

system = System()
print(f"Pool size: {system.db_pool.size()}")
print(f"Checked out: {system.db_pool.checkedOut()}")
```

---

## Success Indicators

After deployment, you should see:

✅ All 4 Phase 2 tables created  
✅ All indexes created  
✅ All triggers created  
✅ pgvector extension installed  
✅ Unit tests passing  
✅ Services importable  
✅ Database connections working  
✅ No errors in logs  

---

## Next Steps

1. ✅ Deploy Phase 2 database schema
2. ✅ Verify all services working
3. ⏭️ Build initial pattern library
4. ⏭️ Integrate few-shot learning into AIHelper
5. ⏭️ Test end-to-end workflow

---

## Support

For deployment issues:

1. **Check logs**: `tail -f /var/log/auroqa.log`
2. **Verify database**: `psql -h localhost -p 5432 -U postgres -d postgres -c "\dt"`
3. **Test services**: `python3 -c "from auroqa.Services.VectorStore import VectorStore; print('OK')"`
4. **Run tests**: `pytest tests/test_phase2_learning_system.py -v`

---

## Deployment Checklist

- [ ] PostgreSQL running
- [ ] pgvector extension installed
- [ ] Database migration applied
- [ ] Tables verified
- [ ] Indexes verified
- [ ] Triggers verified
- [ ] Phase 2 services copied
- [ ] Backend restarted
- [ ] Services imported successfully
- [ ] Unit tests passing
- [ ] Database health checked
- [ ] Performance acceptable

**Status**: Ready for production deployment

