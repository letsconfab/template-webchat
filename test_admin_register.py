import requests
import json

url = "http://localhost:8000/api/auth/admin/register"
data = {
    "email": "test@example.com",
    "password": "testpassword123",
    "confirm_password": "testpassword123"
}

try:
    response = requests.post(url, json=data)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text}")
except Exception as e:
    print(f"Error: {e}")
