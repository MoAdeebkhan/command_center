"""
Deployment Agent — Generates migration output files that open directly
in Power BI Desktop (.pbit) or Tableau Desktop (.twbx).

.pbit structure (ZIP):
    [Content_Types].xml
    Version
    Metadata
    Settings
    DataModelSchema          (UTF-16-LE JSON — TMSL format)
    Report/Layout            (UTF-16-LE JSON)

.twbx structure (ZIP):
    workbook.twb             (Tableau XML)
"""
import json
import logging
import zipfile
import io
import csv
import time
import re
from pathlib import Path

from agents.base import BaseAgent

logger = logging.getLogger(__name__)

# Power BI expects UTF-16-LE without BOM for all JSON files inside .pbit
def _encode_pbi_json(obj: dict) -> bytes:
    """Encode a dict as JSON in UTF-16-LE without BOM."""
    return json.dumps(obj, indent=2, ensure_ascii=False).encode('utf-16-le')



class DeploymentAgent(BaseAgent):
    name = "Deployment Agent"

    def run(self, context: dict) -> dict:
        source_format = context["source_format"]
        report = context.get("report", {})

        output_dir = Path("outputs")
        output_dir.mkdir(exist_ok=True)

        base_name = f"migration_{int(time.time())}"
        package_file = output_dir / f"{base_name}_package.zip"

        # Add source metadata to report for debugging
        source_meta = context.get("source_meta", {})
        report["datasource_connections"] = [
            {
                "table": ds.get("name"),
                "type": ds.get("connection", {}).get("type", "unknown"),
                "server": ds.get("connection", {}).get("server", ""),
                "database": ds.get("connection", {}).get("database", ""),
                "schema": ds.get("connection", {}).get("schema", ""),
                "filename": ds.get("connection", {}).get("filename", ""),
                "table_name": ds.get("connection", {}).get("table", ""),
            }
            for ds in source_meta.get("datasources", [])
        ]

        with zipfile.ZipFile(package_file, "w", zipfile.ZIP_DEFLATED) as pkg:

            # ── Main BI artifact ──────────────────────────────────
            if source_format in ("twbx", "twb"):
                bi_name = f"{base_name}_migrated.pbit"
                bi_bytes = self._build_pbit(context)
                pkg.writestr(bi_name, bi_bytes)
                msg = f"Generated Power BI Template: {bi_name}"
            else:
                bi_name = f"{base_name}_migrated.twbx"
                bi_bytes = self._build_twbx(context)
                pkg.writestr(bi_name, bi_bytes)
                msg = f"Generated Tableau Workbook: {bi_name}"

            # ── Supporting artifacts ──────────────────────────────
            pkg.writestr("migration_report.json",
                         json.dumps(report, indent=2, default=str))
            pkg.writestr("mapping-fields.csv", self._fields_csv(context))
            pkg.writestr("mapping-visuals.csv", self._visuals_csv(context))
            pkg.writestr("mapping-formulas.csv", self._formulas_csv(context))
            pkg.writestr("mapping-relationships.csv",
                         self._relationships_csv(context))

        context["deployment_artifacts"] = [str(package_file)]
        context["deployment_message"] = msg
        context["output_path"] = str(package_file)
        return context

    # ══════════════════════════════════════════════════════════════════
    #  POWER BI TEMPLATE (.pbit)
    # ══════════════════════════════════════════════════════════════════

    def _build_pbit(self, ctx: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # [Content_Types].xml needs to be UTF-8 with BOM
            zf.writestr("[Content_Types].xml", b'\xef\xbb\xbf' + self._pbit_content_types().encode('utf-8'))
            # Version must be UTF-16-LE without BOM (usually '1.28' for modern PBIX/PBIT)
            zf.writestr("Version", "1.28".encode("utf-16-le"))
            zf.writestr("Metadata", self._pbit_metadata())
            zf.writestr("Settings", self._pbit_settings())
            zf.writestr("DataModelSchema",
                        self._pbit_data_model_schema(ctx))
            zf.writestr("Report/Layout",
                        self._pbit_report_layout(ctx))
            # OPC relationship file (required by System.IO.Packaging)
            zf.writestr("_rels/.rels", (
                '<?xml version="1.0" encoding="utf-8"?>'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '</Relationships>'
            ))
        return buf.getvalue()

    # ── Static scaffolding files ──────────────────────────────────

    def _pbit_content_types(self) -> str:
        return (
            '<?xml version="1.0" encoding="utf-8"?>\r\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\r\n'
            '  <Default Extension="json" ContentType="application/json" />\r\n'
            '  <Default Extension="xml" ContentType="application/xml" />\r\n'
            '  <Override PartName="/Version" ContentType="text/plain" />\r\n'
            '  <Override PartName="/Metadata" ContentType="application/json" />\r\n'
            '  <Override PartName="/Settings" ContentType="application/json" />\r\n'
            '  <Override PartName="/DataModelSchema" ContentType="application/json" />\r\n'
            '  <Override PartName="/Report/Layout" ContentType="application/json" />\r\n'
            '</Types>'
        )

    def _pbit_metadata(self) -> bytes:
        obj = {
            "Version": 5,
            "AutoCreatedRelationships": [],
            "CreatedFrom": "Cloud",
            "CreatedFromRelease": "2025.08"
        }
        return _encode_pbi_json(obj)

    def _pbit_settings(self) -> bytes:
        obj = {
            "Version": 4,
            "ReportSettings": {},
            "QueriesSettings": {
                "TypeDetectionEnabled": True,
                "RelationshipImportEnabled": True,
                "Version": "2.146.304.0"
            }
        }
        return _encode_pbi_json(obj)

    # ── DataModelSchema (TMSL) ────────────────────────────────────

    def _get_m_partition_expression(self, tbl_name: str, conn: dict) -> list[str]:
        """
        Build Power Query M expression for data source connection.
        Returns None if connection info is incomplete.
        """
        if not conn or not isinstance(conn, dict):
            return None
            
        conn_type = conn.get("type", "unknown").lower()
        
        # 1. SQL Server
        if "sqlserver" in conn_type or conn_type == "sql":
            server = conn.get("server", "")
            db = conn.get("database", "")
            
            # Validation: both server and database must be present
            if not server or not db:
                logger.warning(f"Incomplete SQL Server connection info for {tbl_name}: server={server}, db={db}")
                return None
                
            schema_name = conn.get("schema", "dbo")
            table = conn.get("table", tbl_name)
            
            return [
                "let",
                f"    Source = Sql.Database(\"{server}\", \"{db}\"),",
                f"    Navigation = Source{{[Schema=\"{schema_name}\",Item=\"{table}\"]}}[Data]",
                "in",
                "    Navigation"
            ]
            
        # 2. PostgreSQL
        elif "postgres" in conn_type:
            server = conn.get("server", "")
            db = conn.get("database", "")
            
            if not server or not db:
                logger.warning(f"Incomplete PostgreSQL connection info for {tbl_name}: server={server}, db={db}")
                return None
                
            schema_name = conn.get("schema", "public")
            table = conn.get("table", tbl_name)
            
            return [
                "let",
                f"    Source = PostgreSQL.Database(\"{server}\", \"{db}\"),",
                f"    Navigation = Source{{[Schema=\"{schema_name}\",Item=\"{table}\"]}}[Data]",
                "in",
                "    Navigation"
            ]
            
        # 3. Excel
        elif "excel" in conn_type:
            filename = conn.get("filename", "")
            
            if not filename:
                logger.warning(f"No filename for Excel connection {tbl_name}")
                return None
                
            # escape backslashes for Power Query
            filename_escaped = filename.replace("\\", "\\\\")
            table = conn.get("table", tbl_name)
            
            return [
                "let",
                f"    Source = Excel.Workbook(File.Contents(\"{filename_escaped}\"), null, true),",
                f"    Sheet = Source{{[Item=\"{table}\",Kind=\"Sheet\"]}}[Data],",
                "    PromoteHeaders = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true])",
                "in",
                "    PromoteHeaders"
            ]

        # 4. Text/CSV
        elif "textscan" in conn_type or "csv" in conn_type:
            filename = conn.get("filename", "")
            
            if not filename:
                logger.warning(f"No filename for CSV connection {tbl_name}")
                return None
                
            filename_escaped = filename.replace("\\", "\\\\")
            
            return [
                "let",
                f"    Source = Csv.Document(File.Contents(\"{filename_escaped}\"), [Delimiter=\",\", Columns=20, Encoding=1252, QuoteStyle=QuoteStyle.None])",
                "in",
                "    Source"
            ]

        # 5. Default/Fallback
        else:
            logger.warning(f"Unknown connection type '{conn_type}' for table {tbl_name}")
            return None

    def _pbit_data_model_schema(self, ctx: dict) -> bytes:
        field_inv = ctx.get("field_inventory", [])
        translated = {f["name"]: f for f in ctx.get("translated_formulas", [])}
        meta = ctx.get("source_meta", {})

        # Group fields by table
        tables_dict: dict[str, dict] = {}
        table_added_names: dict[str, set[str]] = {}
        for f in field_inv:
            tbl = f.get("source_table", "MigratedData")
            if tbl not in tables_dict:
                tables_dict[tbl] = {
                    "name": tbl,
                    "columns": [],
                    "measures": [],
                    "hierarchies": [],
                }
                table_added_names[tbl] = set()

            col_name = f["source_name"].strip("[]")
            if col_name in table_added_names[tbl]:
                continue
            table_added_names[tbl].add(col_name)
            pbi_type = self._to_pbi_type(f["source_type"])

            if f["role"] == "measure" or (f["is_calc"] and f["role"] != "dimension"):
                formula = f.get("formula", "BLANK()")
                # Use translated formula if available
                t = translated.get(f["source_name"])
                if t and t.get("translated_formula"):
                    formula = t["translated_formula"]

                tables_dict[tbl]["measures"].append({
                    "name": col_name,
                    "expression": formula,
                    "formatString": f.get("format_string", ""),
                })
            else:
                col_def = {
                    "name": col_name,
                    "dataType": pbi_type
                }
                
                if f.get("is_calc"):
                    # True calculated column
                    col_def["type"] = "calculated"
                    formula = f.get("formula", "BLANK()")
                    t = translated.get(f["source_name"])
                    if t and t.get("translated_formula"):
                        formula = t["translated_formula"]
                    col_def["expression"] = formula
                else:
                    # Column coming from the table source
                    col_def["type"] = "calculatedTableColumn"
                    col_def["sourceColumn"] = col_name

                if f.get("hidden"):
                    col_def["isHidden"] = True
                if f.get("format_string"):
                    col_def["formatString"] = f["format_string"]
                tables_dict[tbl]["columns"].append(col_def)

        # Hierarchies
        for h in meta.get("hierarchies", []):
            tbl_name = h.get("datasource", h.get("table", ""))
            if tbl_name in tables_dict:
                levels = []
                for i, lvl in enumerate(h.get("levels", [])):
                    lvl_name = lvl.strip("[]")
                    levels.append({
                        "name": lvl_name,
                        "ordinal": i,
                        "column": lvl_name,
                    })
                if levels:
                    tables_dict[tbl_name]["hierarchies"].append({
                        "name": h.get("name", "Hierarchy"),
                        "levels": levels,
                    })

        # Clean empty arrays and build partitions
        datasources = {ds["name"]: ds for ds in meta.get("datasources", [])}
        tables_list = []
        for tbl_name, t in tables_dict.items():
            if not t.get("hierarchies"):
                if "hierarchies" in t:
                    del t["hierarchies"]
            if not t.get("measures"):
                if "measures" in t:
                    del t["measures"]
            
            ds_info = datasources.get(tbl_name, {})
            conn = ds_info.get("connection", {})
            
            # Validate connection has actual data
            has_conn_data = conn and any([
                conn.get("server"),
                conn.get("database"),
                conn.get("filename"),
            ])
            
            m_expr = self._get_m_partition_expression(tbl_name, conn) if has_conn_data else None

            if m_expr:
                t["partitions"] = [{
                    "name": tbl_name,
                    "mode": "import",
                    "source": {
                        "type": "m",
                        "expression": "\n".join(m_expr)  # Join the list into a string
                    }
                }]
                # Set non-calculated columns to data type
                for col in t.get("columns", []):
                    if col.get("type") == "calculatedTableColumn":
                        col["type"] = "data"
            else:
                # No connection info — create empty placeholder table with correct schema
                # This allows the user to manually reconnect the data source
                logger.warning(f"No connection info for table '{tbl_name}' - creating empty placeholder")
                
                # Create columns with proper data types for schema
                dax_cols = []
                for c in t.get("columns", []):
                    if c.get("type") == "calculated":
                        continue  # Skip calculated columns from source
                    col_name_escaped = c["name"].replace('"', '""')
                    dax_cols.append(f'"{col_name_escaped}"')
                
                if not dax_cols:
                    # At least one column is needed
                    dax_cols = ['"_PlaceholderColumn"']
                    t["columns"].append({
                        "name": "_PlaceholderColumn",
                        "dataType": "string",
                        "type": "data",
                        "isHidden": False
                    })
                
                # Use SELECTCOLUMNS on GENERATESERIES to create an empty table
                # This creates the schema without actual data
                dax_cols_str = ", ".join([f'"{c.replace(chr(34), chr(34)*2)}"' for c in dax_cols])
                t["partitions"] = [{
                    "name": tbl_name,
                    "mode": "import",
                    "source": {
                        "type": "calculated",
                        # Creates a table with correct columns but no rows
                        "expression": f"SELECTCOLUMNS(GENERATESERIES(0, -1), {dax_cols_str}, BLANK())"
                    }
                }]
            
            tables_list.append(t)

        # Relationships
        rels = []
        for r in meta.get("relationships", []):
            rel = {
                "name": "",
                "fromTable": r["from_table"],
                "fromColumn": r["from_column"].strip("[]"),
                "toTable": r["to_table"],
                "toColumn": r["to_column"].strip("[]"),
            }
            card = r.get("cardinality", "manyToOne")
            if card:
                rel["cardinality"] = card
            cf = r.get("cross_filter", "singleDirection")
            if cf:
                rel["crossFilteringBehavior"] = cf
            if r.get("active") is False:
                rel["isActive"] = False
            rels.append(rel)

        schema = {
            "name": "Model",
            "compatibilityLevel": 1550,
            "model": {
                "culture": "en-US",
                "tables": tables_list,
                "relationships": rels,
                "annotations": [
                    {"name": "MigratedBy", "value": "Agentic BI Migration Platform"}
                ],
            },
        }

        return _encode_pbi_json(schema)

    # ── Report/Layout ─────────────────────────────────────────────

    TABLEAU_TO_PBI_VISUAL = {
        "bar":            "clusteredBarChart",
        "stackedbar":     "stackedBarChart",
        "side-by-side bar": "clusteredBarChart",
        "automatic":      "clusteredColumnChart",
        "line":           "lineChart",
        "area":           "areaChart",
        "square":         "treemap",
        "circle":         "scatterChart",
        "pie":            "pieChart",
        "text":           "tableEx",
        "map":            "map",
        "polygon":        "filledMap",
        "gantt_bar":      "clusteredBarChart",
        "shape":          "shapeMap",
    }

    def _pbit_report_layout(self, ctx: dict) -> bytes:
        meta = ctx.get("source_meta", {})
        worksheets = meta.get("worksheets", [])
        dashboards = meta.get("dashboards", [])
        field_table_map = meta.get("field_table_map", {})

        sections = []

        if dashboards:
            for di, db in enumerate(dashboards):
                containers = []
                db_sheets = db.get("sheets", [])
                # Lay out worksheet visuals in a grid
                for si, sheet_name in enumerate(db_sheets):
                    ws = next((w for w in worksheets if w["name"] == sheet_name), None)
                    if not ws:
                        continue
                    col = si % 2
                    row = si // 2
                    x = 20 + col * 620
                    y = 20 + row * 380
                    containers.extend(
                        self._ws_to_visual_containers(ws, field_table_map, x, y, 580, 350)
                    )

                sections.append({
                    "name": f"ReportSection{di + 1}",
                    "displayName": db["name"],
                    "width": 1280,
                    "height": 720,
                    "visualContainers": containers,
                })
        elif worksheets:
            for wi, ws in enumerate(worksheets):
                containers = self._ws_to_visual_containers(
                    ws, field_table_map, 20, 20, 1200, 650
                )
                sections.append({
                    "name": f"ReportSection{wi + 1}",
                    "displayName": ws["name"],
                    "width": 1280,
                    "height": 720,
                    "visualContainers": containers,
                })
        else:
            sections.append({
                "name": "ReportSection1",
                "displayName": "Migrated Report",
                "width": 1280,
                "height": 720,
                "visualContainers": [],
            })

        layout = {
            "id": 0,
            "reportId": "00000000-0000-0000-0000-000000000000",
            "sections": sections,
            "config": json.dumps({"version": "5.54", "themeCollection": {"baseTheme": {"name": "CY24SU06", "version": "5.54", "type": 2}}}),
        }
        return _encode_pbi_json(layout)

    def _ws_to_visual_containers(self, ws, ftm, x, y, w, h):
        mark = ws.get("mark_type", "Automatic").lower()
        pbi_type = self.TABLEAU_TO_PBI_VISUAL.get(mark, "clusteredColumnChart")

        rows = ws.get("rows", [])
        cols = ws.get("cols", [])
        encodings = ws.get("encodings", {})

        # Build projections + prototypeQuery From/Select lists
        projections = {}
        from_list = []
        select_list = []
        alias_map = {}  # table -> alias letter

        def get_alias(table):
            if table not in alias_map:
                alias_map[table] = chr(ord('a') + len(alias_map))
                from_list.append({"Name": alias_map[table], "Entity": table, "Type": 0})
            return alias_map[table]

        # Category axis (cols in Tableau = Category/X in PBI)
        cat_fields = []
        for c in cols:
            field = c.get("field", "") if isinstance(c, dict) else str(c)
            field = field.strip("[]")
            if field:
                table = ftm.get(field, "Table")
                alias = get_alias(table)
                qref = f"{table}.{field}"
                cat_fields.append({"queryRef": qref})
                select_list.append({
                    "Column": {
                        "Expression": {"SourceRef": {"Source": alias}},
                        "Property": field
                    },
                    "Name": qref
                })
        if cat_fields:
            projections["Category"] = cat_fields

        # Values axis (rows in Tableau = Y/Values in PBI)
        val_fields = []
        for r in rows:
            field = r.get("field", "") if isinstance(r, dict) else str(r)
            field = field.strip("[]")
            agg = r.get("aggregation", "SUM") if isinstance(r, dict) else "SUM"
            if field:
                table = ftm.get(field, "Table")
                alias = get_alias(table)
                # If we assume all value fields are columns and need aggregation
                # For proper PBI value aggregation, use Column + Aggregation
                qref = f"Sum({table}.{field})" if agg else f"{table}.{field}"
                val_fields.append({"queryRef": qref})
                
                # Check if it's a measure from our parsed fields
                is_measure = False
                # Just assume it's a column with aggregation for now, as that's safer for Tableau rows
                select_item = {
                    "Column": {
                        "Expression": {"SourceRef": {"Source": alias}},
                        "Property": field
                    },
                    "Name": qref
                }
                
                if agg:
                    agg_map = {"SUM": 1, "AVG": 2, "MIN": 3, "MAX": 4, "COUNT": 5, "COUNTD": 6}
                    pbi_agg = agg_map.get(agg.upper(), 1)
                    select_item["Aggregation"] = pbi_agg
                    
                select_list.append(select_item)
        if val_fields:
            projections["Y"] = val_fields

        # Color / Legend
        color_field = encodings.get("color", "")
        if color_field:
            color_field = color_field.strip("[]")
            table = ftm.get(color_field, "Table")
            alias = get_alias(table)
            qref = f"{table}.{color_field}"
            projections["Series"] = [{"queryRef": qref}]
            select_list.append({
                "Column": {
                    "Expression": {"SourceRef": {"Source": alias}},
                    "Property": color_field
                },
                "Name": qref
            })

        # Build prototypeQuery (required for PBI to load data into the visual)
        proto_query = None
        if from_list and select_list:
            proto_query = {
                "Version": 2,
                "From": from_list,
                "Select": select_list
            }

        single_visual = {
            "visualType": pbi_type,
            "projections": projections,
            "objects": {},
        }
        if proto_query:
            single_visual["prototypeQuery"] = proto_query

        config = {
            "name": re.sub(r"[^a-zA-Z0-9]", "", ws.get("name", "Visual")),
            "layouts": [{"id": 0, "position": {"x": x, "y": y, "width": w, "height": h}}],
            "singleVisual": single_visual,
        }

        return [{
            "x": x, "y": y, "width": w, "height": h,
            "config": json.dumps(config, ensure_ascii=False),
            "filters": "[]",
        }]

    # ══════════════════════════════════════════════════════════════════
    #  TABLEAU WORKBOOK (.twbx)
    # ══════════════════════════════════════════════════════════════════

    PBI_TO_TABLEAU_TYPE = {
        "string": "string", "int64": "integer", "double": "real",
        "decimal": "real", "dateTime": "datetime", "boolean": "boolean",
    }

    PBI_TO_TABLEAU_MARK = {
        "clusteredColumnChart": "Bar",
        "clusteredBarChart": "Bar",
        "stackedBarChart": "Bar",
        "lineChart": "Line",
        "areaChart": "Area",
        "pieChart": "Pie",
        "scatterChart": "Circle",
        "treemap": "Square",
        "tableEx": "Text",
        "matrix": "Text",
        "card": "Text",
        "map": "Map",
        "filledMap": "Polygon",
    }

    def _build_twbx(self, ctx: dict) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("migrated.twb", self._build_twb_xml(ctx))
        return buf.getvalue()

    def _build_twb_xml(self, ctx: dict) -> str:
        meta = ctx.get("source_meta", {})
        field_inv = ctx.get("field_inventory", [])
        translated = {f["name"]: f for f in ctx.get("translated_formulas", [])}

        # Group fields by table
        tables: dict[str, list] = {}
        for f in field_inv:
            tbl = f.get("source_table", "Data")
            tables.setdefault(tbl, []).append(f)

        lines = [
            '<?xml version="1.0" encoding="utf-8"?>',
            '<workbook source-build="2024.1.0" source-platform="win" version="18.1"',
            '    xmlns:user="http://www.tableausoftware.com/xml/user">',
            '  <preferences>',
            '    <preference name="ui.encoding.shelf.height" value="24" />',
            '    <preference name="ui.shelf.height" value="26" />',
            '  </preferences>',
            '',
        ]

        # ── Datasources ──────────────────────────────────────────
        lines.append('  <datasources>')
        for tbl_name, cols in tables.items():
            safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', tbl_name)
            lines.append(f'    <datasource caption="{tbl_name}" inline="true" name="{safe_name}" version="18.1">')
            lines.append(f'      <connection class="textscan" directory="" filename="">')
            lines.append(f'        <relation name="{tbl_name}" table="[{tbl_name}]" type="table">')
            lines.append(f'          <columns>')
            for col in cols:
                col_name = col["source_name"]
                col_type = self.PBI_TO_TABLEAU_TYPE.get(col["source_type"], "string")
                lines.append(f'            <column datatype="{col_type}" name="{col_name}" />')
            lines.append(f'          </columns>')
            lines.append(f'        </relation>')
            lines.append(f'      </connection>')

            # Columns with metadata
            for col in cols:
                col_name = col["source_name"]
                caption = col_name.strip("[]")
                col_type = self.PBI_TO_TABLEAU_TYPE.get(col["source_type"], "string")
                role = "measure" if col["role"] == "measure" else "dimension"
                hidden = "true" if col.get("hidden") else "false"

                lines.append(f'      <column caption="{caption}" datatype="{col_type}" '
                             f'hidden="{hidden}" name="[{caption}]" role="{role}" type="quantitative">')

                # Calculated field
                if col.get("is_calc") and col.get("formula"):
                    formula = col["formula"]
                    t = translated.get(col["source_name"])
                    if t and t.get("translated_formula"):
                        formula = t["translated_formula"]
                    formula_escaped = formula.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
                    lines.append(f'        <calculation class="tableau" formula="{formula_escaped}" />')

                lines.append(f'      </column>')

            lines.append(f'    </datasource>')
        lines.append('  </datasources>')

        # ── Worksheets ────────────────────────────────────────────
        lines.append('  <worksheets>')

        pages = meta.get("pages", [])
        if pages:
            for page in pages:
                page_name = page.get("name", "Sheet")
                lines.append(f'    <worksheet name="{page_name}">')
                lines.append(f'      <table>')
                lines.append(f'        <view>')

                visuals = page.get("visuals", [])
                if visuals:
                    first_vis = visuals[0] if visuals else {}
                    vis_type = first_vis.get("type", "tableEx")
                    mark_type = self.PBI_TO_TABLEAU_MARK.get(vis_type, "Automatic")
                    lines.append(f'          <mark class="{mark_type}" />')

                    # Extract field projections
                    projs = first_vis.get("projections", {})
                    cat_fields = projs.get("Category", projs.get("Field", []))
                    val_fields = projs.get("Y", projs.get("Values", []))

                    if cat_fields:
                        cols_str = ", ".join(
                            f'[{cf.get("column", cf.get("ref", ""))}]' for cf in cat_fields
                        )
                        lines.append(f'          <cols>{cols_str}</cols>')
                    if val_fields:
                        rows_str = ", ".join(
                            f'[{vf.get("column", vf.get("ref", ""))}]' for vf in val_fields
                        )
                        lines.append(f'          <rows>{rows_str}</rows>')

                lines.append(f'        </view>')
                lines.append(f'      </table>')
                lines.append(f'    </worksheet>')
        else:
            lines.append('    <worksheet name="Migrated Sheet">')
            lines.append('      <table><view><mark class="Automatic" /></view></table>')
            lines.append('    </worksheet>')

        lines.append('  </worksheets>')

        # ── Dashboards ────────────────────────────────────────────
        lines.append('  <dashboards>')
        if pages and len(pages) > 1:
            lines.append('    <dashboard name="Migrated Dashboard">')
            for page in pages:
                lines.append(f'      <zone name="{page.get("name", "Sheet")}" type="layout-flow" />')
            lines.append('    </dashboard>')
        lines.append('  </dashboards>')

        lines.append('</workbook>')
        return "\n".join(lines)

    # ══════════════════════════════════════════════════════════════════
    #  CSV GENERATORS
    # ══════════════════════════════════════════════════════════════════

    def _to_pbi_type(self, src_type: str) -> str:
        return {
            "string": "string", "integer": "int64", "real": "double",
            "float": "double", "decimal": "decimal",
            "date": "dateTime", "datetime": "dateTime", "boolean": "boolean",
        }.get(src_type, "string")

    def _fields_csv(self, ctx: dict) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Source Field", "Source Table", "Source Type",
                     "Target Field", "Target Type", "Role",
                     "Is Calculated", "Hidden", "Format", "Status"])

        fmt = ctx["source_format"]
        for f in ctx.get("field_inventory", []):
            src_name = f["source_name"]
            src_table = f["source_table"]
            src_type = f["source_type"]
            clean = src_name.strip("[]")

            if fmt in ("twbx", "twb"):
                tgt_field = f"{src_table}[{clean}]"
                tgt_type = self._to_pbi_type(src_type)
            else:
                tgt_field = f"[{clean}]"
                tgt_type = self.PBI_TO_TABLEAU_TYPE.get(src_type, "string")

            status = "mapped" if not f["is_calc"] else "needs_review"
            w.writerow([src_name, src_table, src_type,
                        tgt_field, tgt_type, f["role"],
                        f["is_calc"], f.get("hidden", False),
                        f.get("format_string", ""), status])

        return buf.getvalue().encode("utf-8")

    def _visuals_csv(self, ctx: dict) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        meta = ctx.get("source_meta", {})
        fmt = ctx["source_format"]

        if fmt in ("twbx", "twb"):
            w.writerow(["Worksheet", "Tableau Mark", "PBI Visual Type",
                        "Row Fields", "Col Fields", "Color Encoding", "Filters"])
            for ws in meta.get("worksheets", []):
                rows = ", ".join(
                    r.get("field", str(r)) if isinstance(r, dict) else str(r)
                    for r in ws.get("rows", [])
                )
                cols = ", ".join(
                    c.get("field", str(c)) if isinstance(c, dict) else str(c)
                    for c in ws.get("cols", [])
                )
                color = ws.get("encodings", {}).get("color", "")
                filters = ", ".join(ws.get("filters", []))
                mark = ws.get("mark_type", "Automatic")
                pbi = self.TABLEAU_TO_PBI_VISUAL.get(mark.lower(), "clusteredColumnChart")
                w.writerow([ws["name"], mark, pbi, rows, cols, color, filters])
        else:
            w.writerow(["Page", "Visual Type", "Tableau Mark",
                        "Projections", "Filters"])
            for page in meta.get("pages", []):
                for vis in page.get("visuals", []):
                    vtype = vis.get("type", "")
                    tmark = self.PBI_TO_TABLEAU_MARK.get(vtype, "Automatic")
                    projs = "; ".join(
                        f"{k}: {', '.join(f2.get('column','') for f2 in v)}"
                        for k, v in vis.get("projections", {}).items()
                    )
                    flts = str(len(vis.get("filters", [])))
                    w.writerow([page["name"], vtype, tmark, projs, flts])

        return buf.getvalue().encode("utf-8")

    def _formulas_csv(self, ctx: dict) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["Field Name", "Original Formula", "Translated Formula",
                     "Confidence", "Notes"])
        for f in ctx.get("translated_formulas", []):
            w.writerow([
                f.get("name", ""),
                f.get("original_formula", ""),
                f.get("translated_formula", ""),
                f.get("confidence", ""),
                f.get("notes", ""),
            ])
        return buf.getvalue().encode("utf-8")

    def _relationships_csv(self, ctx: dict) -> bytes:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["From Table", "From Column", "To Table", "To Column",
                     "Cardinality", "Cross Filter", "Active"])
        for r in ctx.get("source_meta", {}).get("relationships", []):
            w.writerow([
                r.get("from_table", ""),
                r.get("from_column", ""),
                r.get("to_table", ""),
                r.get("to_column", ""),
                r.get("cardinality", ""),
                r.get("cross_filter", ""),
                r.get("active", True),
            ])
        return buf.getvalue().encode("utf-8")
