"""Test script for authentication flow."""
import asyncio
import httpx
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

async def test_authentication():
    """Test the complete authentication flow."""
    
    async with httpx.AsyncClient() as client:
        print("=== Testing Authentication Flow ===")
        print(f"Base URL: {BASE_URL}")
        print()
        
        # 1. Test health check
        print("1. Testing health check...")
        try:
            response = await client.get(f"{BASE_URL}/health")
            print(f"   Status: {response.status_code}")
            print(f"   Response: {response.json()}")
        except Exception as e:
            print(f"   Error: {e}")
        print()
        
        # 2. Test admin registration
        print("2. Testing admin registration...")
        admin_data = {
            "email": "admin@test.com",
            "password": "admin123456",
            "confirm_password": "admin123456",
            "full_name": "Test Admin"
        }
        try:
            response = await client.post(
                f"{BASE_URL}/api/auth/admin/register",
                json=admin_data
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                print(f"   Admin created: {response.json()}")
            else:
                print(f"   Error: {response.text}")
        except Exception as e:
            print(f"   Error: {e}")
        print()
        
        # 3. Test login
        print("3. Testing login...")
        login_data = {
            "email": "admin@test.com",
            "password": "admin123456"
        }
        try:
            response = await client.post(
                f"{BASE_URL}/api/auth/login",
                json=login_data
            )
            print(f"   Status: {response.status_code}")
            if response.status_code == 200:
                token_data = response.json()
                print(f"   Login successful!")
                print(f"   Token type: {token_data['token_type']}")
                access_token = token_data['access_token']
                print(f"   Access token: {access_token[:50]}...")
            else:
                print(f"   Error: {response.text}")
                access_token = None
        except Exception as e:
            print(f"   Error: {e}")
            access_token = None
        print()
        
        # 4. Test /api/auth/me with valid token
        if access_token:
            print("4. Testing /api/auth/me with valid token...")
            headers = {"Authorization": f"Bearer {access_token}"}
            try:
                response = await client.get(
                    f"{BASE_URL}/api/auth/me",
                    headers=headers
                )
                print(f"   Status: {response.status_code}")
                if response.status_code == 200:
                    user_data = response.json()
                    print(f"   User data: {json.dumps(user_data, indent=4)}")
                    print(f"   is_admin: {user_data.get('is_admin', 'NOT FOUND')}")
                else:
                    print(f"   Error: {response.text}")
            except Exception as e:
                print(f"   Error: {e}")
            print()
            
            # 5. Test /api/auth/me with invalid token
            print("5. Testing /api/auth/me with invalid token...")
            invalid_headers = {"Authorization": "Bearer invalid_token_here"}
            try:
                response = await client.get(
                    f"{BASE_URL}/api/auth/me",
                    headers=invalid_headers
                )
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
            except Exception as e:
                print(f"   Error: {e}")
            print()
            
            # 6. Test /api/auth/me without token
            print("6. Testing /api/auth/me without token...")
            try:
                response = await client.get(f"{BASE_URL}/api/auth/me")
                print(f"   Status: {response.status_code}")
                print(f"   Response: {response.text}")
            except Exception as e:
                print(f"   Error: {e}")
            print()
        else:
            print("4-6. Skipping /api/auth/me tests (no valid token)")
            print()
        
        print("=== Authentication Flow Test Complete ===")

if __name__ == "__main__":
    asyncio.run(test_authentication())
