"""
Post-Migration Review Agent — Uses advanced LLM (Qwen2.5, Llama3.3, or Gemma2)
to perform deep analysis of completed migration and identify potential issues.

This agent runs AFTER migration is complete and provides:
  - Formula correctness review
  - Data source connection validation
  - Semantic accuracy check
  - Business logic preservation verification
  - Recommendations for manual review
"""
import json
import logging
from typing import Dict, List
from agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Best models for code/formula review (in order of preference)
REVIEW_MODELS = {
    "qwen2.5-coder:32b": "Qwen 2.5 Coder 32B - Best for code/formula analysis",
    "qwen2.5:32b": "Qwen 2.5 32B - Excellent reasoning",
    "llama3.3:70b": "Llama 3.3 70B - Strong analytical capabilities",
    "gemma2:27b": "Gemma 2 27B - Good for technical review",
    "llama3:latest": "Llama 3 - Fallback option",
}


class PostMigrationReviewAgent(BaseAgent):
    name = "Post-Migration Review Agent"
    
    def __init__(self, model_name: str = None):
        """
        Initialize with specific model or auto-select best available.
        
        Args:
            model_name: Specific model to use (e.g., 'qwen2.5-coder:32b')
                       If None, will try models in order of preference
        """
        self.selected_model = model_name or self._select_best_model()
        logger.info(f"Post-Migration Review Agent initialized with model: {self.selected_model}")

    def _select_best_model(self) -> str:
        """
        Query Ollama for available models and select the best one for review.
        Falls back to llama3:latest if none of the preferred models are available.
        """
        try:
            import httpx
            from agents.base import OLLAMA_HOST
            
            with httpx.Client(timeout=5) as client:
                resp = client.get(f"{OLLAMA_HOST}/api/tags")
                data = resp.json()
                available = [m["name"] for m in data.get("models", [])]
                
                # Try preferred models in order
                for model_name, description in REVIEW_MODELS.items():
                    if model_name in available:
                        logger.info(f"Selected {model_name} for post-migration review")
                        return model_name
                
                # Fallback to llama3
                logger.warning("No preferred review models found, using llama3:latest")
                return "llama3:latest"
                
        except Exception as e:
            logger.warning(f"Could not query Ollama models: {e}, using llama3:latest")
            return "llama3:latest"

    def run(self, context: dict) -> dict:
        """
        Perform deep post-migration review of completed migration.
        
        Args:
            context: Migration context with:
                - report: Complete migration report
                - source_meta: Source file metadata
                - translated_formulas: All formula translations
                - field_inventory: All fields
                
        Returns:
            Updated context with review_analysis added
        """
        report = context.get("report", {})
        source_meta = context.get("source_meta", {})
        translated_formulas = context.get("translated_formulas", [])
        field_inventory = context.get("field_inventory", [])
        
        logger.info(f"Starting post-migration review with {self.selected_model}")
        
        # Build comprehensive review prompt
        prompt = self._build_review_prompt(
            report=report,
            source_meta=source_meta,
            translated_formulas=translated_formulas,
            field_inventory=field_inventory,
        )
        
        # Get AI analysis using selected model
        raw = self.ask_ollama(
            prompt=prompt,
            system=(
                "You are an expert BI migration auditor and quality analyst. "
                "Your role is to perform deep technical review of completed migrations, "
                "identifying potential issues, semantic errors, and areas requiring human attention. "
                "Be thorough, critical, and specific in your analysis. "
                "Respond ONLY with valid JSON."
            ),
            temperature=0.1,  # Low temperature for analytical precision
            expect_json=True,
            model=self.selected_model,
        )
        
        analysis = self.parse_json_safe(raw, fallback=self._fallback_analysis())
        
        # Enrich analysis with automated checks
        analysis = self._enrich_with_automated_checks(analysis, context)
        
        # Add to context
        context["post_migration_review"] = analysis
        context["review_model_used"] = self.selected_model
        context["post_migration_review_message"] = (
            f"Deep review completed using {self.selected_model}: "
            f"{len(analysis.get('critical_issues', []))} critical, "
            f"{len(analysis.get('warnings', []))} warnings, "
            f"{len(analysis.get('recommendations', []))} recommendations"
        )
        context["post_migration_review_ai_log"] = raw
        
        # Update report
        report["post_migration_review"] = analysis
        context["report"] = report
        
        return context

    def _build_review_prompt(
        self,
        report: dict,
        source_meta: dict,
        translated_formulas: list,
        field_inventory: list,
    ) -> str:
        """Build comprehensive prompt for post-migration review."""
        
        # Extract key metrics
        stats = report.get("stats", {})
        warnings = report.get("warnings", [])
        datasource_connections = report.get("datasource_connections", [])
        
        # Sample problematic formulas (high complexity or low confidence)
        problematic_formulas = [
            f for f in translated_formulas
            if f.get("confidence") == "low" or "error" in f.get("notes", "").lower()
        ][:10]
        
        # Connection issues
        missing_connections = [
            conn for conn in datasource_connections
            if not conn.get("server") and not conn.get("database") and not conn.get("filename")
        ]
        
        prompt = f"""# POST-MIGRATION REVIEW TASK

You are reviewing a completed BI migration. Perform a comprehensive analysis to identify issues that require human attention.

## MIGRATION SUMMARY
- Source Format: {report.get('source_format', 'Unknown')}
- Target Format: {report.get('target_format', 'Unknown')}
- Total Objects: {stats.get('total_objects', 'N/A')}
- Auto-migrated: {stats.get('auto_migrated', 'N/A')}
- Needs Review: {stats.get('needs_review', 'N/A')}
- Confidence Score: {stats.get('confidence_score', 'N/A')}

## DATA SOURCE CONNECTIONS
Total datasources: {len(datasource_connections)}
Missing connections: {len(missing_connections)}

Datasource connection details:
{json.dumps(datasource_connections, indent=2)[:2000]}

## FORMULA TRANSLATIONS
Total formulas: {len(translated_formulas)}
Low confidence formulas: {len(problematic_formulas)}

Sample problematic formulas:
{json.dumps(problematic_formulas, indent=2)[:3000]}

## EXISTING WARNINGS
{json.dumps(warnings, indent=2)[:1500]}

## FIELD INVENTORY SUMMARY
Total fields: {len(field_inventory)}
Calculated fields: {sum(1 for f in field_inventory if f.get('is_calc'))}
Hidden fields: {sum(1 for f in field_inventory if f.get('hidden'))}

---

# YOUR TASK

Analyze the migration and return JSON with this structure:

{{
  "critical_issues": [
    {{
      "issue_id": "unique-id",
      "category": "formula|connection|data_loss|semantic",
      "severity": "critical",
      "title": "Brief title",
      "description": "Detailed description of the issue",
      "affected_items": ["list of affected formulas/tables/fields"],
      "evidence": "Specific evidence from the migration",
      "impact": "What will break or be incorrect",
      "recommended_action": "Specific steps to fix",
      "can_auto_fix": true/false
    }}
  ],
  "warnings": [
    {{
      "issue_id": "unique-id",
      "category": "performance|usability|best_practice",
      "severity": "warning",
      "title": "Brief title",
      "description": "What might be suboptimal",
      "affected_items": ["list of items"],
      "recommended_action": "How to improve"
    }}
  ],
  "recommendations": [
    {{
      "recommendation_id": "unique-id",
      "category": "optimization|testing|documentation",
      "priority": "high|medium|low",
      "title": "Recommendation title",
      "description": "What to do",
      "rationale": "Why this matters"
    }}
  ],
  "review_summary": {{
    "overall_quality": "excellent|good|fair|poor",
    "migration_ready": true/false,
    "confidence_assessment": "Detailed assessment of migration quality",
    "key_concerns": ["List top 3-5 concerns"],
    "manual_review_required": ["Specific items that MUST be manually reviewed"]
  }},
  "semantic_validation": {{
    "business_logic_preserved": true/false,
    "data_relationships_intact": true/false,
    "calculation_accuracy": "high|medium|low",
    "concerns": ["List any semantic issues"]
  }},
  "testing_checklist": [
    {{
      "test_id": "unique-id",
      "test_type": "functional|data|visual|performance",
      "description": "What to test",
      "priority": "critical|high|medium|low",
      "test_steps": ["Step 1", "Step 2", "..."]
    }}
  ]
}}

## FOCUS AREAS

1. **Formula Correctness**: Are translations semantically accurate?
2. **Data Source Issues**: Will data actually load?
3. **Business Logic**: Is the intent preserved?
4. **Edge Cases**: What might break in production?
5. **Human Review**: What MUST be checked manually?

Be specific, cite evidence, and prioritize by impact.
"""
        
        return prompt

    def _fallback_analysis(self) -> dict:
        """Fallback analysis if LLM fails."""
        return {
            "critical_issues": [],
            "warnings": [{
                "issue_id": "llm-unavailable",
                "category": "system",
                "severity": "warning",
                "title": "AI Review Unavailable",
                "description": "Could not perform AI-powered deep review. Manual review recommended.",
                "recommended_action": "Manually review all formulas and connections"
            }],
            "recommendations": [{
                "recommendation_id": "manual-review",
                "category": "testing",
                "priority": "high",
                "title": "Perform Manual Review",
                "description": "AI review was not available, perform thorough manual testing",
                "rationale": "Automated review could not be completed"
            }],
            "review_summary": {
                "overall_quality": "unknown",
                "migration_ready": False,
                "confidence_assessment": "AI review unavailable",
                "key_concerns": ["AI review system unavailable"],
                "manual_review_required": ["All components"]
            },
            "semantic_validation": {
                "business_logic_preserved": None,
                "data_relationships_intact": None,
                "calculation_accuracy": "unknown",
                "concerns": ["Could not perform semantic validation"]
            },
            "testing_checklist": []
        }

    def _enrich_with_automated_checks(self, analysis: dict, context: dict) -> dict:
        """Add automated checks that don't require LLM."""
        
        report = context.get("report", {})
        translated_formulas = context.get("translated_formulas", [])
        datasource_connections = report.get("datasource_connections", [])
        
        # Check for missing connections
        missing_conns = [
            conn for conn in datasource_connections
            if not conn.get("server") and not conn.get("database") and not conn.get("filename")
        ]
        
        if missing_conns and not any(i.get("category") == "connection" for i in analysis.get("critical_issues", [])):
            analysis.setdefault("critical_issues", []).append({
                "issue_id": "missing-connections",
                "category": "connection",
                "severity": "critical",
                "title": f"{len(missing_conns)} Data Source(s) Missing Connection Info",
                "description": f"The following tables have no connection information: {', '.join(c.get('table', 'Unknown') for c in missing_conns[:5])}",
                "affected_items": [c.get("table") for c in missing_conns],
                "evidence": "No server, database, or filename found in connection metadata",
                "impact": "These tables will appear empty in Power BI. Data will not load.",
                "recommended_action": "Manually configure data source connections in Power BI. See DATA_SOURCE_MANUAL_FIX_GUIDE.md",
                "can_auto_fix": False
            })
        
        # Check for low-confidence formulas
        low_confidence = [f for f in translated_formulas if f.get("confidence") == "low"]
        if low_confidence and not any(i.get("category") == "formula" for i in analysis.get("warnings", [])):
            analysis.setdefault("warnings", []).append({
                "issue_id": "low-confidence-formulas",
                "category": "formula",
                "severity": "warning",
                "title": f"{len(low_confidence)} Formula(s) Translated with Low Confidence",
                "description": "These formulas may not be semantically accurate",
                "affected_items": [f.get("name") for f in low_confidence[:10]],
                "recommended_action": "Manually verify these formula translations produce correct results"
            })
        
        return analysis

    def ask_ollama(
        self,
        prompt: str,
        system: str = "You are a helpful assistant.",
        temperature: float = 0.2,
        expect_json: bool = True,
        model: str = None,
    ) -> str:
        """
        Override base ask_ollama to support model selection.
        """
        from agents.base import OLLAMA_HOST, OLLAMA_TIMEOUT
        import httpx
        
        use_model = model or self.selected_model
        
        payload = {
            "model": use_model,
            "prompt": prompt,
            "system": system,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": 8192,  # Longer output for detailed review
            },
        }

        try:
            with httpx.Client(timeout=OLLAMA_TIMEOUT) as client:
                resp = client.post(f"{OLLAMA_HOST}/api/generate", json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw = data.get("response", "")

                if expect_json:
                    raw = self._extract_json(raw)

                return raw

        except httpx.TimeoutException:
            logger.warning(f"[{self.name}] Ollama timeout with model {use_model}")
            return json.dumps({"error": "timeout", "fallback": True})
        except Exception as e:
            logger.warning(f"[{self.name}] Ollama error with model {use_model}: {e}")
            return json.dumps({"error": str(e), "fallback": True})
