# 👋 START HERE

Welcome to the SQL Query Optimization Engine!

## ⚡ Super Quick Start (30 seconds)

```bash
# Step 1: Start the system
scripts\start.bat         # Windows
./scripts/start.sh        # Linux/Mac

# Step 2: Open browser
# → http://localhost:9000

# Step 3: Click example query → Click "Optimize" → Done!
```

That's it! You should see a purple web interface with optimization results showing "94.5% faster!"

---

## 📚 What to Read Next

### For End Users (Just want to use it)

1. **README.md** - Overview of what this does
2. **QUICKSTART.md** - Detailed getting started guide (5 minutes)
3. **docs/TUTORIAL.md** - Step-by-step tutorials

### For Developers (Want to understand/modify code)

1. **PROJECT_STRUCTURE.md** - How the code is organized
2. **docs/SYSTEM_DESIGN.md** - Architecture and design decisions
3. **docs/API.md** - API endpoint documentation

### For Contributors (Want to add features)

1. **CONTRIBUTING.md** - Contribution guidelines
2. **CODE_OF_CONDUCT.md** - Community standards
3. **PROJECT_STRUCTURE.md** - Where to add new code

---

## 🎯 Common Tasks

### Start the System
```bash
scripts\start.bat      # Windows
./scripts/start.sh     # Linux/Mac
```

### Stop the System
Press `Ctrl+C` in the terminal

### Run Tests
```bash
pytest
```

### View Documentation
```bash
# All docs are in the docs/ folder
ls docs/
```

### Get Help
```bash
# Verify system is set up correctly
python scripts/verify.py
```

---

## 🗺️ Project Map

```
Root Level:
  README.md           ← Overview (start here for info)
  QUICKSTART.md       ← Getting started (start here to run)
  PROJECT_STRUCTURE.md ← Code organization

Scripts:
  scripts/start.bat   ← Start system (Windows)
  scripts/start.sh    ← Start system (Linux/Mac)
  scripts/verify.py   ← Check setup

Documentation:
  docs/SYSTEM_DESIGN.md  ← How it works
  docs/API.md            ← API reference
  docs/TUTORIAL.md       ← Tutorials

Source Code:
  src/app/core/optimizer.py  ← Main optimization logic
  src/app/routers/           ← API endpoints
  src/app/static/index.html  ← Web interface

Tests:
  tests/test_optimizer_rules.py  ← Optimizer tests
  tests/test_*.py                ← Other tests
```

---

## 💡 Key Concepts

**What does this tool do?**
Analyzes your SQL queries and tells you how to make them faster (e.g., "94.5% faster!")

**How does it work?**
- Parses your SQL without running it
- Tests hypothetical indexes using HypoPG
- Shows real cost estimates from PostgreSQL
- Gives you exact SQL statements to run

**Is it safe?**
Yes! It only analyzes - never modifies your database.

---

## 🚀 Your First Query Optimization

1. Start system: `scripts/start.bat`
2. Open: http://localhost:9000
3. Click: "Basic Query with ORDER BY"
4. Click: "Optimize Query" button
5. See: Cost reduction of 94.5%!
6. Copy: The suggested SQL statement
7. Apply: (optional) Run the CREATE INDEX command

**Result**: Your query is now 94.5% faster! 🎉

---

## ❓ Need Help?

**System won't start?**
→ Check Docker Desktop is running
→ Run `scripts/verify.py` to diagnose

**Can't find something?**
→ See `PROJECT_STRUCTURE.md`

**Want to understand the code?**
→ See `docs/SYSTEM_DESIGN.md`

**Found a bug?**
→ Check `docs/ERRORS_AND_MESSAGES.md`

---

## 📋 Checklist for Success

- [ ] Docker Desktop installed and running
- [ ] Python 3.11+ installed
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] System started (`scripts/start.bat`)
- [ ] Browser open to http://localhost:9000
- [ ] Seeing purple web interface
- [ ] Successfully optimized a query

**All checked?** You're all set! 🎉

---

## 🎓 Learning Path

### Beginner
1. Run the quick start above
2. Try all example queries
3. Read QUICKSTART.md

### Intermediate
1. Understand the results (what do costs mean?)
2. Apply an index suggestion
3. Test your own queries

### Advanced
1. Read SYSTEM_DESIGN.md
2. Understand how HypoPG works
3. Contribute improvements

---

## ⭐ Pro Tips

1. **Enable "What-If Analysis"** for accurate cost estimates
2. **Focus on HIGH impact** suggestions (90%+ reduction)
3. **Test in development** before applying to production
4. **Use EXPLAIN ANALYZE** for real execution metrics
5. **Apply indexes concurrently** (won't lock table)

---

## 🔗 Quick Links

- **Web UI**: http://localhost:9000
- **API Docs**: http://localhost:9000/docs
- **Health Check**: http://localhost:9000/health
- **Project Docs**: [docs/](docs/)

---

**Ready?** Run `scripts/start.bat` and start optimizing! 🚀

---

*This project follows clean code principles and professional software development practices. See CLEANUP_SUMMARY.md for details on the organization.*
