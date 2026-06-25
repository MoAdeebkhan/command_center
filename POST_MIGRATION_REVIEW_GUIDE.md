# Post-Migration Review Feature - Complete Guide

## 🎯 Overview

After your migration completes, you can run an **AI-powered deep review** to identify potential issues, verify correctness, and get actionable recommendations.

### What It Does

✅ **Critical Issue Detection**
- Formula translation errors
- Missing data source connections
- Semantic accuracy problems
- Data loss risks

✅ **Quality Assessment**
- Migration readiness evaluation
- Business logic preservation check
- Calculation accuracy validation
- Overall quality scoring

✅ **Actionable Recommendations**
- Specific items requiring manual review
- Testing checklist generation
- Optimization suggestions
- Best practice guidance

---

## 🤖 Supported AI Models

The system automatically selects the best available model, or you can specify one:

| Model | Size | Best For | Strengths |
|-------|------|----------|-----------|
| **qwen2.5-coder:32b** | 32B | Formula/Code Analysis | ⭐ BEST for formula correctness |
| **qwen2.5:32b** | 32B | General Review | Excellent reasoning |
| **llama3.3:70b** | 70B | Deep Analysis | Strong analytical capabilities |
| **gemma2:27b** | 27B | Technical Validation | Good for BI migrations |
| **llama3:latest** | 8B | Fallback | Fast, available everywhere |

### Model Selection Priority

1. **qwen2.5-coder:32b** - If you have it, use it! Best for formula review
2. **qwen2.5:32b** - Excellent alternative
3. **llama3.3:70b** - Very thorough but slower
4. **gemma2:27b** - Good balance
5. **llama3:latest** - Automatic fallback

---

## 📋 How to Use

### Option 1: API Endpoint (Recommended)

After migration completes, call the review endpoint:

```bash
# Auto-select best model
POST http://localhost:8080/api/jobs/{job_id}/review

# Or specify a model
POST http://localhost:8080/api/jobs/{job_id}/review?model_name=qwen2.5-coder:32b
```

**Example with curl:**
```bash
curl -X POST http://localhost:8080/api/jobs/YOUR_JOB_ID/review
```

**Example with Python:**
```python
import requests

job_id = "550e8400-e29b-41d4-a716-446655440000"

# Auto-select model
response = requests.post(f"http://localhost:8080/api/jobs/{job_id}/review")

# Or specify model
response = requests.post(
    f"http://localhost:8080/api/jobs/{job_id}/review",
    params={"model_name": "qwen2.5-coder:32b"}
)

analysis = response.json()
print(f"Critical Issues: {analysis['summary']['critical_issues']}")
print(f"Quality: {analysis['summary']['overall_quality']}")
```

### Option 2: Python Script

```python
from agents.post_migration_review import PostMigrationReviewAgent
import json

# Load your migration report
with open("migration_report.json") as f:
    report = json.load(f)

context = {
    "report": report,
    "source_meta": report.get("source_meta", {}),
    "translated_formulas": report.get("translated_formulas", []),
    "field_inventory": report.get("field_inventory", []),
}

# Run review (auto-selects best model)
agent = PostMigrationReviewAgent()
context = agent.run(context)

analysis = context["post_migration_review"]
print(json.dumps(analysis, indent=2))
```

---

## 📊 Review Output Structure

The review returns comprehensive JSON analysis:

```json
{
  "status": "review_completed",
  "model_used": "qwen2.5-coder:32b",
  "summary": {
    "critical_issues": 2,
    "warnings": 5,
    "recommendations": 8,
    "overall_quality": "good",
    "migration_ready": true
  },
  "analysis": {
    "critical_issues": [...],
    "warnings": [...],
    "recommendations": [...],
    "review_summary": {...},
    "semantic_validation": {...},
    "testing_checklist": [...]
  }
}
```

### Critical Issues Format

```json
{
  "issue_id": "missing-connection-sales",
  "category": "connection",
  "severity": "critical",
  "title": "Sales Table Missing Data Source",
  "description": "The Sales table has no connection information...",
  "affected_items": ["Sales", "Revenue"],
  "evidence": "No server, database, or filename found",
  "impact": "Table will appear empty in Power BI",
  "recommended_action": "Manually configure connection...",
  "can_auto_fix": false
}
```

### Warnings Format

```json
{
  "issue_id": "low-confidence-formula-xyz",
  "category": "formula",
  "severity": "warning",
  "title": "Formula ABC Translated with Low Confidence",
  "description": "Complex LOD expression may not translate accurately",
  "affected_items": ["Revenue by Region"],
  "recommended_action": "Manually verify formula produces correct results"
}
```

### Recommendations Format

```json
{
  "recommendation_id": "test-aggregations",
  "category": "testing",
  "priority": "high",
  "title": "Test All Aggregate Calculations",
  "description": "Verify SUM, AVG, COUNT formulas match source",
  "rationale": "Aggregation syntax differs between Tableau and DAX"
}
```

---

## 🔍 Review Categories

### Critical Issues
**Category Types:**
- `formula` - Formula translation errors
- `connection` - Missing/invalid data sources
- `data_loss` - Potential data loss scenarios
- `semantic` - Semantic accuracy problems

**Action Required:** Must fix before production use

### Warnings
**Category Types:**
- `performance` - Performance concerns
- `usability` - User experience issues
- `best_practice` - Deviations from best practices

**Action Required:** Should review and consider fixing

### Recommendations
**Category Types:**
- `optimization` - Performance improvements
- `testing` - Suggested tests
- `documentation` - Documentation needs

**Action Required:** Optional improvements

---

## 🎓 Best Practices

### When to Run Review

✅ **Always run review when:**
- Migration involves complex formulas
- Source has many calculated fields
- Business-critical data is involved
- Deployment to production

⚠️ **Consider skipping if:**
- Simple migration (few formulas)
- Test/development only
- Time-sensitive quick migration

### Model Selection Guidelines

**Use qwen2.5-coder:32b when:**
- Many formula translations
- Complex DAX/Tableau calculations
- Need highest accuracy

**Use llama3.3:70b when:**
- Need very thorough review
- Can afford longer processing time
- Complex business logic

**Use llama3:latest when:**
- Quick review needed
- Resource-constrained environment
- Simple migrations

### Acting on Review Results

**Critical Issues:**
1. Read the description and evidence
2. Check affected items
3. Follow recommended action
4. Verify fix before deployment

**Warnings:**
1. Prioritize by severity and impact
2. Review affected items
3. Decide if fix is needed now or later
4. Document decision if deferring

**Recommendations:**
1. Add to testing checklist
2. Consider for next iteration
3. Document for knowledge base

---

## 📈 Example Workflow

### Complete Migration Review Process

```bash
# 1. Upload and migrate
POST /api/jobs (upload .twbx file)
# Wait for migration to complete

# 2. Check available models
GET /api/ollama/models

# 3. Run post-migration review
POST /api/jobs/{job_id}/review?model_name=qwen2.5-coder:32b

# 4. Get review results
GET /api/jobs/{job_id}
# Check report.post_migration_review section

# 5. Address critical issues
# - Fix data source connections
# - Verify formula translations
# - Test affected items

# 6. Re-run review if needed
POST /api/jobs/{job_id}/review

# 7. Download final output
GET /api/jobs/{job_id}/download
```

---

## 🛠️ Troubleshooting

### "No preferred models available"
**Solution:** The system falls back to llama3:latest. To use better models:
```bash
# Pull recommended models
ollama pull qwen2.5-coder:32b
ollama pull qwen2.5:32b
ollama pull llama3.3:70b
```

### "Review timeout"
**Solution:** Larger models take longer. Try:
1. Use a smaller model (llama3:latest)
2. Increase OLLAMA_TIMEOUT in base.py
3. Run review separately, not inline

### "Model not found: XYZ"
**Solution:** Check available models:
```bash
GET /api/ollama/models
```
Use a model from the returned list.

### "Review shows no issues but I see problems"
**Solution:** 
1. The AI might miss edge cases - manual review is still important
2. Try a different model (qwen2.5-coder is best for formulas)
3. Check the raw AI log in the database for details

---

## 🔄 Integration with CI/CD

### Automated Review in Pipeline

```yaml
# Example GitHub Actions workflow
name: Migration Review

on:
  migration_complete:
    
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - name: Run Post-Migration Review
        run: |
          REVIEW=$(curl -X POST http://localhost:8080/api/jobs/$JOB_ID/review)
          CRITICAL=$(echo $REVIEW | jq '.summary.critical_issues')
          
          if [ "$CRITICAL" -gt "0" ]; then
            echo "Critical issues found: $CRITICAL"
            exit 1
          fi
```

---

## 📝 Review Report Components

### 1. Review Summary
- Overall quality assessment
- Migration readiness status
- Key concerns highlight
- Items requiring manual review

### 2. Semantic Validation
- Business logic preservation
- Data relationship integrity
- Calculation accuracy assessment

### 3. Testing Checklist
- Prioritized test cases
- Test type categorization
- Step-by-step test procedures

---

## 🎯 Success Metrics

Track these metrics to measure review effectiveness:

- **Issue Detection Rate**: % of real issues caught by AI
- **False Positive Rate**: % of flagged items that aren't actually issues
- **Time Saved**: Hours saved vs manual review
- **Production Incidents**: Issues found in production that review missed

---

## 🔮 Future Enhancements

Planned improvements:
- [ ] Auto-fix for common issues
- [ ] Integration with Power BI REST API for automated testing
- [ ] Historical trend analysis
- [ ] Custom review rules/policies
- [ ] Multi-model ensemble review

---

## 📚 Additional Resources

- **API Documentation**: http://localhost:8080/docs
- **Model Performance**: Check Ollama documentation
- **Formula Reference**: See DATASOURCE_CONNECTION_FIX_SUMMARY.md
- **Manual Review Guide**: DATA_SOURCE_MANUAL_FIX_GUIDE.md

---

**Questions?** Contact your migration team or refer to the API documentation at `/docs`.
