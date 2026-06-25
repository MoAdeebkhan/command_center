"""
Extraction Agent — Processes parsed source structure and normalises it.
Builds the exact field inventory needed for conversion.
"""
import logging
from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ExtractionAgent(BaseAgent):
    name = "Extraction Agent"

    def run(self, context: dict) -> dict:
        source_meta = context["source_meta"]
        source_format = context["source_format"]

        field_inventory = []

        if source_format in ("twbx", "twb"):
            for ds in source_meta.get("datasources", []):
                for col in ds.get("columns", []):
                    field_inventory.append({
                        "source_name": col["name"],
                        "source_table": ds["name"],
                        "source_type": col["type"],
                        "role": col.get("role", "dimension"),
                        "is_calc": col.get("is_calc", False),
                        "hidden": col.get("hidden", False),
                        "formula": col.get("formula", ""),
                        "format_string": col.get("format", ""),
                    })
        else:
            for tbl in source_meta.get("tables", []):
                for col in tbl.get("columns", []):
                    field_inventory.append({
                        "source_name": col["name"],
                        "source_table": tbl["name"],
                        "source_type": col["type"],
                        "role": "dimension",
                        "is_calc": False,
                        "hidden": col.get("hidden", False),
                        "formula": "",
                        "format_string": col.get("format", ""),
                    })
            for meas in source_meta.get("measures", []):
                field_inventory.append({
                    "source_name": meas["name"],
                    "source_table": meas.get("table", "Unknown"),
                    "source_type": "decimal",
                    "role": "measure",
                    "is_calc": True,
                    "hidden": False,
                    "formula": meas.get("expression", ""),
                    "format_string": meas.get("format", ""),
                })

        context["field_inventory"] = field_inventory
        context["extraction_message"] = f"Extracted {len(field_inventory)} fields across datasources."
        return context
