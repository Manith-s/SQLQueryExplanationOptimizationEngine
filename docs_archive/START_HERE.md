# 🚀 START HERE - SQL Query Optimizer

## For End Users - 2 Simple Options

---

## ✨ OPTION 1: Web Interface (Recommended)

### Step 1: Start the System

**On Windows:**
```bash
start.bat
```

**On Linux/Mac:**
```bash
./start.sh
```

### Step 2: Open Browser

Go to: **http://localhost:8000**

### Step 3: Use It!

1. Paste your SQL query in the text box
2. Click "Optimize Query" button
3. See instant recommendations with cost savings
4. Copy the suggested SQL and apply to your database

**That's it!** The web interface shows you everything visually with colors, metrics, and easy copy buttons.

---

## 💻 OPTION 2: Command Line

### Quick Commands:

**Optimize any query:**
```bash
python qeo.py optimize "SELECT * FROM orders WHERE user_id = 42" --what-if
```

**View your database tables:**
```bash
python qeo.py schema
```

**Interactive mode (type queries one by one):**
```bash
python qeo.py
```

---

## 📖 What You'll Get

### Example Output:

```
Found 1 suggestion(s):

1. Index on orders(user_id, created_at)
   Type: INDEX
   Impact: HIGH
   Confidence: 70.0%

   💰 Cost Analysis:
      Before: 1910.68
      After:  104.59
      Saved:  1806.09 (94.5% reduction)

   🔧 Run this SQL:
      CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
      ON orders (user_id, created_at);
```

**Translation:** Creating this index makes your query **94.5% faster!** 🎉

---

## 🎯 Try These Examples

Once the web interface is open (http://localhost:8000), click on any example or type:

1. **Slow query needing an index:**
   ```sql
   SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100
   ```

2. **Query with SELECT *:**
   ```sql
   SELECT * FROM orders WHERE user_id IN (1,2,3,4,5)
   ```

3. **Aggregate query:**
   ```sql
   SELECT COUNT(*) FROM orders WHERE created_at > '2024-01-01'
   ```

---

## 🛑 Stop the System

Press `Ctrl+C` in the terminal, or run:
```bash
docker compose down
```

---

## ❓ Need Help?

- **Full guide:** See `USER_GUIDE.md`
- **API docs:** http://localhost:8000/docs (when running)
- **Health check:** http://localhost:8000/health

---

## ⚡ That's All You Need!

1. Run `start.bat` or `./start.sh`
2. Open http://localhost:8000
3. Paste SQL and click "Optimize"
4. Get instant recommendations

**Enjoy optimizing! 🚀**
