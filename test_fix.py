#!/usr/bin/env python3
"""Test the fix for role assignment bug."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from database import get_db, init_db
from models.invite import Invite, InviteStatus
from models.user import User
from schemas.user import AdminCreate
from sqlalchemy import select
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from main import app


async def test_admin_register_fix():
    """Test that admin registration now respects invite roles."""
    print("Testing admin registration fix...")
    
    # Initialize database
    await init_db()
    db_gen = get_db()
    db = await db_gen.__anext__()
    
    try:
        # Clean up test data
        await db.execute(select(User).where(User.email == "harshdhiman.2026@gmail.com"))
        
        print("\n1. Testing admin registration with invite role='general'...")
        
        # Create test invite with general role (same as your data)
        test_invite = Invite(
            email="harshdhiman.2026@gmail.com",
            token="test-fix-token",
            role="general",
            status=InviteStatus.PENDING,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            created_by_id=1
        )
        
        db.add(test_invite)
        await db.commit()
        
        print(f"   Created invite: {test_invite.email} with role: {test_invite.role}")
        
        # Test admin registration (this should now respect invite role)
        client = TestClient(app)
        
        admin_data = {
            "email": "harshdhiman.2026@gmail.com",
            "password": "password123",
            "confirm_password": "password123"
        }
        
        response = client.post("/api/auth/admin/register", json=admin_data)
        
        if response.status_code == 200:
            user_data = response.json()
            print(f"   Registration successful!")
            print(f"   Email: {user_data['email']}")
            print(f"   Role: {user_data['role']}")
            
            if user_data['role'] == 'general':
                print("   SUCCESS: User got correct role 'general' from invite!")
            else:
                print(f"   FAILED: User got role '{user_data['role']}', expected 'general'")
                
        else:
            print(f"   Registration failed: {response.status_code} - {response.text}")
            
        print("\n2. Verifying invite status...")
        
        # Check invite was marked as accepted
        result = await db.execute(
            select(Invite).where(Invite.email == "harshdhiman.2026@gmail.com")
        )
        updated_invite = result.scalar_one_or_none()
        
        if updated_invite:
            print(f"   Invite status: {updated_invite.status}")
            if updated_invite.status == InviteStatus.ACCEPTED:
                print("   SUCCESS: Invite marked as accepted!")
            else:
                print(f"   FAILED: Invite status is '{updated_invite.status}', expected 'accepted'")
        
        print("\n3. Testing admin registration with invite role='admin'...")
        
        # Test with admin role invite
        admin_invite = Invite(
            email="admin-test@example.com",
            token="admin-test-token",
            role="admin",
            status=InviteStatus.PENDING,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            created_by_id=1
        )
        
        db.add(admin_invite)
        await db.commit()
        
        admin_data2 = {
            "email": "admin-test@example.com",
            "password": "password123",
            "confirm_password": "password123"
        }
        
        response2 = client.post("/api/auth/admin/register", json=admin_data2)
        
        if response2.status_code == 200:
            user_data2 = response2.json()
            print(f"   Registration successful!")
            print(f"   Email: {user_data2['email']}")
            print(f"   Role: {user_data2['role']}")
            
            if user_data2['role'] == 'admin':
                print("   SUCCESS: User got correct role 'admin' from invite!")
            else:
                print(f"   FAILED: User got role '{user_data2['role']}', expected 'admin'")
        
        print("\n4. Testing admin registration without invite...")
        
        # Test without any invite
        no_invite_data = {
            "email": "noinvite@example.com",
            "password": "password123",
            "confirm_password": "password123"
        }
        
        response3 = client.post("/api/auth/admin/register", json=no_invite_data)
        
        if response3.status_code == 200:
            user_data3 = response3.json()
            print(f"   Registration successful!")
            print(f"   Email: {user_data3['email']}")
            print(f"   Role: {user_data3['role']}")
            
            if user_data3['role'] == 'general':
                print("   SUCCESS: User got default role 'general' when no invite!")
            else:
                print(f"   FAILED: User got role '{user_data3['role']}', expected 'general'")
        
        print("\n" + "="*50)
        print("FIX VERIFICATION COMPLETE!")
        print("="*50)
        
    except Exception as e:
        print(f"Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_admin_register_fix())
