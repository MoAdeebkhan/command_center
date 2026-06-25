"""
Debug script to inspect extracted connection information from a migration job.
Usage: python debug_connections.py <job_id>
"""
import json
import sys
from database import get_db


def debug_job_connections(job_id: str):
    """Print detailed connection information from a job's report."""
    
    with get_db() as db:
        job = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        
        if not job:
            print(f"❌ Job not found: {job_id}")
            sys.exit(1)
        
        print(f"\n{'='*70}")
        print(f"Job: {job_id}")
        print(f"Filename: {job['filename']}")
        print(f"Source Format: {job['source_format']} → {job['target_format']}")
        print(f"Status: {job['status']}")
        print(f"{'='*70}\n")
        
        if not job["report"]:
            print("⚠️  No report data available yet. Job may still be processing.")
            sys.exit(1)
        
        report = json.loads(job["report"])
        
        # Print datasource connections
        connections = report.get("datasource_connections", [])
        
        if not connections:
            print("❌ No datasource connections extracted")
        else:
            print(f"✅ Found {len(connections)} datasource connection(s):\n")
            
            for i, conn in enumerate(connections, 1):
                print(f"[{i}] Table: {conn.get('table', 'Unknown')}")
                print(f"    Type: {conn.get('type', 'unknown')}")
                
                if conn.get("type") in ("sqlserver", "sql"):
                    print(f"    Server: {conn.get('server') or '(empty - NEEDS MANUAL INPUT)'}")
                    print(f"    Database: {conn.get('database') or '(empty - NEEDS MANUAL INPUT)'}")
                    print(f"    Schema: {conn.get('schema') or 'dbo'}")
                    print(f"    Source Table: {conn.get('table_name') or '(empty)'}")
                    
                elif conn.get("type") == "postgres":
                    print(f"    Server: {conn.get('server') or '(empty - NEEDS MANUAL INPUT)'}")
                    print(f"    Database: {conn.get('database') or '(empty - NEEDS MANUAL INPUT)'}")
                    print(f"    Schema: {conn.get('schema') or 'public'}")
                    print(f"    Source Table: {conn.get('table_name') or '(empty)'}")
                    
                elif conn.get("type") == "excel":
                    print(f"    File: {conn.get('filename') or '(empty - NEEDS MANUAL INPUT)'}")
                    print(f"    Sheet: {conn.get('table_name') or '(empty)'}")
                    
                elif conn.get("type") == "csv" or conn.get("type") == "textscan":
                    print(f"    File: {conn.get('filename') or '(empty - NEEDS MANUAL INPUT)'}")
                    
                else:
                    print(f"    Unknown type - manual inspection needed")
                    print(f"    Data: {json.dumps(conn, indent=6)}")
                
                print()
        
        # Print stats
        print(f"\nMigration Stats:")
        stats = report.get("stats", {})
        for key, value in stats.items():
            print(f"  {key}: {value}")
        
        # Print warnings
        warnings = report.get("warnings", [])
        if warnings:
            print(f"\n⚠️  Warnings ({len(warnings)}):")
            for w in warnings[:5]:  # Show first 5
                print(f"  - {w}")
            if len(warnings) > 5:
                print(f"  ... and {len(warnings) - 5} more")
        
        print(f"\n{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_connections.py <job_id>")
        print("       python debug_connections.py --help")
        sys.exit(1)
    
    job_id = sys.argv[1]
    
    if job_id == "--help":
        print("""
Debug Connections - Inspect extracted datasource connections

Usage:
    python debug_connections.py <job_id>

Example:
    python debug_connections.py 550e8400-e29b-41d4-a716-446655440000

This script will print:
  - All extracted datasource connections
  - Connection details (server, database, table names)
  - Migration statistics
  - Any warnings

Use this to diagnose why data sources aren't connecting in Power BI.
        """)
        sys.exit(0)
    
    debug_job_connections(job_id)
