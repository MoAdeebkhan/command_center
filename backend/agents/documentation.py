"""
Documentation Agent — Uses llama4 to generate a human-readable
migration guide from the conversion plan.
"""
import json
import logging
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class DocumentationAgent(BaseAgent):
    name = "Documentation Agent"

    def run(self, context: dict) -> dict:
        report = context.get("report", {})
        source_format = context["source_format"]
        target_format = context["target_format"]
        kpis = context.get("kpis", [])
        complexity = context.get("complexity", "Medium")

        prompt = self._build_prompt(report, source_format, target_format, kpis, complexity)
        raw = self.ask_ollama(
            prompt=prompt,
            system=(
                "You are a BI migration documentation expert. "
                "Generate clear, actionable migration documentation. "
                "Respond ONLY with valid JSON."
            ),
            expect_json=True,
        )

        docs = self.parse_json_safe(raw, fallback=self._fallback_docs(source_format, target_format, report))

        sections = docs.get("sections", [])
        msg = f"Generated migration guide with {len(sections)} sections"

        # Attach docs to report
        report["documentation"] = docs
        context["report"] = report
        context["documentation_message"] = msg
        context["documentation_ai_log"] = raw
        return context

    def _build_prompt(self, report: dict, source_format: str, target_format: str, kpis: list, complexity: str) -> str:
        stats = report.get("stats", {})
        warnings = report.get("warnings", [])
        unsupported = report.get("unsupported", [])
        translated = report.get("translated_formulas", [])

        direction = f"{source_format.upper()} → {target_format.upper()}"

        return f"""Generate a migration guide for a {direction} BI migration.

MIGRATION STATS:
- Total objects: {stats.get("total_objects", "?")}
- Auto-migrated: {stats.get("auto_migrated", "?")}
- Needs review: {stats.get("needs_review", "?")}
- Unsupported: {stats.get("unsupported", "?")}
- Confidence: {stats.get("confidence_score", "?")}
- Complexity: {complexity}

WARNINGS:
{json.dumps(warnings, indent=2)}

UNSUPPORTED FEATURES:
{json.dumps(unsupported, indent=2)}

TRANSLATED FORMULAS (sample):
{json.dumps(translated[:3], indent=2)}

KPIS:
{json.dumps(kpis[:5], indent=2)}

Generate a structured migration guide. Return JSON:
{{
  "sections": [
    {{
      "title": "Overview",
      "content": "Brief description of the migration scope and approach"
    }},
    {{
      "title": "Pre-Migration Checklist",
      "content": "Steps to prepare before starting"
    }},
    {{
      "title": "Formula Migration Guide",
      "content": "How to handle formula/measure translations"
    }},
    {{
      "title": "Manual Steps Required",
      "content": "List of items that need human intervention"
    }},
    {{
      "title": "Post-Migration Validation",
      "content": "How to verify the migration was successful"
    }}
  ],
  "estimated_effort": "X-Y days",
  "risk_level": "Low|Medium|High",
  "recommendations": ["recommendation 1", "recommendation 2", "recommendation 3"]
}}"""

    def _fallback_docs(self, source_format: str, target_format: str, report: dict) -> dict:
        stats = report.get("stats", {})
        return {
            "sections": [
                {
                    "title": "Overview",
                    "content": (
                        f"This migration converts a {source_format.upper()} workbook to {target_format.upper()} format. "
                        f"Total of {stats.get('total_objects', '?')} objects identified with "
                        f"{stats.get('auto_migrated', '?')} auto-migrated and "
                        f"{stats.get('needs_review', '?')} requiring manual review."
                    ),
                },
                {
                    "title": "Pre-Migration Checklist",
                    "content": (
                        "1. Back up the original source file\n"
                        "2. Document all data source connections\n"
                        "3. Note all user-defined calculated fields\n"
                        "4. List all dashboard interactions and filters\n"
                        "5. Capture expected output values for regression testing"
                    ),
                },
                {
                    "title": "Formula Migration Guide",
                    "content": (
                        "Review all translated formulas in the report. "
                        "High-confidence translations can be used directly. "
                        "Low-confidence translations marked with ⚠️ require manual verification."
                    ),
                },
                {
                    "title": "Manual Steps Required",
                    "content": "\n".join(report.get("warnings", ["Review unsupported features manually."])),
                },
                {
                    "title": "Post-Migration Validation",
                    "content": (
                        "1. Compare KPI values between source and target\n"
                        "2. Verify all filters work as expected\n"
                        "3. Test on representative data samples\n"
                        "4. Have a business user validate the report visually"
                    ),
                },
            ],
            "estimated_effort": "3-5 days",
            "risk_level": "Medium",
            "recommendations": [
                "Start with the highest-confidence auto-migrated objects",
                "Prioritize KPI measures for manual review",
                "Run parallel validation with both tools before decommissioning the source",
            ],
        }
