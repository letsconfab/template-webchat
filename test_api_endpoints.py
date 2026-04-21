#!/usr/bin/env python3
"""Test script to verify the API endpoints work correctly."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from database import get_db, init_db
from models.invite import Invite, InviteStatus
from models.user import User
from sqlalchemy import select
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from main import app


async def test_api_endpoints():
    """Test the API endpoints."""
    print("🔧 Initializing database...")
    await init_db()
    
    # Get database session
    db_gen = get_db()
    db = await db_gen.__anext__()
    
    try:
        print("\n📧 Creating test invite...")
        
        # Clean up any existing test data
        await db.execute(select(User).where(User.email == "api-test@example.com"))
        await db.execute(select(Invite).where(Invite.email == "api-test@example.com"))
        
        # Create test invite with admin role
        test_invite = Invite(
            email="api-test@example.com",
            token="api-test-token-123",
            role="admin",
            status=InviteStatus.PENDING,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            created_by_id=1
        )
        
        db.add(test_invite)
        await db.commit()
        await db.refresh(test_invite)
        
        print(f"✅ Created invite: {test_invite.email} with role: {test_invite.role}")
        
        # Test API endpoints
        client = TestClient(app)
        
        print("\n🔍 Testing invite check endpoint...")
        response = client.get(f"/api/invite/check?email={test_invite.email}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Invite check successful:")
            print(f"   Found: {data['found']}")
            print(f"   Email: {data['email']}")
            print(f"   Role: {data['role']}")
            print(f"   Message: {data['message']}")
        else:
            print(f"❌ Invite check failed: {response.status_code} - {response.text}")
            
        print("\n👤 Testing registration endpoint...")
        
        # Test registration with the role from invite
        registration_data = {
            "email": "api-test@example.com",
            "password": "testpassword123",
            "role": data['role'] if 'data' in locals() else "admin"
        }
        
        response = client.post("/api/auth/register", json=registration_data)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Registration successful:")
            print(f"   Email: {user_data['email']}")
            print(f"   Role: {user_data['role']}")
            print(f"   Is Admin: {user_data['role'] == 'admin'}")
        else:
            print(f"❌ Registration failed: {response.status_code} - {response.text}")
            
        print("\n🧪 Testing non-invited user registration...")
        
        # Test registration without invite
        non_invited_data = {
            "email": "non-invited-api@example.com",
            "password": "testpassword123",
            "role": "general"
        }
        
        response = client.post("/api/auth/register", json=non_invited_data)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"✅ Non-invited registration successful:")
            print(f"   Email: {user_data['email']}")
            print(f"   Role: {user_data['role']}")
            print(f"   Is Admin: {user_data['role'] == 'admin'}")
        else:
            print(f"❌ Non-invited registration failed: {response.status_code} - {response.text}")
            
        print("\n🎉 API endpoint tests completed!")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_api_endpoints())
