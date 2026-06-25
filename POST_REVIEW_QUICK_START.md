# Post-Migration Review - Quick Start

## 🚀 Quick Commands

### 1. Check Available Models
```bash
curl http://localhost:8080/api/ollama/models
```

### 2. Run Review (Auto-Select Best Model)
```bash
curl -X POST http://localhost:8080/api/jobs/YOUR_JOB_ID/review
```

### 3. Run Review with Specific Model
```bash
# Best for formulas
curl -X POST "http://localhost:8080/api/jobs/YOUR_JOB_ID/review?model_name=qwen2.5-coder:32b"

# Good alternative
curl -X POST "http://localhost:8080/api/jobs/YOUR_JOB_ID/review?model_name=qwen2.5:32b"

# Thorough but slower
curl -X POST "http://localhost:8080/api/jobs/YOUR_JOB_ID/review?model_name=llama3.3:70b"
```

### 4. Get Review Results
```bash
curl http://localhost:8080/api/jobs/YOUR_JOB_ID | jq '.report.post_migration_review'
```

---

## 🎯 When to Use Which Model

| Scenario | Recommended Model | Why |
|----------|------------------|-----|
| **Complex formulas** | qwen2.5-coder:32b | Best code/formula analysis |
| **General review** | qwen2.5:32b | Excellent reasoning |
| **Deep analysis** | llama3.3:70b | Most thorough |
| **Quick review** | llama3:latest | Fast, always available |
| **Balance** | gemma2:27b | Good performance/speed |

---

## 📊 What You Get

### Summary
```json
{
  "critical_issues": 2,        // Must fix before production
  "warnings": 5,               // Should review
  "recommendations": 8,        // Nice to have
  "overall_quality": "good",   // excellent|good|fair|poor
  "migration_ready": true      // Ready for production?
}
```

### Critical Issues
- Formula translation errors
- Missing data source connections
- Data loss risks
- Semantic problems

### Warnings  
- Performance concerns
- Usability issues
- Best practice violations

### Recommendations
- Testing checklist
- Optimization suggestions
- Documentation needs

---

## 🔍 Common Issues Found

### 1. Missing Data Source Connections
**Issue:** Tables have no server/database info  
**Impact:** Data won't load in Power BI  
**Fix:** Use DATA_SOURCE_MANUAL_FIX_GUIDE.md

### 2. Low-Confidence Formula Translations
**Issue:** Complex formulas might not be accurate  
**Impact:** Wrong calculations  
**Fix:** Manually verify formulas

### 3. Semantic Accuracy
**Issue:** Translation is syntactically correct but semantically wrong  
**Impact:** Produces incorrect results  
**Fix:** Test with known data

---

## ⚡ Installation (If Models Missing)

```bash
# Install best model for review
ollama pull qwen2.5-coder:32b

# Or alternatives
ollama pull qwen2.5:32b
ollama pull llama3.3:70b
ollama pull gemma2:27b
```

---

## 🎬 Example Workflow

```bash
# 1. Upload and migrate file
JOB_ID=$(curl -X POST -F "file=@Sales_Dashboard.twbx" \
  http://localhost:8080/api/jobs | jq -r '.job_id')

echo "Job ID: $JOB_ID"

# 2. Wait for migration to complete
while true; do
  STATUS=$(curl -s http://localhost:8080/api/jobs/$JOB_ID | jq -r '.status')
  echo "Status: $STATUS"
  [[ "$STATUS" == "completed" ]] && break
  sleep 5
done

# 3. Run post-migration review
REVIEW=$(curl -X POST http://localhost:8080/api/jobs/$JOB_ID/review)

# 4. Check results
echo $REVIEW | jq '.summary'

# 5. Get critical issues
echo $REVIEW | jq '.analysis.critical_issues'

# 6. Download if ready
READY=$(echo $REVIEW | jq -r '.summary.migration_ready')
if [[ "$READY" == "true" ]]; then
  curl http://localhost:8080/api/jobs/$JOB_ID/download -o migration_output.zip
else
  echo "Fix critical issues before downloading"
fi
```

---

## 🐛 Troubleshooting

### Error: "Job must be completed first"
**Solution:** Wait for migration to finish, then run review

### Error: "Model not found: XYZ"
**Solution:** Check available models with `/api/ollama/models`

### Timeout
**Solution:** Use smaller model (llama3:latest) or increase timeout

### No issues found but problems exist
**Solution:** 
1. Try qwen2.5-coder:32b (best for formulas)
2. Manual review is still important
3. Check AI log for raw output

---

## 📝 Response Example

```json
{
  "status": "review_completed",
  "model_used": "qwen2.5-coder:32b",
  "summary": {
    "critical_issues": 1,
    "warnings": 3,
    "recommendations": 5,
    "overall_quality": "good",
    "migration_ready": true
  },
  "analysis": {
    "critical_issues": [
      {
        "issue_id": "missing-connection-sales",
        "category": "connection",
        "severity": "critical",
        "title": "Sales Table Missing Connection",
        "description": "No server or database info found",
        "affected_items": ["Sales"],
        "impact": "Table will be empty in Power BI",
        "recommended_action": "Manually configure data source",
        "can_auto_fix": false
      }
    ],
    "review_summary": {
      "overall_quality": "good",
      "migration_ready": true,
      "confidence_assessment": "Migration is structurally sound...",
      "key_concerns": [
        "Data source connection missing for Sales table"
      ],
      "manual_review_required": [
        "Sales table connection",
        "Verify aggregation formulas"
      ]
    }
  }
}
```

---

## 🎯 Key API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/ollama/models` | GET | List available models |
| `/api/jobs/{id}/review` | POST | Run review |
| `/api/jobs/{id}` | GET | Get results |
| `/docs` | GET | API documentation |

---

**Full Guide:** See POST_MIGRATION_REVIEW_GUIDE.md  
**API Docs:** http://localhost:8080/docs  
**Frontend:** http://localhost:3001
