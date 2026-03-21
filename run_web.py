#!/usr/bin/env python3
"""
Run the Subtext private web service.

The service binds to localhost only and is meant to be reached through
Tailscale Serve or another loopback-safe private proxy.
"""
import sys
import os
from pathlib import Path

# Run from project root so src.* imports work
project_root = Path(__file__).resolve().parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("SUBTEXT_SERVER_HOST", "127.0.0.1")
    port = int(os.getenv("SUBTEXT_SERVER_PORT", "8000"))

    uvicorn.run(
        "src.web.server:app",
        host=host,
        port=port,
        reload=False,
    )
