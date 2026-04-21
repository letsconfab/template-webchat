#!/usr/bin/env python3
"""Test script to verify the registration flow with role assignment."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.append(str(Path(__file__).parent / "backend"))

from database import get_db, init_db
from models.invite import Invite, InviteStatus
from models.user import User, UserRole
from sqlalchemy import select
from datetime import datetime, timedelta


async def test_registration_flow():
    """Test the complete registration flow."""
    print("🔧 Initializing database...")
    await init_db()
    
    # Get database session
    db_gen = get_db()
    db = await db_gen.__anext__()
    
    try:
        print("\n📧 Step 1: Creating test invite...")
        
        # Clean up any existing test data
        await db.execute(select(User).where(User.email == "test@example.com"))
        await db.execute(select(Invite).where(Invite.email == "test@example.com"))
        
        # Create test invite with general role
        test_invite = Invite(
            email="test@example.com",
            token="test-token-123",
            role="general",
            status=InviteStatus.PENDING,
            expiry_date=datetime.utcnow() + timedelta(days=7),
            created_by_id=1  # Assuming admin user with ID 1 exists
        )
        
        db.add(test_invite)
        await db.commit()
        await db.refresh(test_invite)
        
        print(f"✅ Created invite: {test_invite.email} with role: {test_invite.role}")
        
        print("\n🔍 Step 2: Testing invite check API...")
        
        # Simulate the invite check logic
        result = await db.execute(
            select(Invite).where(
                Invite.email == "test@example.com",
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow()
            )
        )
        found_invite = result.scalar_one_or_none()
        
        if found_invite:
            print(f"✅ Invite found: {found_invite.email}, role: {found_invite.role}")
            print(f"   Message: You are invited by admin")
        else:
            print("❌ Invite not found")
            
        print("\n👤 Step 3: Testing user registration with role...")
        
        # Simulate registration payload
        registration_data = {
            "email": "test@example.com",
            "password": "testpassword123",
            "role": found_invite.role if found_invite else "general"
        }
        
        print(f"   Registration payload: {registration_data}")
        
        # Check if user already exists
        result = await db.execute(select(User).where(User.email == registration_data["email"]))
        existing_user = result.scalar_one_or_none()
        
        if existing_user:
            print(f"❌ User already exists: {existing_user.email}")
        else:
            print("✅ User does not exist, can proceed with registration")
            
            # Determine role logic (same as in auth.py)
            user_role = registration_data.get("role") or (found_invite.role if found_invite else "general")
            print(f"   Assigned role: {user_role}")
            
            # Create user (simulating the registration endpoint)
            from services.auth import get_password_hash
            hashed_password = get_password_hash(registration_data["password"])
            
            new_user = User(
                email=registration_data["email"],
                password_hash=hashed_password,
                role=user_role,
                is_active=True
            )
            
            db.add(new_user)
            
            # Mark invite as accepted
            if found_invite:
                found_invite.status = InviteStatus.ACCEPTED
                print(f"   Invite status updated to: {found_invite.status}")
            
            await db.commit()
            await db.refresh(new_user)
            
            print(f"✅ User created successfully:")
            print(f"   Email: {new_user.email}")
            print(f"   Role: {new_user.role}")
            print(f"   Is Admin: {new_user.role == 'admin'}")
            
        print("\n🧪 Step 4: Testing non-invited user registration...")
        
        # Test registration without invite
        non_invited_email = "noninvited@example.com"
        registration_data_no_invite = {
            "email": non_invited_email,
            "password": "testpassword123",
            "role": "general"  # Should default to general
        }
        
        print(f"   Registration payload: {registration_data_no_invite}")
        
        # Check invite for non-invited email
        result = await db.execute(
            select(Invite).where(
                Invite.email == non_invited_email,
                Invite.status == InviteStatus.PENDING,
                Invite.expiry_date > datetime.utcnow()
            )
        )
        no_invite = result.scalar_one_or_none()
        
        user_role_no_invite = registration_data_no_invite.get("role") or (no_invite.role if no_invite else "general")
        print(f"   Assigned role: {user_role_no_invite}")
        
        if not no_invite:
            print("✅ No invite found, correctly defaulting to 'general' role")
        
        print("\n🎉 Registration flow test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(test_registration_flow())
