#!/usr/bin/env python3
"""Reset database by dropping and recreating tables."""

import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from backend.database import engine, Base, close_db

async def main():
    """Drop and recreate all database tables."""
    try:
        print("Dropping all tables...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        
        print("Creating tables with new schema...")
        async with engine.begin() as conn:
            # Import all models here to ensure they are registered
            from backend.models.user import User
            from backend.models.invite import Invite
            from backend.models.settings import SystemSettings
            
            await conn.run_sync(Base.metadata.create_all)
        
        print("Database reset successfully!")
    except Exception as e:
        print(f"Error resetting database: {e}")
        sys.exit(1)
    finally:
        await close_db()

if __name__ == "__main__":
    asyncio.run(main())
