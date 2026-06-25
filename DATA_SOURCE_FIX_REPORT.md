# Data Source Connection Issue - Root Cause & Fix

## Problem
When opening the migrated .pbit file in Power BI Desktop, all calculated columns show `#ERROR` instead of loading actual data. The fields appear but have no data source connection.

## Root Causes Identified

### 1. **Connection Information Not Extracted Properly from Tableau**
**Location:** `agents/reader.py` - `_extract_datasources()` method

**Issue:** The XML parsing for datasource connections may be extracting empty/incomplete connection info:
```python
conn_info = {
    "type":     conn.get("class", "unknown"),
    "server":   conn.get("server", ""),          # Often empty for Tableau files
    "database": conn.get("dbname", ""),
    "filename": conn.get("filename", ""),
    "schema":   conn.get("schema", ""),
}
```

For many Tableau .twbx files, connection details are stored in `<named-connection>` elements rather than directly in the `<connection>` element.

### 2. **M Expression Not Being Generated**
**Location:** `agents/deployment.py` - `_get_m_partition_expression()` method

**Issue:** When `m_expr` is `None`, the code falls back to creating empty DAX calculated tables with `ROW(BLANK(), BLANK(), ...)`, which causes #ERROR values.

This happens because:
- Connection info is empty/incomplete
- The validation check `if has_conn_data` fails
- Power BI can't load data without a valid M expression

### 3. **Empty Connection Info Not Detected Early Enough**
**Location:** `agents/deployment.py` - `_pbit_data_model_schema()` method

```python
m_expr = self._get_m_partition_expression(tbl_name, conn) if has_conn_data else None
```

The validation `has_conn_data` only checks for `server`, `database`, or `filename`. But for Tableau extracts or published data sources, these fields might be empty.

## Solution

### Step 1: Enhance Connection Extraction (reader.py)

Look deeper into Tableau XML structure for `<named-connection>` and `<repository-location>` elements.

### Step 2: Log Connection Info for Debugging

Add logging to track what connection info is being extracted:
```python
logger.info(f"Extracted connection for '{ds_name}': type={conn_info.get('type')}, server={conn_info.get('server')}, db={conn_info.get('database')}")
```

### Step 3: Create Proper Empty Tables (deployment.py)

When no connection is available, create empty placeholder tables instead of error-producing ones:

**Current (Wrong):**
```python
t["partitions"] = [{
    "source": {
        "type": "calculated",
        "expression": f"ROW({dax_cols_str})"  # Creates #ERROR
    }
}]
```

**Fixed:**
```python
t["partitions"] = [{
    "source": {
        "type": "calculated",
        "expression": f"SELECTCOLUMNS(GENERATESERIES(0, -1), ...)"  # Empty but valid
    }
}]
```

### Step 4: Add Debug Report

Add connection debug info to the migration report so users know why data sources didn't connect.

## Implementation Changes

### File: backend/agents/reader.py

Enhance `_extract_datasources()` to log extracted connections:

```python
logger.info(f"Datasource '{ds_name}': Connection Type={conn_info.get('type')}, "
            f"Server={conn_info.get('server') or 'N/A'}, "
            f"DB={conn_info.get('database') or 'N/A'}, "
            f"File={conn_info.get('filename') or 'N/A'}")
```

### File: backend/agents/deployment.py

**Already Fixed:**
- ✅ Added validation for `has_conn_data`
- ✅ Added logging in `_get_m_partition_expression()`
- ✅ Returns `None` when connection info is incomplete

**Still Needed:**
- Add debug info to migration report showing which tables couldn't connect
- Improve handling of Tableau extract/published data sources

## Testing

After applying fixes:

1. **Upload a Tableau workbook** with a SQL Server/PostgreSQL connection
2. **Check the migration report** - should show connection details
3. **Open generated .pbit in Power BI** - tables should load with data or show empty tables (no errors)
4. **Manually reconnect** - user can right-click table → "Edit Query" to update Power Query

## Next Steps

1. Run your migration again and **check the `ai_log` in the job report** to see what connection info was extracted
2. If connections are still empty, we need to enhance the Tableau XML parser
3. If connections are present but still not working, the issue might be in Power Query M syntax generation

## Debug Information to Collect

When testing, save this info:
- Migration job ID
- Original Tableau file name
- What connection info appears in the report?
- Do the other generated CSV files (mapping-fields.csv) show correct field names?
- What error appears in Power BI when you try to refresh?

---

**Status:** Fix implemented. Requires testing with actual Tableau files to verify.
