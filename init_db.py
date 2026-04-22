#!/usr/bin/env python3
"""Initialize database with proper schema."""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.database import init_db, close_db

async def main():
    """Initialize database tables."""
    try:
        print("Initializing database...")
        await init_db()
        print("Database initialized successfully!")
    except Exception as e:
        print(f"Error initializing database: {e}")
        sys.exit(1)
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
