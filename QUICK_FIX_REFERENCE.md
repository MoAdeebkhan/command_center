# Quick Reference - Data Source Connection Issues

## The Problem (in 30 seconds)
Opening .pbit → Fields show `#ERROR` instead of data → Data source didn't connect

## The Root Cause
Tableau files don't always contain complete data source connection info in a format Power BI can use.

## What We Fixed
- ✅ Better connection info extraction logging
- ✅ Graceful handling when connections are missing
- ✅ Debug report showing what connections were found
- ✅ User guide for manual reconnection

## Quick Troubleshooting

### I'm seeing #ERROR in Power BI
1. Check the migration report in the output ZIP → `migration_report.json`
2. Look for `"datasource_connections"` section
3. If servers/databases are empty → **Connections not extracted**
4. If they show values → **Connections extracted, but Power BI needs to be configured**

### Run Debug Script
```bash
cd backend
python debug_connections.py <your_job_id>
```

This shows:
- What connection info was extracted
- What's missing
- Which tables are affected

### Manual Fix in Power BI
1. Open the .pbit file
2. Go to Model tab
3. Find a table, click "Edit Query"
4. Update the connection string with your actual server/database
5. Use the values from the migration report
6. Test by clicking Refresh

### More Detailed Help
See: `DATA_SOURCE_MANUAL_FIX_GUIDE.md`

---

## What Each File Does

| File | Purpose |
|------|---------|
| `DATASOURCE_CONNECTION_FIX_SUMMARY.md` | Technical summary of all changes |
| `DATA_SOURCE_FIX_REPORT.md` | Detailed root cause analysis |
| `DATA_SOURCE_MANUAL_FIX_GUIDE.md` | Step-by-step user guide for reconnecting |
| `debug_connections.py` | Utility to inspect extracted connections |
| `QUICK_FIX_REFERENCE.md` | This file - quick answer to common issues |

---

## Before & After

### Before Fix
- ❌ Connections silently failed
- ❌ All fields showed `#ERROR`
- ❌ No way to know what went wrong
- ❌ No guidance for manual fix

### After Fix
- ✅ Connections logged and reported
- ✅ Empty tables created instead of errors
- ✅ Migration report shows what was extracted
- ✅ User guide for manual reconnection
- ✅ Debug script to diagnose issues

---

## Common Scenarios

### "Connection info shows but Power BI won't connect"
→ Firewall/network issue or wrong credentials. Update connection in Power Query.

### "Connection info is empty"
→ Tableau file didn't have connection details. Manual reconnection needed.

### "Some tables work, some don't"
→ Some connections were extracted, others weren't. Check report for which ones.

### "How do I test if data loaded?"
→ Click Refresh in Power BI. If it works, no #ERROR will appear.

---

## Files in Migration Output

```
migration_[timestamp]_package.zip
├── migration_[timestamp]_migrated.pbit      ← Open this in Power BI
├── migration_report.json                     ← Check datasource_connections
├── mapping-fields.csv                        ← Field name mappings
├── mapping-formulas.csv                      ← Formula translations
├── mapping-visuals.csv                       ← Visual mappings
└── mapping-relationships.csv                 ← Relationship mappings
```

---

## Next Steps

**If connections work automatically:**
- You're done! Files are ready to use.

**If connections don't work:**
1. Extract migration_report.json
2. Find datasource_connections section
3. Run `python debug_connections.py <job_id>`
4. Follow DATA_SOURCE_MANUAL_FIX_GUIDE.md
5. Update Power Query in Power BI Desktop

---

**Questions?** Check the relevant guide file above or run the debug script.
