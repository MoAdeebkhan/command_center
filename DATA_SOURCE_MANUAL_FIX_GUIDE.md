# Manual Data Source Connection Guide

## What Happened?

Your migration created the .pbit file structure and formulas correctly, but **Power BI couldn't automatically extract the data source connection** from your Tableau file.

This is common when:
- Tableau is using embedded/published data sources
- Connection details are in named connections
- The source uses Tableau extracts (.tde files)

## How to Fix It in Power BI Desktop

### Option 1: Direct Query Connection (Recommended)

1. **Open the migrated .pbit** in Power BI Desktop
2. Go to **Model** tab (left sidebar)
3. Select a table that shows no data
4. In the **Query Editor** (Transform Data), click the data source query
5. Click **"Edit Query"** or **"Edit Parameters"** button
6. In the Power Query Editor, update the connection string:

**For SQL Server:**
```
let
    Source = Sql.Database("YOUR_SERVER_NAME", "YOUR_DATABASE"),
    Navigation = Source{[Schema="dbo",Item="YOUR_TABLE_NAME"]}[Data]
in
    Navigation
```

**For PostgreSQL:**
```
let
    Source = PostgreSQL.Database("YOUR_SERVER", "YOUR_DATABASE"),
    Navigation = Source{[Schema="public",Item="YOUR_TABLE_NAME"]}[Data]
in
    Navigation
```

**For Excel:**
```
let
    Source = Excel.Workbook(File.Contents("C:\Path\To\Your\File.xlsx"), null, true),
    Sheet = Source{[Item="Sheet1",Kind="Sheet"]}[Data],
    PromoteHeaders = Table.PromoteHeaders(Sheet, [PromoteAllScalars=true])
in
    PromoteHeaders
```

7. Click **"Done"** and then **"Close & Apply"**

### Option 2: Check the Migration Report

The migration output includes a file called `migration_report.json` with a section:

```json
{
  "datasource_connections": [
    {
      "table": "Sales",
      "type": "sqlserver",
      "server": "YOUR_SERVER",
      "database": "YOUR_DB",
      "schema": "dbo",
      "table_name": "SalesData"
    }
  ]
}
```

Use this information to fill in your Power Query connection strings.

### Option 3: Import Data from CSV

1. In Power BI, click **"Get Data"** → **"CSV"**
2. Navigate to your original data source file
3. Load it as a new table
4. Then create relationships between the empty migrated tables and this new data table

## Troubleshooting

### Issue: "Expression.Error: The key didn't match any rows..."

**Solution:** Check that the table name and schema are exactly correct. In Power Query, go back to the data source and verify:
- Server name is reachable
- Database exists and you have permissions
- Table name exists and is spelled correctly

### Issue: "The connection string is not valid"

**Solution:** You might need credentials. Click the data source step and add:
- Windows authentication
- Or database username/password

### Issue: "The table doesn't exist"

**Solution:** 
- Verify the exact table name in your source system
- Check the schema (usually "dbo" for SQL Server, "public" for PostgreSQL)
- Look in the CSV mapping file: `mapping-fields.csv` - it shows what table names were found during parsing

## Files in Your Migration Output

- **{name}_migrated.pbit** - The migrated Power BI Template (open this)
- **migration_report.json** - Detailed report including extracted connection info
- **mapping-fields.csv** - Field name mappings
- **mapping-formulas.csv** - Formula translations
- **mapping-visuals.csv** - Visual type mappings

## Next Steps

1. **Use the migration report** to get exact connection details
2. **Open the .pbit** in Power BI Desktop
3. **Update one query** with the correct connection string
4. Test by clicking **"Refresh"** to load data
5. Repeat for other tables if needed
6. Save your .pbix file

---

**Note:** These are temporary connections until a full manual reconnection. For production use, consider:
- Setting up Power BI gateways for on-premises data
- Using Power BI Premium with DirectQuery
- Publishing the report to Power BI Service with proper credentials
