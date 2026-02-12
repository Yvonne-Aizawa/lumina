#!/usr/bin/env python3
"""Thin launcher — import the app and run uvicorn."""

import uvicorn

from app.server import app

if __name__ == "__main__":
    print("Starting server at http://localhost:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
