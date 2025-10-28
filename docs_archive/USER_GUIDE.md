# SQL Query Optimizer - User Guide

A simple, powerful tool to optimize your PostgreSQL queries with AI-powered recommendations.

## 🚀 Quick Start (3 Steps)

### Step 1: Start the System

**Windows:**
```bash
start.bat
```

**Linux/Mac:**
```bash
./start.sh
```

The system will:
- Start PostgreSQL database (port 5433)
- Start API server (port 8000)
- Open web interface at http://localhost:8000

### Step 2: Open Your Browser

Go to: **http://localhost:8000**

You'll see a beautiful web interface where you can:
- Enter your SQL queries
- Get instant optimization suggestions
- See cost reductions (e.g., "94.5% faster!")
- Copy SQL statements to apply improvements

### Step 3: Optimize Your Queries!

**Try these example queries:**

1. **Basic Query:**
   ```sql
   SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100
   ```
   Result: Get index suggestions that make it 90%+ faster!

2. **Aggregate Query:**
   ```sql
   SELECT COUNT(*) FROM orders WHERE created_at > '2024-01-01'
   ```
   Result: Learn if an index would help!

3. **Complex Query:**
   ```sql
   SELECT id, user_id FROM orders WHERE user_id IN (1,2,3,4,5)
   ```
   Result: Get rewrite suggestions!

---

## 🌐 Using the Web Interface

### Features:
- ✅ **Simple text box** - Just paste your SQL
- ✅ **One-click optimize** - Get instant suggestions
- ✅ **Cost analysis** - See before/after performance metrics
- ✅ **Copy buttons** - Easy to apply recommendations
- ✅ **Example queries** - Click to try pre-made examples

### Options:
- **Run EXPLAIN ANALYZE** - Executes query to get real metrics (checked by default)
- **Enable What-If Analysis** - Tests hypothetical indexes with HypoPG (checked by default)
- **Top K Suggestions** - How many suggestions to show (default: 5)

### Buttons:
- **Optimize Query** - Get optimization suggestions (recommended!)
- **Explain Plan** - See query execution plan details
- **View Schema** - See your database tables and columns

---

## 💻 Using Command Line (Alternative)

### Simple Commands:

**Optimize a query:**
```bash
python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42"
```

**With what-if analysis (recommended):**
```bash
python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42" --what-if
```

**Explain query plan:**
```bash
python qeo.py explain "SELECT * FROM orders WHERE user_id > 100"
```

**Check SQL syntax:**
```bash
python qeo.py lint "SELECT * FROM orders"
```

**View database schema:**
```bash
python qeo.py schema
```

### Interactive Mode:
```bash
python qeo.py
```
Then just type queries and press Enter!

---

## 📊 Understanding Results

### What You'll See:

**1. Summary:**
```
Summary: Top suggestion: Index on orders(user_id, created_at)
Optimization Score: 48%
Ranking Method: cost_based
```

**2. Suggestions:**
Each suggestion shows:
- **Title**: What to do (e.g., "Create index on orders(user_id)")
- **Type**: Index or Rewrite
- **Impact**: High, Medium, or Low
- **Cost Reduction**: "94.5% faster" means huge improvement!

**3. Cost Analysis:**
```
Cost Before:  1,910.68
Cost After:   104.59
Saved:        1,806.09 (94.5% reduction)
```
Lower numbers = faster queries. Higher % reduction = bigger win!

**4. SQL to Run:**
```sql
CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
ON orders (user_id, created_at);
```
Just copy and run this in your database!

---

## 🔧 Applying Recommendations

### Option 1: Via Command Line
```bash
docker exec -it queryexpnopt-db psql -U postgres -d queryexpnopt -c "CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at ON orders (user_id, created_at);"
```

### Option 2: Via Database Client
1. Connect to: `localhost:5433`
2. Database: `queryexpnopt`
3. User: `postgres`
4. Password: `password`
5. Run the suggested SQL

### Why CONCURRENTLY?
- Won't lock your table
- Safe to run in production
- Takes longer but doesn't block queries

---

## ❓ Common Questions

### "What does 94.5% reduction mean?"
Your query will use 94.5% less database resources (much faster!).

### "Should I create all suggested indexes?"
Start with the highest cost reduction. Too many indexes can slow down writes.

### "Is this safe for production?"
The tool only analyzes - it never modifies your database. You decide what to apply.

### "What if I don't have a 'orders' table?"
The examples use sample data. Use your own table names in the web interface!

---

## 🛑 Stopping the System

**Option 1: Stop API only**
Press `Ctrl+C` in the terminal where you ran `start.bat` or `start.sh`

**Option 2: Stop everything**
```bash
docker compose down
```

---

## 💡 Tips for Best Results

1. **Use "What-If Analysis"** - It tests indexes before you create them!
2. **Start with high-impact suggestions** - Focus on "HIGH" impact first
3. **Test in development first** - Try suggestions on test data
4. **Monitor your database** - See if queries actually get faster
5. **Don't over-index** - More indexes = slower writes

---

## 🎯 Typical Workflow

1. **Paste your slow query** into the web interface
2. **Click "Optimize Query"** with both checkboxes enabled
3. **Review suggestions** - look for high cost reductions
4. **Copy the SQL statement** from top suggestion
5. **Test in development** database first
6. **Apply to production** if results are good
7. **Re-run optimizer** to verify improvement

---

## 🆘 Troubleshooting

### "Cannot connect to database"
```bash
# Check if database is running
docker compose ps

# Start database
docker compose up -d db
```

### "Web interface not loading"
```bash
# Check if API is running
curl http://localhost:8000/health

# Should return: {"status":"ok"}
```

### "No suggestions generated"
- Table might be too small (< 10,000 rows)
- Query might already be optimal
- Try enabling "What-If Analysis"

### "Port 8000 already in use"
```bash
# Kill existing process or use different port
python -m uvicorn app.main:app --reload --app-dir src --port 8001
```

---

## 📚 Next Steps

- Try analyzing your real production queries
- Compare performance before/after applying suggestions
- Use workload analysis for multiple queries at once
- Check out `/docs` for full API documentation

---

## 🎉 You're Ready!

Just run `start.bat` (Windows) or `./start.sh` (Linux/Mac) and open http://localhost:8000 in your browser!

Happy optimizing! 🚀
