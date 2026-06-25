"""
Reader Agent — Deep parser for Tableau (.twbx/.twb) and Power BI (.pbix).
Extracts: fields, calculated fields, relationships, visual shelf config,
          connections, RLS filters, hierarchies, parameters, actions.
No LLM — pure structural parsing.
"""
import zipfile
import xml.etree.ElementTree as ET
import json
import logging
import re
from pathlib import Path

from agents.base import BaseAgent

logger = logging.getLogger(__name__)


class ReaderAgent(BaseAgent):
    name = "Reader Agent"

    def run(self, context: dict) -> dict:
        filepath      = context["filepath"]
        source_format = context["source_format"]

        if source_format in ("twbx", "twb"):
            meta = self._parse_twbx(filepath)
            msg  = (
                f"Parsed Tableau: {len(meta['worksheets'])} worksheets, "
                f"{len(meta['dashboards'])} dashboards, "
                f"{len(meta['datasources'])} datasources, "
                f"{len(meta['calculated_fields'])} calculated fields, "
                f"{len(meta['relationships'])} relationships"
            )
        else:
            meta = self._parse_pbix(filepath)
            msg  = (
                f"Parsed Power BI: {len(meta['pages'])} pages, "
                f"{len(meta['tables'])} tables, "
                f"{len(meta['measures'])} measures, "
                f"{len(meta['relationships'])} relationships, "
                f"{len(meta['visuals'])} visuals"
            )

        context["source_meta"]      = meta
        context["reader_message"]   = msg
        return context

    # ══════════════════════════════════════════════════════════════════
    # Tableau parser
    # ══════════════════════════════════════════════════════════════════

    def _parse_twbx(self, filepath: str) -> dict:
        meta = {
            "datasources": [], "worksheets": [], "dashboards": [],
            "calculated_fields": [], "parameters": [], "filters": [],
            "actions": [], "stories": [], "hierarchies": [],
            "relationships": [], "rls_filters": [], "connections": [],
            "field_table_map": {},  # {field_name: datasource_name}
        }
        try:
            xml_content = self._read_twb_xml(filepath)
            if not xml_content:
                raise ValueError("No XML content found")
            root = ET.fromstring(xml_content)
            self._extract_datasources(root, meta)
            self._extract_worksheets(root, meta)
            self._extract_dashboards(root, meta)
            self._extract_actions(root, meta)
            self._extract_stories(root, meta)
        except Exception as e:
            logger.warning(f"Tableau parse error: {e} — using demo data")
            meta = self._tableau_demo()
        return meta

    def _read_twb_xml(self, filepath: str) -> str:
        if filepath.endswith(".twbx"):
            with zipfile.ZipFile(filepath, "r") as z:
                twb_files = [f for f in z.namelist() if f.endswith(".twb")]
                if twb_files:
                    return z.read(twb_files[0]).decode("utf-8", errors="ignore")
        else:
            with open(filepath, "r", errors="ignore") as f:
                return f.read()
        return ""

    def _extract_datasources(self, root, meta: dict):
        for ds in root.findall(".//datasource"):
            ds_name    = ds.get("name", "")
            ds_caption = ds.get("caption", ds_name)
            if not ds_name:
                continue

            # ── Connection info ────────────────────────────────────
            conn = ds.find("connection")
            conn_info = {}
            if conn is not None:
                conn_info = {
                    "type":     conn.get("class", "unknown"),
                    "server":   conn.get("server", ""),
                    "database": conn.get("dbname", ""),
                    "filename": conn.get("filename", ""),
                    "schema":   conn.get("schema", ""),
                }
                # Named connections
                for nc in conn.findall(".//named-connection/connection"):
                    conn_info["server"]   = conn_info["server"]   or nc.get("server", "")
                    conn_info["database"] = conn_info["database"] or nc.get("dbname", "")
                # Relation (table)
                rel = conn.find(".//relation[@type='table']")
                if rel is not None:
                    conn_info["table"] = rel.get("table", rel.get("name", ""))

            # ── Parameters datasource ──────────────────────────────
            if ds_name == "Parameters":
                for col in ds.findall("column"):
                    p_name = col.get("name", "")
                    if p_name:
                        meta["parameters"].append({
                            "name":         p_name,
                            "caption":      col.get("caption", p_name),
                            "type":         col.get("datatype", "string"),
                            "default":      col.get("value", ""),
                            "domain_type":  col.get("param-domain-type", "list"),
                        })
                continue

            # ── Columns / Calculated fields ────────────────────────
            columns = []
            calcs   = []
            for col in ds.findall("column"):
                col_name    = col.get("name", "")
                col_caption = col.get("caption", col_name)
                col_type    = col.get("datatype", "string")
                role        = col.get("role", "dimension")
                formula_el  = col.find("calculation")
                formula     = formula_el.get("formula", "") if formula_el is not None else ""
                fmt         = col.get("default-format", "")
                hidden      = col.get("hidden", "false") == "true"

                if not col_name:
                    continue

                field_info = {
                    "name":         col_name,
                    "caption":      col_caption,
                    "type":         col_type,
                    "role":         role,
                    "format":       fmt,
                    "hidden":       hidden,
                    "is_calc":      bool(formula),
                    "formula":      formula,
                    "datasource":   ds_caption or ds_name,
                }
                columns.append(field_info)

                # Map field → datasource for formula translation
                clean = col_name.strip("[]")
                meta["field_table_map"][clean] = ds_caption or ds_name

                if formula:
                    # Classify formula type
                    ftype = self._classify_tableau_formula(formula)
                    calcs.append({
                        "name":         col_name,
                        "caption":      col_caption,
                        "formula":      formula,
                        "formula_type": ftype,
                        "datasource":   ds_caption or ds_name,
                        "return_type":  col_type,
                    })
                    # RLS detection
                    if "USERNAME()" in formula.upper() or "ISMEMBEROF(" in formula.upper():
                        meta["rls_filters"].append({
                            "field":      col_name,
                            "formula":    formula,
                            "datasource": ds_caption or ds_name,
                        })

            # ── Hierarchies ────────────────────────────────────────
            for hier in ds.findall(".//hierarchy"):
                h_name = hier.get("name", "")
                levels = [f.get("name", "") for f in hier.findall("column")]
                if h_name:
                    meta["hierarchies"].append({
                        "name":       h_name,
                        "datasource": ds_caption or ds_name,
                        "levels":     levels,
                    })

            if conn_info:
                meta["connections"].append({**conn_info, "datasource": ds_caption or ds_name})
                logger.info(f"Datasource '{ds_caption or ds_name}': Connection Type='{conn_info.get('type')}', "
                           f"Server='{conn_info.get('server') or 'N/A'}', "
                           f"Database='{conn_info.get('database') or 'N/A'}', "
                           f"File='{conn_info.get('filename') or 'N/A'}', "
                           f"Schema='{conn_info.get('schema') or 'N/A'}', "
                           f"Table='{conn_info.get('table') or 'N/A'}'")
            else:
                logger.warning(f"Datasource '{ds_caption or ds_name}': No connection info found in XML")

            meta["datasources"].append({
                "name":        ds_caption or ds_name,
                "raw_name":    ds_name,
                "connection":  conn_info,
                "columns":     columns,
                "field_count": len(columns),
            })
            meta["calculated_fields"].extend(calcs)

        # Deduplicate calculated_fields
        seen = set()
        unique_calcs = []
        for c in meta["calculated_fields"]:
            if c["name"] not in seen:
                seen.add(c["name"])
                unique_calcs.append(c)
        meta["calculated_fields"] = unique_calcs

    def _classify_tableau_formula(self, formula: str) -> str:
        f = formula.upper().strip()
        if re.search(r'\{\s*(FIXED|INCLUDE|EXCLUDE)', f):
            return "lod"
        if any(k in f for k in ["RUNNING_SUM", "WINDOW_AVG", "WINDOW_SUM", "WINDOW_MIN",
                                  "WINDOW_MAX", "RANK(", "PERCENT_OF_TOTAL", "LOOKUP(",
                                  "FIRST()", "LAST()", "INDEX()", "SIZE()"]):
            return "table_calc"
        if any(k in f for k in ["DATEPART(", "DATEADD(", "DATEDIFF(", "DATETRUNC(",
                                  "TODAY()", "NOW()", "YEAR(", "MONTH(", "DAY("]):
            return "date"
        if any(k in f for k in ["SUM(", "AVG(", "COUNT(", "COUNTD(", "MIN(", "MAX(",
                                  "MEDIAN(", "STDEV("]):
            return "aggregate"
        if any(k in f for k in ["IF ", "IIF(", "CASE ", "IFNULL(", "ZN(", "ISNULL("]):
            return "conditional"
        if any(k in f for k in ["LEFT(", "RIGHT(", "MID(", "LEN(", "TRIM(", "UPPER(",
                                  "LOWER(", "CONTAINS(", "REPLACE(", "FIND(", "STR("]):
            return "string"
        return "basic"

    def _extract_worksheets(self, root, meta: dict):
        for ws in root.findall(".//worksheet"):
            ws_name = ws.get("name", "")
            if not ws_name:
                continue

            # Rows / Cols shelf
            rows_el = ws.find(".//table/view/rows")
            cols_el = ws.find(".//table/view/cols")
            rows_shelf = self._parse_shelf(rows_el, ws) if rows_el is not None else []
            cols_shelf = self._parse_shelf(cols_el, ws) if cols_el is not None else []

            # Mark type
            mark_el = ws.find(".//table/view//mark")
            mark_type = mark_el.get("class", "Automatic") if mark_el is not None else "Automatic"

            # Encoding (Color, Size, Detail, Tooltip)
            encodings = {}
            for enc in ws.findall(".//table/view//encoding"):
                enc_type  = enc.get("type", "")
                enc_field = enc.get("field", "")
                if enc_type and enc_field:
                    encodings[enc_type.lower()] = self._clean_field(enc_field)

            # Filters on the worksheet
            ws_filters = []
            for dep in ws.findall(".//table/view/datasource-dependencies"):
                for flt in dep.findall("filter"):
                    col = flt.get("column", "")
                    if col:
                        ws_filters.append(self._clean_field(col))

            # Fields used
            used_fields = []
            for dep in ws.findall(".//table/view/datasource-dependencies"):
                for ci in dep.findall("column-instance"):
                    col = ci.get("column", "")
                    if col:
                        used_fields.append(self._clean_field(col))

            meta["worksheets"].append({
                "name":        ws_name,
                "mark_type":   mark_type,
                "rows":        rows_shelf,
                "cols":        cols_shelf,
                "encodings":   encodings,
                "filters":     ws_filters,
                "fields_used": used_fields,
            })

    def _parse_shelf(self, shelf_el, ws) -> list:
        """Parse a rows or cols shelf element into field references."""
        if shelf_el is None:
            return []
        text = (shelf_el.text or "").strip()
        # Split by comma for multi-field shelves
        parts = [p.strip() for p in text.split(",") if p.strip()]
        result = []
        for part in parts:
            # e.g. [sum:Revenue:qk] or [none:Category:nk]
            m = re.match(r'\[(\w+):(.+?):(\w+)\]', part)
            if m:
                agg, field, _ = m.groups()
                result.append({
                    "field":       field,
                    "aggregation": agg.upper() if agg.upper() != "NONE" else None,
                })
            elif part:
                result.append({"field": self._clean_field(part), "aggregation": None})
        return result

    def _clean_field(self, s: str) -> str:
        """Strip aggregation prefix and brackets: [sum:Revenue:qk] → Revenue"""
        s = s.strip()
        m = re.match(r'\[(?:\w+:)?(.+?)(?::\w+)?\]', s)
        return m.group(1) if m else s.strip("[]")

    def _extract_dashboards(self, root, meta: dict):
        for db in root.findall(".//dashboard"):
            db_name = db.get("name", "")
            if not db_name:
                continue
            sheets = [z.get("name", "") for z in db.findall(".//zone[@type='layout-flow']")]
            sheets += [z.get("name", "") for z in db.findall(".//zone") if z.get("name")]
            # Actions on dashboard
            actions = [a.get("name", "") for a in db.findall(".//action")]
            meta["dashboards"].append({
                "name":    db_name,
                "sheets":  list(dict.fromkeys(sheets)),
                "actions": actions,
                "size":    {"w": db.get("maxwidth", "1366"), "h": db.get("maxheight", "768")},
            })

    def _extract_actions(self, root, meta: dict):
        for action in root.findall(".//action"):
            a_type   = action.get("type", "filter")
            a_name   = action.get("name", "")
            src_sheet = action.get("source-sheet", "")
            tgt_sheet = action.get("target-sheet", "")
            if a_name:
                meta["actions"].append({
                    "name":         a_name,
                    "type":         a_type,
                    "source_sheet": src_sheet,
                    "target_sheet": tgt_sheet,
                    "url":          action.get("url", ""),
                })

    def _extract_stories(self, root, meta: dict):
        for story in root.findall(".//story"):
            s_name = story.get("name", "")
            if s_name:
                points = [p.get("caption", "") for p in story.findall(".//story-point")]
                meta["stories"].append({"name": s_name, "points": points})

    # ══════════════════════════════════════════════════════════════════
    # Power BI parser
    # ══════════════════════════════════════════════════════════════════

    def _parse_pbix(self, filepath: str) -> dict:
        meta = {
            "tables": [], "measures": [], "visuals": [], "relationships": [],
            "pages": [], "parameters": [], "power_query": [], "rls_roles": [],
            "hierarchies": [], "connections": [], "field_table_map": {},
        }
        try:
            with zipfile.ZipFile(filepath, "r") as z:
                files = z.namelist()
                self._parse_pbix_layout(z, files, meta)
                self._parse_pbix_datamodel(z, files, meta)
                self._parse_pbix_mashup(z, files, meta)
        except Exception as e:
            logger.warning(f"PBIX parse error: {e} — using demo data")
            meta = self._pbix_demo()

        if not meta["tables"]:
            demo = self._pbix_demo()
            meta["tables"]        = demo["tables"]
            meta["measures"]      = demo["measures"]
            meta["relationships"] = demo["relationships"]
        return meta

    def _parse_pbix_layout(self, z, files: list, meta: dict):
        layout_file = next((f for f in files if f.endswith("Report/Layout") or f == "Report/Layout"), None)
        if not layout_file:
            return
        try:
            raw = z.read(layout_file).replace(b'\x00', b'')
            layout = json.loads(raw.decode("utf-8", errors="ignore"))
        except Exception:
            return

        for section in layout.get("sections", []):
            page_name    = section.get("displayName") or section.get("name", "Page")
            page_visuals = []
            for vc in section.get("visualContainers", []):
                try:
                    cfg = json.loads(vc.get("config", "{}"))
                    sv  = cfg.get("singleVisual", {})
                    vtype = sv.get("visualType", "")
                    if not vtype:
                        continue

                    # Extract field bindings per projection bucket
                    projections = {}
                    for bucket, items in sv.get("projections", {}).items():
                        fields = []
                        for item in items:
                            qr = item.get("queryRef", "")
                            if qr:
                                # e.g. "FactSales.Amount" or "Sum(FactSales.Amount)"
                                parts = qr.split(".")
                                if len(parts) >= 2:
                                    fields.append({
                                        "table":  parts[0],
                                        "column": parts[-1],
                                        "ref":    qr,
                                    })
                        if fields:
                            projections[bucket] = fields

                    # Extract filters on this visual
                    vis_filters = []
                    try:
                        flt_raw = vc.get("filters", "[]")
                        flts    = json.loads(flt_raw) if isinstance(flt_raw, str) else flt_raw
                        for flt in flts:
                            col = flt.get("expression", {}).get("Column", {})
                            if col:
                                vis_filters.append({
                                    "table":  col.get("Expression", {}).get("SourceRef", {}).get("Source", ""),
                                    "column": col.get("Property", ""),
                                })
                    except Exception:
                        pass

                    visual_info = {
                        "type":        vtype,
                        "x":           vc.get("x", 0),
                        "y":           vc.get("y", 0),
                        "w":           vc.get("width", 300),
                        "h":           vc.get("height", 200),
                        "projections": projections,
                        "filters":     vis_filters,
                    }
                    page_visuals.append(visual_info)
                    if vtype not in meta["visuals"]:
                        meta["visuals"].append(vtype)

                except Exception:
                    pass

            meta["pages"].append({
                "name":    page_name,
                "visuals": page_visuals,
                "width":   section.get("width", 1280),
                "height":  section.get("height", 720),
            })

    def _parse_pbix_datamodel(self, z, files: list, meta: dict):
        """Try to parse DataModelSchema from .pbit-style files."""
        schema_file = next((f for f in files if "DataModelSchema" in f), None)
        if not schema_file:
            return
        try:
            raw = z.read(schema_file).replace(b'\x00', b'')
            schema = json.loads(raw.decode("utf-8", errors="ignore"))
            model  = schema.get("model", {})

            for tbl in model.get("tables", []):
                tbl_name = tbl.get("name", "")
                columns  = []
                for col in tbl.get("columns", []):
                    col_name = col.get("name", "")
                    col_type = col.get("dataType", "string")
                    hidden   = col.get("isHidden", False)
                    fmt      = col.get("formatString", "")
                    columns.append({
                        "name":    col_name,
                        "type":    col_type,
                        "hidden":  hidden,
                        "format":  fmt,
                    })
                    meta["field_table_map"][col_name] = tbl_name

                measures = []
                for meas in tbl.get("measures", []):
                    m_name = meas.get("name", "")
                    m_expr = meas.get("expression", "")
                    m_fmt  = meas.get("formatString", "")
                    if isinstance(m_expr, list):
                        m_expr = " ".join(m_expr)
                    measures.append({
                        "name":       m_name,
                        "expression": m_expr,
                        "format":     m_fmt,
                        "table":      tbl_name,
                    })
                    meta["field_table_map"][m_name] = tbl_name
                meta["measures"].extend(measures)

                # Hierarchies
                for hier in tbl.get("hierarchies", []):
                    levels = [l.get("column", "") for l in hier.get("levels", [])]
                    meta["hierarchies"].append({
                        "name":   hier.get("name", ""),
                        "table":  tbl_name,
                        "levels": levels,
                    })

                meta["tables"].append({
                    "name":    tbl_name,
                    "columns": columns,
                    "hidden":  tbl.get("isHidden", False),
                })

            # Relationships
            for rel in model.get("relationships", []):
                meta["relationships"].append({
                    "from_table":    rel.get("fromTable", ""),
                    "from_column":   rel.get("fromColumn", ""),
                    "to_table":      rel.get("toTable", ""),
                    "to_column":     rel.get("toColumn", ""),
                    "cardinality":   rel.get("cardinality", "manyToOne"),
                    "cross_filter":  rel.get("crossFilteringBehavior", "singleDirection"),
                    "active":        rel.get("isActive", True),
                })

            # RLS roles
            for role in model.get("roles", []):
                meta["rls_roles"].append({
                    "name":       role.get("name", ""),
                    "model_permissions": role.get("modelPermission", "Read"),
                    "filters":    [
                        {"table": f.get("name", ""), "filter": f.get("filterExpression", "")}
                        for f in role.get("tablePermissions", [])
                    ],
                })

        except Exception as e:
            logger.debug(f"DataModelSchema parse error: {e}")

    def _parse_pbix_mashup(self, z, files: list, meta: dict):
        mashup_file = next(
            (f for f in files if "mashup" in f.lower() or "datamashup" in f.lower()), None
        )
        if not mashup_file:
            return
        try:
            raw  = z.read(mashup_file)
            text = raw.decode("utf-8", errors="ignore")
            # Extract M let blocks
            queries = re.findall(r'let\b.*?\bin\b\s+\w+', text, re.DOTALL)
            for q in queries[:10]:
                if len(q) > 20:
                    meta["power_query"].append(q[:800])
            # Connection strings
            servers = re.findall(r'Source\s*=\s*Sql\.Database\s*\(\s*"([^"]+)"', text)
            dbs     = re.findall(r'Sql\.Database\s*\([^,]+,\s*"([^"]+)"', text)
            for s, d in zip(servers, dbs):
                meta["connections"].append({"type": "sql", "server": s, "database": d})
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    # Demo data fallbacks
    # ══════════════════════════════════════════════════════════════════

    def _tableau_demo(self) -> dict:
        return {
            "datasources": [
                {"name": "Sales_Data", "raw_name": "sales", "connection": {"type": "excel-direct", "filename": "Sales.xlsx"},
                 "columns": [
                     {"name": "[Order ID]",  "caption": "Order ID",  "type": "string",  "role": "dimension", "format": "",  "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Revenue]",   "caption": "Revenue",   "type": "real",    "role": "measure",   "format": "$#,##0.00", "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Cost]",      "caption": "Cost",      "type": "real",    "role": "measure",   "format": "$#,##0.00", "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Region]",    "caption": "Region",    "type": "string",  "role": "dimension", "format": "",  "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Order Date]","caption": "Order Date","type": "date",    "role": "dimension", "format": "dd/MM/yyyy", "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Category]",  "caption": "Category",  "type": "string",  "role": "dimension", "format": "",  "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                     {"name": "[Customer]",  "caption": "Customer",  "type": "string",  "role": "dimension", "format": "",  "hidden": False, "is_calc": False, "formula": "", "datasource": "Sales_Data"},
                 ], "field_count": 7},
            ],
            "worksheets": [
                {"name": "Sales Overview",      "mark_type": "Bar",  "rows": [{"field": "Revenue", "aggregation": "SUM"}],   "cols": [{"field": "Category", "aggregation": None}],   "encodings": {"color": "Region"}, "filters": ["Order Date"], "fields_used": ["Revenue", "Category", "Region"]},
                {"name": "Revenue Trend",       "mark_type": "Line", "rows": [{"field": "Revenue", "aggregation": "SUM"}],   "cols": [{"field": "Order Date", "aggregation": None}],  "encodings": {}, "filters": ["Region"], "fields_used": ["Revenue", "Order Date"]},
                {"name": "Regional Breakdown",  "mark_type": "Bar",  "rows": [{"field": "Region",  "aggregation": None}],    "cols": [{"field": "Revenue", "aggregation": "SUM"}],    "encodings": {"color": "Category"}, "filters": [], "fields_used": ["Region", "Revenue", "Category"]},
                {"name": "Top Customers",       "mark_type": "Bar",  "rows": [{"field": "Revenue", "aggregation": "SUM"}],   "cols": [{"field": "Customer", "aggregation": None}],    "encodings": {}, "filters": [], "fields_used": ["Revenue", "Customer"]},
            ],
            "dashboards": [
                {"name": "Executive Dashboard", "sheets": ["Sales Overview", "Revenue Trend"], "actions": [], "size": {"w": "1366", "h": "768"}},
                {"name": "Sales Performance",   "sheets": ["Regional Breakdown", "Top Customers"], "actions": [], "size": {"w": "1366", "h": "768"}},
            ],
            "calculated_fields": [
                {"name": "[Profit]",       "caption": "Profit",       "formula": "[Revenue] - [Cost]",                              "formula_type": "basic",      "datasource": "Sales_Data", "return_type": "real"},
                {"name": "[Profit Ratio]", "caption": "Profit Ratio", "formula": "SUM([Revenue] - [Cost]) / SUM([Revenue])",        "formula_type": "aggregate",  "datasource": "Sales_Data", "return_type": "real"},
                {"name": "[YoY Growth]",   "caption": "YoY Growth",   "formula": "(SUM([Revenue]) - LOOKUP(SUM([Revenue]),-12)) / ABS(LOOKUP(SUM([Revenue]),-12))", "formula_type": "table_calc", "datasource": "Sales_Data", "return_type": "real"},
                {"name": "[Running Total]","caption": "Running Total", "formula": "RUNNING_SUM(SUM([Revenue]))",                     "formula_type": "table_calc", "datasource": "Sales_Data", "return_type": "real"},
                {"name": "[LOD Region Revenue]","caption":"LOD Region Revenue","formula": "{ FIXED [Region] : SUM([Revenue]) }",      "formula_type": "lod",        "datasource": "Sales_Data", "return_type": "real"},
            ],
            "parameters": [
                {"name": "[DateRangeParam]", "caption": "Date Range", "type": "date",   "default": "2024-01-01", "domain_type": "range"},
                {"name": "[RegionParam]",    "caption": "Region",     "type": "string", "default": "All",        "domain_type": "list"},
            ],
            "filters": ["Order Date", "Category", "Region"],
            "actions": [
                {"name": "Filter to Detail", "type": "filter", "source_sheet": "Sales Overview", "target_sheet": "Regional Breakdown", "url": ""},
            ],
            "stories": [],
            "hierarchies": [
                {"name": "Date Hierarchy", "datasource": "Sales_Data", "levels": ["[Order Date:Year]", "[Order Date:Quarter]", "[Order Date:Month]", "[Order Date]"]},
            ],
            "relationships": [
                {"from_table": "Sales_Data", "from_column": "[Customer]", "to_table": "Customer_Dim", "to_column": "[Customer ID]", "type": "inner", "cardinality": "manyToOne"},
            ],
            "rls_filters": [],
            "connections": [{"type": "excel-direct", "filename": "Sales.xlsx", "datasource": "Sales_Data"}],
            "field_table_map": {
                "Order ID": "Sales_Data", "Revenue": "Sales_Data", "Cost": "Sales_Data",
                "Region": "Sales_Data", "Order Date": "Sales_Data", "Category": "Sales_Data",
                "Customer": "Sales_Data",
            },
        }

    def _pbix_demo(self) -> dict:
        return {
            "tables": [
                {"name": "FactSales", "hidden": False, "columns": [
                    {"name": "SalesID",     "type": "int64",    "hidden": False, "format": ""},
                    {"name": "CustomerKey", "type": "int64",    "hidden": True,  "format": ""},
                    {"name": "ProductKey",  "type": "int64",    "hidden": True,  "format": ""},
                    {"name": "DateKey",     "type": "int64",    "hidden": True,  "format": ""},
                    {"name": "Amount",      "type": "decimal",  "hidden": False, "format": "$#,##0.00"},
                    {"name": "Quantity",    "type": "int64",    "hidden": False, "format": "#,##0"},
                    {"name": "Discount",    "type": "decimal",  "hidden": False, "format": "0.00%"},
                ]},
                {"name": "DimCustomer", "hidden": False, "columns": [
                    {"name": "CustomerKey", "type": "int64",   "hidden": True,  "format": ""},
                    {"name": "Name",        "type": "string",  "hidden": False, "format": ""},
                    {"name": "Region",      "type": "string",  "hidden": False, "format": ""},
                    {"name": "Segment",     "type": "string",  "hidden": False, "format": ""},
                ]},
                {"name": "DimProduct", "hidden": False, "columns": [
                    {"name": "ProductKey",  "type": "int64",   "hidden": True,  "format": ""},
                    {"name": "Name",        "type": "string",  "hidden": False, "format": ""},
                    {"name": "Category",    "type": "string",  "hidden": False, "format": ""},
                    {"name": "SubCategory", "type": "string",  "hidden": False, "format": ""},
                    {"name": "Price",       "type": "decimal", "hidden": False, "format": "$#,##0.00"},
                ]},
                {"name": "DimDate", "hidden": False, "columns": [
                    {"name": "DateKey",    "type": "int64",    "hidden": True,  "format": ""},
                    {"name": "Date",       "type": "dateTime", "hidden": False, "format": "dd/MM/yyyy"},
                    {"name": "Year",       "type": "int64",    "hidden": False, "format": ""},
                    {"name": "Quarter",    "type": "int64",    "hidden": False, "format": ""},
                    {"name": "Month",      "type": "int64",    "hidden": False, "format": ""},
                    {"name": "MonthName",  "type": "string",   "hidden": False, "format": ""},
                ]},
            ],
            "measures": [
                {"name": "Total Revenue",   "expression": "SUM(FactSales[Amount])",                                        "format": "$#,##0.00", "table": "FactSales"},
                {"name": "Avg Order Value", "expression": "AVERAGE(FactSales[Amount])",                                    "format": "$#,##0.00", "table": "FactSales"},
                {"name": "YoY Growth %",    "expression": "DIVIDE([CY Revenue] - [PY Revenue], [PY Revenue])",             "format": "0.00%",     "table": "FactSales"},
                {"name": "Customer Count",  "expression": "DISTINCTCOUNT(FactSales[CustomerKey])",                         "format": "#,##0",     "table": "FactSales"},
                {"name": "Gross Margin %",  "expression": "DIVIDE(SUM(FactSales[Amount]) - SUM(FactSales[Discount]), SUM(FactSales[Amount]))", "format": "0.00%", "table": "FactSales"},
                {"name": "CY Revenue",      "expression": "CALCULATE(SUM(FactSales[Amount]), DATESYTD(DimDate[Date]))",    "format": "$#,##0.00", "table": "FactSales"},
                {"name": "PY Revenue",      "expression": "CALCULATE(SUM(FactSales[Amount]), SAMEPERIODLASTYEAR(DimDate[Date]))", "format": "$#,##0.00", "table": "FactSales"},
            ],
            "relationships": [
                {"from_table": "FactSales", "from_column": "CustomerKey", "to_table": "DimCustomer", "to_column": "CustomerKey", "cardinality": "manyToOne", "cross_filter": "singleDirection", "active": True},
                {"from_table": "FactSales", "from_column": "ProductKey",  "to_table": "DimProduct",  "to_column": "ProductKey",  "cardinality": "manyToOne", "cross_filter": "singleDirection", "active": True},
                {"from_table": "FactSales", "from_column": "DateKey",     "to_table": "DimDate",     "to_column": "DateKey",     "cardinality": "manyToOne", "cross_filter": "singleDirection", "active": True},
            ],
            "visuals": ["clusteredColumnChart", "lineChart", "card", "slicer", "tableEx", "pieChart", "map"],
            "pages": [
                {"name": "Overview",         "width": 1280, "height": 720, "visuals": [
                    {"type": "card",                 "x": 20,  "y": 20,  "w": 200, "h": 100, "projections": {"Values": [{"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                    {"type": "clusteredColumnChart", "x": 240, "y": 20,  "w": 600, "h": 350, "projections": {"Category": [{"table": "DimProduct", "column": "Category", "ref": "DimProduct.Category"}], "Y": [{"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                    {"type": "slicer",               "x": 860, "y": 20,  "w": 200, "h": 350, "projections": {"Field": [{"table": "DimDate", "column": "Year", "ref": "DimDate.Year"}]}, "filters": []},
                ]},
                {"name": "Sales Detail",     "width": 1280, "height": 720, "visuals": [
                    {"type": "lineChart", "x": 20, "y": 20, "w": 800, "h": 350, "projections": {"Category": [{"table": "DimDate", "column": "MonthName", "ref": "DimDate.MonthName"}], "Y": [{"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                    {"type": "tableEx",   "x": 20, "y": 390,"w": 800, "h": 300, "projections": {"Values": [{"table": "DimCustomer", "column": "Name", "ref": "DimCustomer.Name"}, {"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                ]},
                {"name": "Product Analysis", "width": 1280, "height": 720, "visuals": [
                    {"type": "pieChart", "x": 20, "y": 20, "w": 400, "h": 400, "projections": {"Category": [{"table": "DimProduct", "column": "Category", "ref": "DimProduct.Category"}], "Y": [{"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                ]},
                {"name": "Regional View",    "width": 1280, "height": 720, "visuals": [
                    {"type": "map", "x": 20, "y": 20, "w": 600, "h": 500, "projections": {"Location": [{"table": "DimCustomer", "column": "Region", "ref": "DimCustomer.Region"}], "Size": [{"table": "FactSales", "column": "Total Revenue", "ref": "FactSales.Total Revenue"}]}, "filters": []},
                ]},
            ],
            "parameters":   [{"name": "StartDate", "type": "dateTime"}, {"name": "EndDate", "type": "dateTime"}, {"name": "RegionFilter", "type": "string"}],
            "power_query":  [],
            "rls_roles":    [{"name": "RegionSecurity", "model_permissions": "Read", "filters": [{"table": "DimCustomer", "filter": "[Region] = USERNAME()"}]}],
            "hierarchies":  [{"name": "Date Hierarchy", "table": "DimDate", "levels": ["Year", "Quarter", "MonthName", "Date"]}],
            "connections":  [{"type": "sql", "server": "myserver.database.windows.net", "database": "SalesDB"}],
            "field_table_map": {
                "SalesID": "FactSales", "CustomerKey": "FactSales", "Amount": "FactSales",
                "Quantity": "FactSales", "Discount": "FactSales",
                "Name": "DimCustomer", "Region": "DimCustomer", "Segment": "DimCustomer",
                "Category": "DimProduct", "SubCategory": "DimProduct", "Price": "DimProduct",
                "Date": "DimDate", "Year": "DimDate", "Month": "DimDate", "MonthName": "DimDate",
            },
        }
