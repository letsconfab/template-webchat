# Authentication Implementation

This document describes the robust authentication system implemented for the FastAPI + PostgreSQL project.

## Overview

The authentication system uses:
- **JWT (JSON Web Tokens)** for stateless authentication
- **Async SQLAlchemy 2.0** for database operations
- **bcrypt** for secure password hashing
- **FastAPI Security Dependencies** for reusable auth logic

## Key Features

### 1. Secure JWT Token Handling
- Tokens contain user ID in `sub` field (as string)
- Automatic expiry validation (default: 30 minutes)
- Proper error handling for expired/invalid tokens
- HS256 algorithm with configurable secret key

### 2. Robust User Authentication
- Safe conversion of user ID from string to integer
- Database user validation with async queries
- Inactive user handling
- Comprehensive error responses (401, 403, 400)

### 3. Production-Ready Dependencies
- Reusable authentication dependencies
- Optional authentication support
- Role-based access control (admin/user)
- Proper HTTP exception handling

## API Endpoints

### POST /api/auth/login
```json
{
  "email": "admin@test.com",
  "password": "password123"
}
```

**Response:**
```json
{
  "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
  "token_type": "bearer"
}
```

### GET /api/auth/me
**Headers:** `Authorization: Bearer <token>`

**Response:**
```json
{
  "id": 1,
  "email": "admin@test.com",
  "role": "admin",
  "is_active": true,
  "created_at": "2024-01-01T00:00:00",
  "updated_at": "2024-01-01T00:00:00",
  "is_admin": true
}
```

## Implementation Details

### JWT Token Structure
```json
{
  "sub": "1",           // User ID as string
  "exp": 1640995200    // Expiration timestamp
}
```

### Database Schema
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    email VARCHAR UNIQUE NOT NULL,
    password_hash VARCHAR NOT NULL,
    role VARCHAR DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

### Security Dependencies

#### `get_current_user`
- Validates JWT token
- Converts user ID to integer safely
- Fetches user from database
- Raises 401 for invalid auth

#### `get_current_active_user`
- Extends `get_current_user`
- Verifies user is active
- Raises 400 for inactive users

#### `get_admin_user`
- Extends `get_current_active_user`
- Verifies user has admin role
- Raises 403 for non-admin users

#### `get_optional_current_user`
- Returns user if valid token provided
- Returns None if no token or invalid token
- Useful for optional authentication

## Error Handling

### 401 Unauthorized
- Invalid or missing JWT token
- Expired token
- Malformed token
- User not found in database

### 400 Bad Request
- Inactive user account
- Invalid credentials format

### 403 Forbidden
- Insufficient permissions (non-admin accessing admin endpoints)

## Configuration

### Environment Variables
```bash
# Database
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/webchat_db

# JWT Security
SECRET_KEY=your-super-secret-jwt-key-change-this-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
```

### Security Recommendations
1. **Generate a strong SECRET_KEY:**
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. **Use HTTPS in production**
3. **Set appropriate token expiry**
4. **Implement token refresh mechanism for long sessions**

## Testing

Run the authentication test script:
```bash
cd backend
python test_auth.py
```

This script tests:
- Health check endpoint
- Admin registration
- User login
- Token validation
- Protected endpoint access
- Error scenarios

## Migration Notes

### From Previous Implementation
- Fixed JWT `sub` field parsing (string to int conversion)
- Improved error handling with specific HTTP status codes
- Added `is_admin` computed property to UserResponse schema
- Created reusable authentication dependencies
- Enhanced JWT token validation with explicit expiry checking

### Breaking Changes
- Import paths changed from `middleware.auth` to `dependencies.auth`
- UserResponse schema now includes `is_admin` property
- Better error responses with specific status codes

## Troubleshooting

### Common Issues

#### 500 Internal Server Error on /api/auth/me
**Cause:** User ID type mismatch (string vs int)
**Solution:** Fixed by safe string-to-int conversion in dependencies

#### Token validation failures
**Cause:** Expired tokens or invalid secret key
**Solution:** Check SECRET_KEY and token expiry settings

#### Database connection issues
**Cause:** Incorrect DATABASE_URL or PostgreSQL not running
**Solution:** Verify database connection string and PostgreSQL status

### Debug Mode
Enable debug logging by setting `echo=True` in database.py (development only).

## Best Practices

1. **Always validate tokens on the server side**
2. **Use HTTPS in production**
3. **Implement rate limiting for auth endpoints**
4. **Log authentication attempts for security monitoring**
5. **Use environment variables for sensitive configuration**
6. **Implement password strength requirements**
7. **Consider adding refresh tokens for better UX**

## Frontend Integration

### React/Fetch Example
```javascript
// Login
const loginResponse = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ email, password })
});
const { access_token } = await loginResponse.json();

// Get current user
const userResponse = await fetch('/api/auth/me', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});
const user = await userResponse.json();
console.log(user.is_admin); // true/false
```

This authentication system provides a robust, secure, and production-ready solution for user authentication in FastAPI applications.
