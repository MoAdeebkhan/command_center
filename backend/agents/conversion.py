"""
Conversion Agent — Transforms field metadata and translates formulas.
Uses deterministic regex rules for formula translation with AI fallback.
"""
import logging
from agents.base import BaseAgent
from agents.formula_rules import translate_tableau_to_dax, translate_dax_to_tableau

logger = logging.getLogger(__name__)

PBI_DATATYPE_MAP = {
    "string": "string",
    "integer": "int64",
    "float": "double",
    "decimal": "decimal",
    "real": "double",
    "date": "dateTime",
    "datetime": "dateTime",
    "boolean": "boolean",
}

class ConversionAgent(BaseAgent):
    name = "Conversion Agent"

    def run(self, context: dict) -> dict:
        field_inv = context.get("field_inventory", [])
        source_format = context["source_format"]
        source_meta = context.get("source_meta", {})

        field_table_map = source_meta.get("field_table_map", {})
        
        field_mappings = []
        translated_formulas = []
        
        # 1. Map fields and types
        for f in field_inv:
            src_name = f["source_name"]
            src_type = f["source_type"]
            
            if source_format in ("twbx", "twb"):
                tgt_type = PBI_DATATYPE_MAP.get(src_type, "string")
                clean_name = src_name.strip("[]")
                tgt_name = f"{f['source_table']}[{clean_name}]"
            else:
                tgt_type = {"int64": "integer", "decimal": "real", "double": "real", "dateTime": "date"}.get(src_type, "string")
                tgt_name = f"[{src_name}]"
                
            field_mappings.append({
                "source_concept": src_name,
                "target_concept": tgt_name,
                "status": "mapped" if not f["is_calc"] else "needs_review",
                "type": f["role"]
            })
            
            # 2. Translate formulas
            if f["is_calc"] and f["formula"]:
                formula = f["formula"]
                
                if source_format in ("twbx", "twb"):
                    trans, conf, notes = translate_tableau_to_dax(formula, field_table_map)
                else:
                    trans, conf, notes = translate_dax_to_tableau(formula, field_table_map)
                
                # AI Fallback for low confidence
                if conf == "low":
                    try:
                        ai_res = self.ask_llm(
                            f"Translate this formula. Source: {source_format}, Formula: {formula}. Output JSON: {{'translated_formula': '...', 'notes': '...'}}"
                        )
                        trans = ai_res.get("translated_formula", trans)
                        notes = "AI Translation: " + ai_res.get("notes", notes)
                        conf = "medium"
                    except Exception:
                        pass

                translated_formulas.append({
                    "name": src_name,
                    "original_formula": formula,
                    "translated_formula": trans,
                    "confidence": conf,
                    "notes": notes
                })

        context["report"] = context.get("report", {})
        context["report"]["field_mappings"] = field_mappings
        context["report"]["translated_formulas"] = translated_formulas
        context["translated_formulas"] = translated_formulas
        context["conversion_message"] = f"Translated {len(translated_formulas)} formulas and mapped {len(field_mappings)} fields deterministically."
        
        return context
