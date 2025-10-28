#!/usr/bin/env python
"""
Simple CLI wrapper for SQL Query Optimizer
Usage: python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42"
"""

import sys
import json
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

# Set up environment
import os
os.environ.setdefault("PYTHONPATH", "src")
os.environ.setdefault("DB_URL", "postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt")

from app.cli import main as cli_main


def print_banner():
    """Print a nice banner."""
    print("""
╔═══════════════════════════════════════════════════════════╗
║       SQL Query Optimization Engine - CLI Tool           ║
║  Analyze and optimize your PostgreSQL queries instantly  ║
╚═══════════════════════════════════════════════════════════╝
    """)


def format_output(data):
    """Format JSON output in a user-friendly way."""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            print(data)
            return

    if isinstance(data, dict):
        # Check if it's an optimize result
        if "suggestions" in data:
            print("\n" + "="*60)
            print("  OPTIMIZATION RESULTS")
            print("="*60 + "\n")

            if data.get("summary"):
                summary = data["summary"]
                print(f"📊 Summary: {summary.get('summary', 'N/A')}")
                print(f"   Score: {(summary.get('score', 0) * 100):.1f}%")
                print(f"   Ranking: {data.get('ranking', 'N/A').upper()}\n")

            suggestions = data.get("suggestions", [])
            if suggestions:
                print(f"Found {len(suggestions)} suggestion(s):\n")
                for i, sug in enumerate(suggestions, 1):
                    print(f"\n{i}. {sug.get('title', 'Untitled')}")
                    print(f"   Type: {sug.get('kind', 'N/A').upper()}")
                    print(f"   Impact: {sug.get('impact', 'N/A').upper()}")
                    print(f"   Confidence: {sug.get('confidence', 0):.1%}")

                    # Show cost metrics if available
                    if sug.get('estCostBefore') and sug.get('estCostAfter'):
                        before = sug['estCostBefore']
                        after = sug['estCostAfter']
                        delta = sug.get('estCostDelta', 0)
                        reduction = (delta / before * 100) if before > 0 else 0

                        print(f"\n   💰 Cost Analysis:")
                        print(f"      Before: {before:.2f}")
                        print(f"      After:  {after:.2f}")
                        print(f"      Saved:  {delta:.2f} ({reduction:.1f}% reduction)")

                    # Show rationale
                    if sug.get('rationale'):
                        print(f"\n   📝 Rationale: {sug['rationale']}")

                    # Show SQL statements
                    if sug.get('statements'):
                        print(f"\n   🔧 Run this SQL:")
                        for stmt in sug['statements']:
                            print(f"      {stmt}")

                    if sug.get('alt_sql'):
                        print(f"\n   💡 Alternative SQL:")
                        print(f"      {sug['alt_sql']}")

                    print("\n   " + "-"*56)
            else:
                print("✅ No optimization suggestions - your query looks good!")

            # Show warnings
            if data.get('plan_warnings'):
                print("\n⚠️  Warnings:")
                for warn in data['plan_warnings']:
                    print(f"   - {warn.get('code', 'N/A')}: {warn.get('detail', 'N/A')}")

        else:
            # Generic JSON output
            print(json.dumps(data, indent=2))
    else:
        print(data)


class InterceptingParser(argparse.ArgumentParser):
    """Parser that intercepts help and other args."""

    def parse_args(self, args=None, namespace=None):
        # If no args, show help
        if not args and len(sys.argv) == 1:
            self.print_help()
            sys.exit(0)
        return super().parse_args(args, namespace)


def main():
    """Main entry point."""

    # Quick command shortcuts
    if len(sys.argv) == 2 and sys.argv[1] in ['--help', '-h', 'help']:
        print_banner()
        print("""
Usage Examples:

  Optimize a query:
    python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42"

  Optimize with what-if analysis:
    python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42" --what-if

  Explain query plan:
    python qeo.py explain "SELECT * FROM orders WHERE user_id > 100"

  Lint SQL:
    python qeo.py lint "SELECT * FROM orders"

  View schema:
    python qeo.py schema

  Interactive mode:
    python qeo.py

Available Commands:
  optimize   - Get optimization suggestions for your query
  explain    - Analyze query execution plan
  lint       - Check SQL for common issues
  schema     - View database schema

Options:
  --what-if  - Enable cost-based HypoPG analysis (optimize only)
  --analyze  - Run actual query execution (explain only)
  --table    - Show results in table format
  --markdown - Show results in markdown format

Examples:
  python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42" --what-if --table
  python qeo.py explain "SELECT COUNT(*) FROM orders" --analyze
  python qeo.py lint "SELECT * FROM users WHERE age > 25"
        """)
        return

    # Interactive mode
    if len(sys.argv) == 1:
        print_banner()
        print("Interactive Mode\n")
        print("Enter your SQL query (or 'quit' to exit):")

        while True:
            try:
                sql = input("\n> ").strip()
                if not sql or sql.lower() in ['quit', 'exit', 'q']:
                    print("Goodbye!")
                    break

                # Run optimize by default in interactive mode
                sys.argv = ['qeo.py', 'optimize', '--sql', sql, '--what-if']
                cli_main()

            except KeyboardInterrupt:
                print("\nGoodbye!")
                break
            except EOFError:
                break
        return

    # Parse command
    if len(sys.argv) >= 2:
        command = sys.argv[1].lower()

        # Handle quick commands
        if command == 'schema':
            print_banner()
            print("Fetching database schema...\n")
            # Call API directly
            import requests
            try:
                resp = requests.get("http://localhost:8000/api/v1/schema")
                data = resp.json()
                if data.get('schema', {}).get('tables'):
                    for table in data['schema']['tables']:
                        print(f"\n📋 Table: {table['name']}")
                        print(f"   Columns:")
                        for col in table['columns']:
                            nullable = "NULL" if col['nullable'] else "NOT NULL"
                            default = f", Default: {col['default']}" if col['default'] else ""
                            print(f"     - {col['name']}: {col['data_type']} ({nullable}{default})")
                        if table.get('primary_key'):
                            print(f"   Primary Key: {', '.join(table['primary_key'])}")
                else:
                    print(json.dumps(data, indent=2))
            except Exception as e:
                print(f"Error: {e}")
                print("Make sure the API is running at http://localhost:8000")
            return

        # For other commands, pass to CLI
        if command in ['optimize', 'explain', 'lint']:
            # If next arg doesn't start with -, treat it as SQL
            if len(sys.argv) >= 3 and not sys.argv[2].startswith('-'):
                sql = sys.argv[2]
                # Rebuild args for CLI
                new_args = [sys.argv[0], command, '--sql', sql] + sys.argv[3:]
                sys.argv = new_args

    # Call the main CLI
    print_banner()
    cli_main()


if __name__ == "__main__":
    main()
