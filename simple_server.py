#!/usr/bin/env python
"""
Simple standalone web server for SQL Query Optimizer
Just run: python simple_server.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import os
os.environ.setdefault("DB_URL", "postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt")

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# Import the existing routers
from app.routers import health, lint, explain, optimize, schema, workload
from app.core.auth import verify_token
from fastapi import Depends

# Create app
app = FastAPI(title="SQL Query Optimizer")

# Include all API routers
app.include_router(health.router, tags=["health"])
app.include_router(lint.router, prefix="/api/v1", tags=["lint"], dependencies=[Depends(verify_token)])
app.include_router(explain.router, prefix="/api/v1", tags=["explain"], dependencies=[Depends(verify_token)])
app.include_router(optimize.router, prefix="/api/v1", tags=["optimize"], dependencies=[Depends(verify_token)])
app.include_router(schema.router, prefix="/api/v1", tags=["schema"], dependencies=[Depends(verify_token)])
app.include_router(workload.router, prefix="/api/v1", tags=["workload"], dependencies=[Depends(verify_token)])

# Serve web UI
@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the web interface."""
    static_dir = Path(__file__).parent / "src" / "app" / "static"
    index_file = static_dir / "index.html"

    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            return f.read()
    else:
        return """
        <html>
            <body>
                <h1>SQL Query Optimizer API</h1>
                <p>Web UI not found. Go to <a href="/docs">/docs</a> for API documentation.</p>
            </body>
        </html>
        """

if __name__ == "__main__":
    # Check for port argument
    import sys
    port = 8000
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except:
            port = 8000

    print(f"""
╔═══════════════════════════════════════════════════════════╗
║       SQL Query Optimization Engine - Web Server         ║
╚═══════════════════════════════════════════════════════════╝

Starting server...

  Web UI:   http://localhost:{port}
  API Docs: http://localhost:{port}/docs
  Health:   http://localhost:{port}/health

Press Ctrl+C to stop
    """)

    uvicorn.run(app, host="0.0.0.0", port=port)
