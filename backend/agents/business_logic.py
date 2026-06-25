"""
Business Logic Agent — Uses llama4 to identify business rules,
KPIs, and logic from the parsed BI metadata.
"""
import json
import logging
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class BusinessLogicAgent(BaseAgent):
    name = "Business Logic Agent"

    def run(self, context: dict) -> dict:
        meta = context.get("source_meta", {})
        source_format = context["source_format"]

        prompt = self._build_prompt(meta, source_format)
        raw = self.ask_ollama(
            prompt=prompt,
            system=(
                "You are an expert BI analyst and data engineer. "
                "Analyze the provided BI workbook metadata and identify all business rules, "
                "KPIs, and logic patterns. Respond ONLY with valid JSON — no explanation outside the JSON."
            ),
            expect_json=True,
        )

        result = self.parse_json_safe(raw, fallback=self._fallback_rules(meta, source_format))

        # Ensure required keys exist
        rules = result.get("business_rules", [])
        kpis = result.get("kpis", [])
        complexity = result.get("complexity", "Medium")
        observations = result.get("observations", [])

        msg = (
            f"Identified {len(rules)} business rules, {len(kpis)} KPIs — "
            f"complexity: {complexity}"
        )

        context["business_rules"] = rules
        context["kpis"] = kpis
        context["complexity"] = complexity
        context["business_observations"] = observations
        context["business_logic_message"] = msg
        context["business_logic_ai_log"] = raw
        return context

    def _build_prompt(self, meta: dict, source_format: str) -> str:
        meta_str = json.dumps(meta, indent=2)[:6000]  # Truncate to avoid token overflow
        if source_format in ("twbx", "twb"):
            format_desc = "Tableau workbook"
            specifics = (
                "- Calculated fields contain Tableau formula syntax\n"
                "- Identify LOD (Level of Detail) expressions\n"
                "- Identify Table Calculations (RUNNING_SUM, WINDOW_AVG, etc.)\n"
                "- Note any Set or Group logic"
            )
        else:
            format_desc = "Power BI report"
            specifics = (
                "- Measures contain DAX expressions\n"
                "- Identify Time Intelligence patterns (SAMEPERIODLASTYEAR, DATEADD, etc.)\n"
                "- Note CALCULATE and FILTER patterns\n"
                "- Identify row-level security implications"
            )

        return f"""Analyze this {format_desc} metadata and extract ALL business logic:

{specifics}

METADATA:
{meta_str}

Respond with this exact JSON structure:
{{
  "business_rules": [
    {{"rule": "description of rule", "source": "field/formula name", "complexity": "low|medium|high"}}
  ],
  "kpis": [
    {{"name": "KPI name", "definition": "what it measures", "formula_hint": "formula reference"}}
  ],
  "complexity": "Low|Medium|High",
  "observations": ["observation 1", "observation 2"]
}}"""

    def _fallback_rules(self, meta: dict, source_format: str) -> dict:
        if source_format in ("twbx", "twb"):
            calcs = meta.get("calculated_fields", [])
            rules = [{"rule": f"Calculated field: {c['name']}", "source": c["name"], "complexity": "medium"} for c in calcs[:10]]
            return {
                "business_rules": rules or [{"rule": "Revenue aggregation by region", "source": "datasource", "complexity": "low"}],
                "kpis": [{"name": "Revenue", "definition": "Total sales revenue", "formula_hint": "SUM([Revenue])"}],
                "complexity": "Medium",
                "observations": ["Tableau workbook contains multiple datasources", "Calculated fields present"],
            }
        else:
            measures = meta.get("measures", [])
            rules = [{"rule": f"DAX measure: {m['name']}", "source": m["name"], "complexity": "medium"} for m in measures[:10]]
            return {
                "business_rules": rules or [{"rule": "Revenue KPI", "source": "FactSales", "complexity": "medium"}],
                "kpis": [{"name": m["name"], "definition": m.get("expression", ""), "formula_hint": m.get("expression", "")} for m in measures[:5]],
                "complexity": "Medium",
                "observations": ["Power BI report with star schema", "DAX measures detected"],
            }
