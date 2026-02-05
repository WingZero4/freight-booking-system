-- ============================================================================
-- FREIGHT BOOKING SYSTEM - WORKFLOW TABLES
-- ============================================================================
-- Configurable approval workflows per customer
-- ============================================================================

-- ----------------------------------------------------------------------------
-- WORKFLOW CONFIGS TABLE
-- ----------------------------------------------------------------------------
-- Customer-specific workflow rule sets
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_configs (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    customer_id UNIQUEIDENTIFIER NOT NULL,

    name NVARCHAR(100) NOT NULL,
    description NVARCHAR(500),

    -- Trigger Conditions (booking must match all non-null conditions)
    transport_mode NVARCHAR(20),                 -- NULL = all modes
    min_booking_value DECIMAL(18, 2),            -- Trigger if value >= this
    max_booking_value DECIMAL(18, 2),            -- Trigger if value <= this
    is_dangerous_goods BIT,                      -- NULL = any, 1 = DG only, 0 = non-DG only
    origin_country_code CHAR(2),                 -- NULL = any origin
    destination_country_code CHAR(2),            -- NULL = any destination

    -- Workflow Settings
    requires_approval BIT DEFAULT 1,
    approval_type NVARCHAR(20) DEFAULT 'SEQUENTIAL', -- 'SEQUENTIAL', 'PARALLEL', 'ANY'
    auto_approve_below_value DECIMAL(18, 2),     -- Auto-approve if value < this

    -- Active/Priority
    is_active BIT DEFAULT 1,
    priority INT DEFAULT 100,                    -- Lower = higher priority for matching

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),
    created_by_user_id UNIQUEIDENTIFIER,

    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Indexes
CREATE INDEX idx_workflow_configs_customer ON workflow_configs(customer_id);
CREATE INDEX idx_workflow_configs_active ON workflow_configs(is_active, priority) WHERE is_active = 1;


-- ----------------------------------------------------------------------------
-- WORKFLOW STEPS TABLE
-- ----------------------------------------------------------------------------
-- Individual approval steps within a workflow
-- ----------------------------------------------------------------------------
CREATE TABLE workflow_steps (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    workflow_config_id UNIQUEIDENTIFIER NOT NULL,

    step_order INT NOT NULL,                     -- Execution order (1, 2, 3...)
    step_name NVARCHAR(100) NOT NULL,            -- 'Manager Approval', 'Finance Review', etc.

    -- Approver Assignment
    approver_type NVARCHAR(20) NOT NULL,         -- 'USER', 'ROLE', 'MANAGER'
    approver_user_id UNIQUEIDENTIFIER,           -- If type = USER
    approver_role NVARCHAR(50),                  -- If type = ROLE ('ADMIN', 'MANAGER', etc.)

    -- Escalation Settings
    escalation_hours INT,                        -- Escalate if no response in X hours
    escalation_user_id UNIQUEIDENTIFIER,         -- Who to escalate to

    -- Step Options
    is_optional BIT DEFAULT 0,                   -- Can this step be skipped?
    can_delegate BIT DEFAULT 1,                  -- Can approver delegate?

    FOREIGN KEY (workflow_config_id) REFERENCES workflow_configs(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_workflow_steps_config ON workflow_steps(workflow_config_id);
CREATE UNIQUE INDEX idx_workflow_steps_order ON workflow_steps(workflow_config_id, step_order);


-- ----------------------------------------------------------------------------
-- BOOKING APPROVALS TABLE
-- ----------------------------------------------------------------------------
-- Approval records for each booking going through a workflow
-- ----------------------------------------------------------------------------
CREATE TABLE booking_approvals (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,
    workflow_config_id UNIQUEIDENTIFIER,
    workflow_step_id UNIQUEIDENTIFIER,

    step_order INT NOT NULL,

    -- Assignment
    assigned_to_user_id UNIQUEIDENTIFIER NOT NULL,
    assigned_at DATETIME2 DEFAULT GETUTCDATE(),

    -- Decision
    status NVARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- Statuses: 'WAITING', 'PENDING', 'APPROVED', 'REJECTED', 'SKIPPED', 'DELEGATED'

    decision_at DATETIME2,
    decision_by_user_id UNIQUEIDENTIFIER,        -- May differ from assigned if delegated

    comments NVARCHAR(MAX),

    -- Escalation Tracking
    escalated_at DATETIME2,
    escalated_to_user_id UNIQUEIDENTIFIER,
    escalation_count INT DEFAULT 0,

    -- Delegation
    delegated_from_user_id UNIQUEIDENTIFIER,
    delegated_at DATETIME2,

    -- Reminder Tracking
    last_reminder_sent_at DATETIME2,
    reminder_count INT DEFAULT 0,

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (workflow_config_id) REFERENCES workflow_configs(id),
    FOREIGN KEY (workflow_step_id) REFERENCES workflow_steps(id)
);

-- Indexes
CREATE INDEX idx_booking_approvals_booking ON booking_approvals(booking_id);
CREATE INDEX idx_booking_approvals_assigned ON booking_approvals(assigned_to_user_id, status);
CREATE INDEX idx_booking_approvals_pending ON booking_approvals(status, assigned_at) WHERE status = 'PENDING';


-- ----------------------------------------------------------------------------
-- APPROVAL DELEGATION LOG
-- ----------------------------------------------------------------------------
-- Track delegation history for audit purposes
-- ----------------------------------------------------------------------------
CREATE TABLE approval_delegations (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_approval_id UNIQUEIDENTIFIER NOT NULL,

    from_user_id UNIQUEIDENTIFIER NOT NULL,
    to_user_id UNIQUEIDENTIFIER NOT NULL,
    delegated_at DATETIME2 DEFAULT GETUTCDATE(),

    reason NVARCHAR(500),

    FOREIGN KEY (booking_approval_id) REFERENCES booking_approvals(id) ON DELETE CASCADE
);

-- Index
CREATE INDEX idx_approval_delegations_approval ON approval_delegations(booking_approval_id);
