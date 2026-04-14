# Admin Invitation Email Workflow - Step by Step Guide

## परिचय (Introduction)
यह document Confab Chat application में admin invitation email system के complete workflow को step by step explain करता है।

---

## 📁 Files और उनका Purpose

### 1. Environment Configuration
**File:** `.env.example` (Lines 31-36)
- **Purpose:** Email service के लिए configuration settings
- **Key Lines:**
  - `SMTP_SERVER=smtp.gmail.com` - Email server address
  - `SMTP_PORT=587` - Email server port
  - `SMTP_USERNAME=harshdhiman.2026@gmail.com` - Sender email
  - `SMTP_PASSWORD=vnzowfhkpjftsbko` - Email password/app password
  - `FROM_EMAIL=harshdhiman.2026@gmail.com` - From email address

---

### 2. Main Application Entry Point
**File:** `backend/main.py` (Lines 19, 91-93)
- **Purpose:** FastAPI application का main file जो invite router को include करता है
- **Key Lines:**
  - Line 19: `from .routers import auth, users, invites` - Invite router import
  - Line 93: `app.include_router(invites.router)` - Invite router को register करना

---

### 3. Invite Router - Main Logic
**File:** `backend/routers/invites.py`

#### 3.1 Import Statements (Lines 1-18)
- **Purpose:** Required dependencies और services import करना
- **Key Lines:**
  - Line 16: `from ..services.email import email_service` - Email service import

#### 3.2 Create Invite Endpoint (Lines 21-88)
**Endpoint:** `POST /api/admin/invite-user`
- **Purpose:** Admin द्वारा नए user को invite भेजना
- **Step by Step Process:**

1. **Line 28-36:** Check if user already exists
   ```python
   result = await db.execute(select(User).where(User.email == invite_data.email))
   existing_user = result.scalar_one_or_none()
   ```

2. **Line 38-54:** Check for existing pending invite
   ```python
   result = await db.execute(
       select(Invite).where(
           and_(
               Invite.email == invite_data.email,
               Invite.status == InviteStatus.PENDING,
               Invite.expiry_date > datetime.utcnow()
           )
       )
   )
   ```

3. **Line 57:** Generate secure token
   ```python
   token = generate_secure_token()
   ```

4. **Line 60-70:** Create invite in database
   ```python
   db_invite = Invite(
       email=invite_data.email,
       token=token,
       status=InviteStatus.PENDING,
       expiry_date=datetime.utcnow() + timedelta(days=7),
       created_by_id=current_user.id
   )
   ```

5. **Line 72-77:** Send invitation email
   ```python
   email_sent = await email_service.send_invite_email(
       to_email=invite_data.email,
       invite_token=token,
       inviter_name=current_user.email
   )
   ```

#### 3.3 Accept Invite Endpoint (Lines 151-236)
**Endpoint:** `POST /api/accept-invite/{token}`
- **Purpose:** User द्वारा invite accept करके account create करना
- **Key Steps:**
  - Line 159-182: Validate invite token
  - Line 204-213: Create new user account
  - Line 224-227: Send welcome email

---

### 4. Email Service
**File:** `backend/services/email.py`

#### 4.1 Email Configuration (Lines 12-22)
- **Purpose:** SMTP connection settings
- **Key Lines:**
  ```python
  email_config = ConnectionConfig(
      MAIL_USERNAME=config.SMTP_USERNAME,
      MAIL_PASSWORD=config.SMTP_PASSWORD,
      MAIL_FROM=config.FROM_EMAIL,
      MAIL_PORT=config.SMTP_PORT,
      MAIL_SERVER=config.SMTP_SERVER,
      MAIL_STARTTLS=True,
      MAIL_SSL_TLS=False,
      USE_CREDENTIALS=True,
      VALIDATE_CERTS=True,
  )
  ```

#### 4.2 Send Invite Email Method (Lines 31-134)
**Method:** `send_invite_email()`
- **Purpose:** Invitation email भेजना
- **Key Steps:**

1. **Line 40:** Create invite link
   ```python
   invite_link = f"http://localhost:8000/accept-invite/{invite_token}"
   ```

2. **Line 43:** Email subject
   ```python
   subject = "You're invited to join Confab Chat"
   ```

3. **Line 46-112:** HTML email template
   - Professional email design
   - Accept invitation button
   - Invite link included

4. **Line 115-120:** Create message schema
   ```python
   message = MessageSchema(
       subject=subject,
       recipients=[to_email],
       body=html_content,
       subtype=MessageType.html,
   )
   ```

5. **Line 123-125:** Send email
   ```python
   from fastapi_mail import FastMail
   fm = FastMail(self.config)
   await fm.send_message(message)
   ```

#### 4.3 Send Welcome Email Method (Lines 136-227)
**Method:** `send_welcome_email()`
- **Purpose:** New user को welcome email भेजना
- **Similar structure** जैसे invite email

---

### 5. Database Models

#### 5.1 Invite Model
**File:** `backend/models/invite.py`

##### Invite Status Enum (Lines 12-17)
```python
class InviteStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
```

##### Invite Class (Lines 20-51)
- **Line 25:** `id = Column(Integer, primary_key=True, index=True)`
- **Line 26:** `email = Column(String, index=True, nullable=False)`
- **Line 27:** `token = Column(String, unique=True, index=True, nullable=False)`
- **Line 28:** `status = Column(String, default=InviteStatus.PENDING, nullable=False)`
- **Line 29:** `expiry_date = Column(DateTime, nullable=False)`
- **Line 34:** `created_by_id = Column(Integer, ForeignKey("users.id"), nullable=False)`
- **Line 37:** `created_by = relationship("User", foreign_keys=[created_by_id], back_populates="created_invites")`

##### Is Expired Property (Lines 42-45)
```python
@property
def is_expired(self) -> bool:
    return datetime.utcnow() > self.expiry_date
```

---

### 6. Pydantic Schemas
**File:** `backend/schemas/invite.py`

#### 6.1 Invite Create Schema (Lines 8-10)
```python
class InviteCreate(BaseModel):
    email: EmailStr
```

#### 6.2 Invite Response Schema (Lines 13-24)
```python
class InviteResponse(BaseModel):
    id: int
    email: str
    token: str
    status: str
    expiry_date: datetime
    created_at: datetime
    created_by_id: int
```

#### 6.3 Invite Accept Schema (Lines 27-30)
```python
class InviteAccept(BaseModel):
    token: str
    password: str
```

---

## 🔄 Complete Workflow Step by Step

### Step 1: Admin Login करके Invite भेजता है
1. Admin login करता है
2. `POST /api/admin/invite-user` endpoint call करता है
3. Email address provide करता है

### Step 2: Server Side Validation
1. **invites.py Line 28-36:** Check करता है कि user पहले से exist तो नहीं करता
2. **invites.py Line 38-54:** Check करता है कि pending invite तो नहीं है
3. **invites.py Line 57:** Secure token generate करता है

### Step 3: Database में Invite Store करना
1. **invites.py Line 60-70:** Invite record create करता है
2. Database में invite store हो जाता है
3. Status: "pending", Expiry: 7 days

### Step 4: Email भेजना
1. **email.py Line 40:** Invite link generate करता है
2. **email.py Line 46-112:** HTML email template prepare करता है
3. **email.py Line 123-125:** SMTP के through email भेजता है
4. Email में "Accept Invitation" button होता है

### Step 5: User को Email मिलता है
1. User को invitation email मिलता है
2. Email में invite link होता है: `http://localhost:8000/accept-invite/{token}`

### Step 6: User Invite Accept करता है
1. User email में "Accept Invitation" button पर click करता है
2. Browser में invite page open होता है
3. User password set करके account create करता है
4. `POST /api/accept-invite/{token}` endpoint call होता है

### Step 7: Server Side Invite Validation
1. **invites.py Line 159-182:** Token validate करता है
2. Check करता है कि invite expire तो नहीं हुआ
3. Token matching check करता है

### Step 8: User Account Create करना
1. **invites.py Line 204-213:** New user account create करता है
2. Password hash करके store करता है
3. User role: "user", is_active: True

### Step 9: Invite Status Update करना
1. **invites.py Line 217-218:** Invite status "accepted" में change करता है
2. Database में update हो जाता है

### Step 10: Welcome Email भेजना
1. **email.py Line 136-227:** Welcome email भेजता है
2. User को successful registration का notification मिलता है

---

## 🔗 File Connections Summary

```
.env.example (Email Config)
    ↓
backend/main.py (Router Registration)
    ↓
backend/routers/invites.py (Main Logic)
    ↓
backend/services/email.py (Email Sending)
    ↓
backend/models/invite.py (Database Model)
    ↓
backend/schemas/invite.py (Data Validation)
```

---

## 🛠️ Important Functions और उनकी Lines

### 1. Token Generation
- **File:** `backend/services/auth.py`
- **Function:** `generate_secure_token()`
- **Used in:** `invites.py Line 57`

### 2. Password Hashing
- **File:** `backend/services/auth.py`
- **Function:** `get_password_hash()`
- **Used in:** `invites.py Line 206`

### 3. Email Template
- **File:** `backend/services/email.py`
- **Lines 46-112:** Invite email HTML template
- **Lines 142-205:** Welcome email HTML template

---

## 📊 Database Tables Structure

### Invites Table
- id (Primary Key)
- email (Indexed)
- token (Unique, Indexed)
- status (pending/accepted/expired/cancelled)
- expiry_date (DateTime)
- created_at (DateTime)
- updated_at (DateTime)
- created_by_id (Foreign Key → users.id)

### Users Table
- id (Primary Key)
- email (Unique, Indexed)
- password_hash
- role (admin/user)
- is_active (Boolean)
- created_at (DateTime)
- updated_at (DateTime)

---

## 🔒 Security Features

1. **Secure Token Generation:** Unique tokens for each invite
2. **Token Expiry:** 7 days expiry automatically
3. **Password Hashing:** Secure password storage
4. **Admin Authentication:** Only admins can send invites
5. **Email Validation:** Pydantic EmailStr validation
6. **Status Tracking:** Complete invite lifecycle tracking

---

## 🚀 API Endpoints Summary

### Admin Endpoints
- `POST /api/admin/invite-user` - Create new invite
- `GET /api/admin/invites` - List all invites
- `DELETE /api/admin/invites/{invite_id}` - Cancel invite

### User Endpoints
- `GET /api/accept-invite/{token}` - Check invite validity
- `POST /api/accept-invite/{token}` - Accept invite and create account

---

यह complete workflow है जो admin invitation email system को implement करता है। हर step properly connected है और secure तरीके से काम करता है।
