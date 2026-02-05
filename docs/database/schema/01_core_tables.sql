-- ============================================================================
-- FREIGHT BOOKING SYSTEM - CORE TABLES
-- ============================================================================
-- Customer & User Management, Audit Trail
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CUSTOMERS TABLE
-- ----------------------------------------------------------------------------
-- Represents shipper/consignee companies that use the booking portal
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(20) NOT NULL UNIQUE,          -- Customer code (e.g., 'CUST001')
    name NVARCHAR(255) NOT NULL,                -- Display name
    legal_name NVARCHAR(255),                   -- Legal entity name
    tax_id NVARCHAR(50),                        -- Tax identification number
    customer_type NVARCHAR(20) NOT NULL,        -- 'SHIPPER', 'CONSIGNEE', 'BOTH'

    -- Contact Information
    email NVARCHAR(255),
    phone NVARCHAR(50),
    website NVARCHAR(255),

    -- Primary Address
    address_line1 NVARCHAR(255),
    address_line2 NVARCHAR(255),
    city NVARCHAR(100),
    state_province NVARCHAR(100),
    postal_code NVARCHAR(20),
    country_code CHAR(2),                       -- ISO 3166-1 alpha-2

    -- Default Settings
    default_incoterm NVARCHAR(10),              -- 'FOB', 'CIF', 'EXW', etc.
    credit_limit DECIMAL(18, 2),
    payment_terms_days INT DEFAULT 30,

    -- Status
    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),
    created_by UNIQUEIDENTIFIER,
    updated_by UNIQUEIDENTIFIER
);

-- Indexes
CREATE INDEX idx_customers_code ON customers(code);
CREATE INDEX idx_customers_name ON customers(name);
CREATE INDEX idx_customers_active ON customers(is_active) WHERE is_active = 1;


-- ----------------------------------------------------------------------------
-- USER PROFILES TABLE
-- ----------------------------------------------------------------------------
-- Extends Django's auth_user with application-specific data
-- Links users to customers (NULL customer_id = internal staff)
-- ----------------------------------------------------------------------------
CREATE TABLE user_profiles (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    user_id INT NOT NULL UNIQUE,                -- FK to Django auth_user
    customer_id UNIQUEIDENTIFIER,               -- NULL for internal staff

    -- Profile Information
    job_title NVARCHAR(100),
    department NVARCHAR(100),
    phone NVARCHAR(50),
    mobile NVARCHAR(50),

    -- Permissions
    role NVARCHAR(50) NOT NULL,                 -- 'ADMIN', 'MANAGER', 'OPERATOR', 'VIEWER'
    can_approve_bookings BIT DEFAULT 0,
    approval_limit DECIMAL(18, 2),              -- Max booking value they can approve

    -- Preferences
    timezone NVARCHAR(50) DEFAULT 'UTC',
    notification_preferences NVARCHAR(MAX),     -- JSON: email, in-app settings

    -- Status
    is_active BIT DEFAULT 1,
    last_login_at DATETIME2,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Indexes
CREATE INDEX idx_user_profiles_customer ON user_profiles(customer_id);
CREATE INDEX idx_user_profiles_role ON user_profiles(role);
CREATE INDEX idx_user_profiles_user ON user_profiles(user_id);


-- ----------------------------------------------------------------------------
-- AUDIT LOG TABLE
-- ----------------------------------------------------------------------------
-- Immutable log of all data changes for compliance and debugging
-- ----------------------------------------------------------------------------
CREATE TABLE audit_log (
    id BIGINT IDENTITY(1,1) PRIMARY KEY,

    -- What changed
    entity_type NVARCHAR(50) NOT NULL,          -- 'BOOKING', 'CUSTOMER', 'USER', etc.
    entity_id NVARCHAR(50) NOT NULL,            -- UUID as string

    -- Action
    action NVARCHAR(20) NOT NULL,               -- 'CREATE', 'UPDATE', 'DELETE', 'STATUS_CHANGE'

    -- Who/When
    performed_by_user_id UNIQUEIDENTIFIER,
    performed_at DATETIME2 DEFAULT GETUTCDATE(),

    -- What was changed
    field_name NVARCHAR(100),
    old_value NVARCHAR(MAX),
    new_value NVARCHAR(MAX),

    -- Full snapshot (optional, for critical entities)
    entity_snapshot NVARCHAR(MAX),              -- JSON of entity state

    -- Context
    ip_address NVARCHAR(45),
    user_agent NVARCHAR(500),
    request_id NVARCHAR(50),

    -- Additional context
    metadata NVARCHAR(MAX)                      -- JSON for additional context
);

-- Indexes (audit tables need fast reads by entity and date)
CREATE INDEX idx_audit_log_entity ON audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_log_user ON audit_log(performed_by_user_id);
CREATE INDEX idx_audit_log_date ON audit_log(performed_at DESC);
CREATE INDEX idx_audit_log_action ON audit_log(action, performed_at DESC);


-- ----------------------------------------------------------------------------
-- BOOKING STATUS HISTORY TABLE
-- ----------------------------------------------------------------------------
-- Denormalized status history for fast access to booking state transitions
-- ----------------------------------------------------------------------------
CREATE TABLE booking_status_history (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,

    from_status NVARCHAR(30),
    to_status NVARCHAR(30) NOT NULL,

    changed_by_user_id UNIQUEIDENTIFIER,
    changed_at DATETIME2 DEFAULT GETUTCDATE(),

    reason NVARCHAR(500),
    notes NVARCHAR(MAX)
);

-- Index for booking timeline queries
CREATE INDEX idx_booking_status_history_booking ON booking_status_history(booking_id, changed_at DESC);


-- ----------------------------------------------------------------------------
-- NOTIFICATION TEMPLATES TABLE
-- ----------------------------------------------------------------------------
-- Email templates with placeholder support
-- ----------------------------------------------------------------------------
CREATE TABLE notification_templates (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    code NVARCHAR(50) NOT NULL UNIQUE,          -- 'BOOKING_SUBMITTED', 'APPROVAL_REQUIRED', etc.
    name NVARCHAR(100) NOT NULL,
    description NVARCHAR(500),

    -- Template Content (supports placeholders like {{booking_number}})
    email_subject_template NVARCHAR(500),
    email_body_template NVARCHAR(MAX),

    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE()
);


-- ----------------------------------------------------------------------------
-- NOTIFICATIONS TABLE
-- ----------------------------------------------------------------------------
-- Email notification queue for async processing
-- ----------------------------------------------------------------------------
CREATE TABLE notifications (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    template_code NVARCHAR(50) NOT NULL,

    -- Target
    recipient_user_id UNIQUEIDENTIFIER,
    recipient_email NVARCHAR(255) NOT NULL,

    -- Content (rendered from template)
    subject NVARCHAR(500) NOT NULL,
    body NVARCHAR(MAX) NOT NULL,

    -- Context
    booking_id UNIQUEIDENTIFIER,

    -- Status
    status NVARCHAR(20) DEFAULT 'PENDING',      -- 'PENDING', 'SENT', 'FAILED', 'RETRY'
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,

    sent_at DATETIME2,
    error_message NVARCHAR(MAX),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    scheduled_for DATETIME2 DEFAULT GETUTCDATE()
);

-- Indexes for queue processing
CREATE INDEX idx_notifications_status ON notifications(status, scheduled_for);
CREATE INDEX idx_notifications_recipient ON notifications(recipient_email);
CREATE INDEX idx_notifications_booking ON notifications(booking_id);
