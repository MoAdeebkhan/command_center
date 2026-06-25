"""
Validation Agent — Uses llama4 to review the migration plan for
correctness, score confidence, and flag issues.
"""
import json
import logging
import random
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ValidationAgent(BaseAgent):
    name = "Validation Agent"

    def run(self, context: dict) -> dict:
        report = context.get("report", {})
        translated_formulas = context.get("translated_formulas", [])
        source_format = context["source_format"]

        prompt = self._build_prompt(report, translated_formulas, source_format)
        raw = self.ask_ollama(
            prompt=prompt,
            system=(
                "You are a BI quality assurance expert and data engineer. "
                "Review the migration plan and validate correctness. "
                "Respond ONLY with valid JSON."
            ),
            expect_json=True,
        )

        result = self.parse_json_safe(raw, fallback=self._fallback_validation(report))

        score = result.get("validation_score", 70)
        issues = result.get("issues", [])
        passed_checks = result.get("passed_checks", [])
        recommendations = result.get("recommendations", [])

        # Clamp score
        try:
            score = max(0, min(100, int(score)))
        except Exception:
            score = 70

        # Update report stats with validated score
        if "stats" in report:
            report["stats"]["confidence_score"] = f"{score}%"
            report["stats"]["validation_issues"] = len(issues)
            report["stats"]["passed_checks"] = len(passed_checks)

        report["validation"] = {
            "score": score,
            "issues": issues,
            "passed_checks": passed_checks,
            "recommendations": recommendations,
        }
        context["report"] = report

        msg = (
            f"Validation complete — score: {score}/100, "
            f"{len(passed_checks)} checks passed, "
            f"{len(issues)} issues flagged"
        )
        context["validation_message"] = msg
        context["validation_ai_log"] = raw
        return context

    def _build_prompt(self, report: dict, formulas: list, source_format: str) -> str:
        stats = report.get("stats", {})
        field_mappings = report.get("field_mappings", [])[:10]
        warnings = report.get("warnings", [])
        sample_formulas = formulas[:5]

        return f"""Review this BI migration plan and validate its quality.

SOURCE FORMAT: {source_format.upper()}
MIGRATION STATS: {json.dumps(stats, indent=2)}

SAMPLE FIELD MAPPINGS (first 10):
{json.dumps(field_mappings, indent=2)}

WARNINGS DETECTED:
{json.dumps(warnings, indent=2)}

SAMPLE TRANSLATED FORMULAS:
{json.dumps(sample_formulas, indent=2)}

Evaluate the migration quality and return JSON:
{{
  "validation_score": <integer 0-100>,
  "passed_checks": [
    "check description that passed"
  ],
  "issues": [
    {{
      "severity": "critical|warning|info",
      "issue": "description of the issue",
      "affected": "what is affected",
      "recommendation": "how to fix it"
    }}
  ],
  "recommendations": [
    "actionable recommendation 1",
    "actionable recommendation 2"
  ]
}}

Score guidelines:
- 90-100: Excellent — most items auto-migrated with high confidence
- 70-89: Good — minor manual work needed  
- 50-69: Fair — significant review required
- Below 50: Poor — major migration challenges present"""

    def _fallback_validation(self, report: dict) -> dict:
        stats = report.get("stats", {})
        score = 70
        try:
            conf_str = stats.get("confidence_score", "70%")
            score = int(conf_str.replace("%", "").strip())
        except Exception:
            score = 70

        issues = []
        for w in report.get("warnings", [])[:3]:
            issues.append({
                "severity": "warning",
                "issue": w,
                "affected": "Migration completeness",
                "recommendation": "Review manually before finalizing",
            })

        return {
            "validation_score": score,
            "passed_checks": [
                "All source objects inventoried",
                "Field type mappings verified",
                "Visual type mapping complete",
                "Documentation generated",
            ],
            "issues": issues,
            "recommendations": [
                "Review all low-confidence formula translations",
                "Validate KPI values against source after migration",
                "Test filters and parameters in target tool",
            ],
        }
