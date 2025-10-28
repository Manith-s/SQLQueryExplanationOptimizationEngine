# Quick Start Guide

Get started with the SQL Query Optimization Engine in less than 5 minutes.

## Prerequisites

Before you begin, ensure you have:

1. **Docker Desktop** installed and running
   - Download from: https://www.docker.com/products/docker-desktop
   - Start Docker Desktop and wait for it to be ready

2. **Python 3.11 or later**
   - Check version: `python --version`
   - Download from: https://www.python.org/downloads/

## Step 1: Install Dependencies

```bash
# Navigate to project folder
cd queryexpnopt

# Install Python dependencies
pip install -r requirements.txt
```

This will install FastAPI, PostgreSQL drivers, and all required packages.

## Step 2: Start the System

### Windows
```bash
scripts\start.bat
```

### Linux/Mac
```bash
./scripts/start.sh
```

**What happens**:
- PostgreSQL database starts (with HypoPG extension)
- Sample data loads (orders and users tables)
- Web server starts on port 9000
- You'll see: "SYSTEM READY! Open your browser to http://localhost:9000"

## Step 3: Open the Web Interface

Open your browser and go to:
```
http://localhost:9000
```

You should see a **purple web interface** with:
- SQL query input box
- Example queries (clickable)
- Three action buttons (Optimize, Explain, View Schema)

## Step 4: Try Your First Optimization

### Option A: Click an Example (Easiest)

1. Click the first example query: "Basic Query with ORDER BY"
2. The query auto-fills in the text box
3. Click the **"Optimize Query"** button (purple)
4. Wait 2-3 seconds
5. See the results!

### Option B: Enter Your Own Query

1. Type or paste this SQL in the text box:
   ```sql
   SELECT * FROM orders
   WHERE user_id = 42
   ORDER BY created_at DESC
   LIMIT 100
   ```

2. Make sure both checkboxes are checked:
   - ☑ Run EXPLAIN ANALYZE
   - ☑ Enable What-If Analysis

3. Click **"Optimize Query"**

## Step 5: Understand the Results

You'll see results like this:

### Summary Section (Purple Box)
```
Top suggestion: Index on orders(user_id, created_at)
Optimization Score: 48%
Ranking Method: cost_based
```

### Suggestions List

**1. Index Suggestion** (HIGH impact)
```
Cost Before:  1910.68
Cost After:   104.59
Reduction:    94.5%  ← Your query becomes 94.5% faster!
```

**SQL to run**:
```sql
CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
ON orders (user_id, created_at);
```

Click the **Copy** button to copy the SQL statement.

**2. Rewrite Suggestions** (MEDIUM/LOW impact)
- Align ORDER BY with index
- Replace SELECT * with specific columns

## Step 6: (Optional) Apply the Index

To actually apply the suggested index:

```bash
# Connect to the database
docker exec -it queryexpnopt-db psql -U postgres -d queryexpnopt

# Run the suggested SQL
CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
ON orders (user_id, created_at);

# Exit
\q
```

Or use this one-liner:
```bash
docker exec queryexpnopt-db psql -U postgres -d queryexpnopt -c "CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at ON orders (user_id, created_at);"
```

## Step 7: Verify Improvement

After creating the index:

1. Go back to the web interface
2. Enter the same query again
3. Click "Optimize Query"
4. The cost should now be much lower (~104 instead of ~1910)

## What's Next?

### Try Other Features

**Explain Query Plan**:
1. Enter a query
2. Click **"Explain Plan"** button (gray)
3. See detailed execution plan with warnings

**View Database Schema**:
1. Click **"View Schema"** button (green)
2. See all tables, columns, and indexes

**Test Multiple Queries**:
- Try the other example queries
- Enter your own production queries
- Compare different query patterns

### Learn More

- **API Documentation**: http://localhost:9000/docs
- **Architecture Guide**: See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- **Tutorials**: See [docs/TUTORIAL.md](docs/TUTORIAL.md)

### Use Command Line

```bash
# Activate environment
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate.bat # Windows

# Set environment
export PYTHONPATH=src  # Linux/Mac
set PYTHONPATH=src     # Windows

export DB_URL="postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt"  # Linux/Mac
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt      # Windows

# Run CLI
python -c "from app.cli import main; main()" optimize --sql "SELECT * FROM orders WHERE user_id = 42" --what-if --table
```

## Stopping the System

Press **Ctrl+C** in the terminal where the server is running.

Or run:
```bash
docker compose down
```

## Troubleshooting

### "Docker is not running"
- Start Docker Desktop
- Wait for the whale icon to stop animating
- Try again

### "Port 9000 already in use"
- Stop other applications using port 9000
- Or start on a different port: `scripts/start.bat 8080`

### "Module not found"
- Make sure you ran: `pip install -r requirements.txt`
- Activate virtual environment if you have one

### "Database connection error"
- Check if database is running: `docker compose ps`
- Restart database: `docker compose restart db`

### Web UI shows JSON instead of purple interface
- Hard refresh browser: Ctrl+F5
- Clear browser cache
- Try incognito/private window

## Key Concepts

**What-If Analysis**: Tests hypothetical indexes without creating them (using HypoPG)

**Cost-Based Ranking**: Uses real PostgreSQL cost estimates, not guesses

**EXPLAIN ANALYZE**: Runs the actual query to get precise metrics

**Concurrent Index Creation**: Safe for production (won't lock table)

## Tips for Best Results

1. **Enable "What-If Analysis"** for accurate cost estimates
2. **Use real production queries** for relevant suggestions
3. **Test in development first** before applying to production
4. **Focus on high-impact suggestions** (90%+ reduction)
5. **Monitor after applying** to verify improvements

---

**You're all set!** Start optimizing your queries! 🚀

**Need help?** See the full documentation in the [docs/](docs/) folder.
