-- ============================================================================
-- FREIGHT BOOKING SYSTEM - EDI TABLES
-- ============================================================================
-- EDI ANSI X12 transaction tracking and partner configuration
-- ============================================================================

-- ----------------------------------------------------------------------------
-- EDI PARTNERS TABLE
-- ----------------------------------------------------------------------------
-- Trading partner configuration for EDI communication
-- ----------------------------------------------------------------------------
CREATE TABLE edi_partners (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    -- Partner Identification
    partner_code NVARCHAR(20) NOT NULL UNIQUE,   -- Internal code
    partner_name NVARCHAR(255) NOT NULL,
    partner_type NVARCHAR(20) NOT NULL,          -- 'CARRIER', 'CUSTOMER', 'AGENT'

    -- EDI Identifiers (ISA segment)
    isa_qualifier CHAR(2) NOT NULL DEFAULT 'ZZ', -- ISA05/ISA07 qualifier
    isa_id NVARCHAR(15) NOT NULL,                -- ISA06/ISA08 ID (padded to 15)

    -- GS Level Identifiers
    gs_id NVARCHAR(15) NOT NULL,                 -- GS02/GS03 Application ID

    -- Communication Settings
    comm_method NVARCHAR(20) NOT NULL,           -- 'AS2', 'SFTP', 'FTP', 'VAN'

    -- AS2 Settings
    as2_id NVARCHAR(100),
    as2_url NVARCHAR(500),
    as2_certificate NVARCHAR(MAX),               -- Base64 encoded certificate

    -- SFTP Settings
    sftp_host NVARCHAR(255),
    sftp_port INT DEFAULT 22,
    sftp_username NVARCHAR(100),
    sftp_password_encrypted NVARCHAR(MAX),       -- Encrypted
    sftp_private_key_encrypted NVARCHAR(MAX),    -- Encrypted
    sftp_inbound_path NVARCHAR(255),
    sftp_outbound_path NVARCHAR(255),

    -- EDI Settings
    segment_terminator CHAR(1) DEFAULT '~',
    element_separator CHAR(1) DEFAULT '*',
    subelement_separator CHAR(1) DEFAULT ':',
    use_line_breaks BIT DEFAULT 0,

    -- Transaction Types Supported
    supports_300 BIT DEFAULT 0,                  -- Ocean Booking Request
    supports_301 BIT DEFAULT 0,                  -- Ocean Booking Confirmation
    supports_304 BIT DEFAULT 0,                  -- Shipping Instructions
    supports_204 BIT DEFAULT 0,                  -- Motor Carrier Load Tender
    supports_990 BIT DEFAULT 0,                  -- Response to Load Tender
    supports_214 BIT DEFAULT 0,                  -- Shipment Status
    supports_210 BIT DEFAULT 0,                  -- Freight Invoice

    -- Status
    is_active BIT DEFAULT 1,
    last_successful_send DATETIME2,
    last_successful_receive DATETIME2,

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE()
);

-- Index
CREATE INDEX idx_edi_partners_active ON edi_partners(is_active) WHERE is_active = 1;


-- ----------------------------------------------------------------------------
-- EDI CONTROL NUMBERS TABLE
-- ----------------------------------------------------------------------------
-- Track ISA, GS, and ST control numbers per partner
-- Ensures uniqueness and sequential generation
-- ----------------------------------------------------------------------------
CREATE TABLE edi_control_numbers (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    edi_partner_id UNIQUEIDENTIFIER NOT NULL,

    number_type NVARCHAR(10) NOT NULL,           -- 'ISA', 'GS', 'ST'

    -- For ST numbers, also track transaction type
    transaction_type NVARCHAR(10),               -- '300', '301', '204', etc.

    current_number BIGINT NOT NULL DEFAULT 0,
    last_used_at DATETIME2,

    FOREIGN KEY (edi_partner_id) REFERENCES edi_partners(id),
    UNIQUE (edi_partner_id, number_type, transaction_type)
);


-- ----------------------------------------------------------------------------
-- EDI OUTBOUND QUEUE TABLE
-- ----------------------------------------------------------------------------
-- Queue of EDI messages pending transmission
-- ----------------------------------------------------------------------------
CREATE TABLE edi_outbound_queue (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    -- Reference
    booking_id UNIQUEIDENTIFIER NOT NULL,
    edi_partner_id UNIQUEIDENTIFIER NOT NULL,

    -- Transaction Info
    transaction_type NVARCHAR(10) NOT NULL,      -- '300', '304', '204', '997'
    transaction_purpose NVARCHAR(20),            -- '00' (Original), '01' (Cancel), '04' (Change)

    -- Control Numbers
    isa_control_number BIGINT,
    gs_control_number BIGINT,
    st_control_number BIGINT,

    -- Content
    edi_content NVARCHAR(MAX),                   -- Generated EDI content
    file_name NVARCHAR(255),

    -- Status
    status NVARCHAR(20) NOT NULL DEFAULT 'PENDING',
    -- Statuses: 'PENDING', 'PROCESSING', 'SENT', 'ACKNOWLEDGED', 'FAILED', 'RETRY'

    -- Transmission Tracking
    scheduled_at DATETIME2 DEFAULT GETUTCDATE(),
    sent_at DATETIME2,
    acknowledged_at DATETIME2,

    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    next_retry_at DATETIME2,

    error_message NVARCHAR(MAX),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id),
    FOREIGN KEY (edi_partner_id) REFERENCES edi_partners(id)
);

-- Indexes
CREATE INDEX idx_edi_outbound_status ON edi_outbound_queue(status, scheduled_at);
CREATE INDEX idx_edi_outbound_booking ON edi_outbound_queue(booking_id);
CREATE INDEX idx_edi_outbound_partner ON edi_outbound_queue(edi_partner_id);


-- ----------------------------------------------------------------------------
-- EDI INBOUND RAW TABLE
-- ----------------------------------------------------------------------------
-- Store raw received EDI files before parsing
-- ----------------------------------------------------------------------------
CREATE TABLE edi_inbound_raw (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    edi_partner_id UNIQUEIDENTIFIER,             -- NULL if sender unknown

    -- File Info
    file_name NVARCHAR(255) NOT NULL,
    file_path NVARCHAR(500),                     -- Azure Blob path
    file_size_bytes BIGINT,

    -- Raw Content
    edi_content NVARCHAR(MAX) NOT NULL,

    -- Envelope Info (extracted during initial parse)
    isa_control_number BIGINT,
    isa_sender_id NVARCHAR(15),
    isa_receiver_id NVARCHAR(15),
    isa_date NVARCHAR(10),
    isa_time NVARCHAR(4),

    -- Status
    status NVARCHAR(20) NOT NULL DEFAULT 'RECEIVED',
    -- Statuses: 'RECEIVED', 'PARSING', 'PARSED', 'ERROR'

    error_message NVARCHAR(MAX),

    received_at DATETIME2 DEFAULT GETUTCDATE(),
    parsed_at DATETIME2,

    FOREIGN KEY (edi_partner_id) REFERENCES edi_partners(id)
);

-- Indexes
CREATE INDEX idx_edi_inbound_raw_status ON edi_inbound_raw(status);
CREATE INDEX idx_edi_inbound_raw_received ON edi_inbound_raw(received_at DESC);
CREATE INDEX idx_edi_inbound_raw_isa ON edi_inbound_raw(isa_sender_id, isa_control_number);


-- ----------------------------------------------------------------------------
-- EDI TRANSACTIONS TABLE
-- ----------------------------------------------------------------------------
-- Parsed EDI transaction records
-- ----------------------------------------------------------------------------
CREATE TABLE edi_transactions (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    -- Source
    edi_inbound_raw_id UNIQUEIDENTIFIER,         -- For inbound
    edi_outbound_queue_id UNIQUEIDENTIFIER,      -- For outbound

    direction NVARCHAR(10) NOT NULL,             -- 'INBOUND', 'OUTBOUND'
    edi_partner_id UNIQUEIDENTIFIER NOT NULL,

    -- Transaction Details
    transaction_type NVARCHAR(10) NOT NULL,      -- '300', '301', '214', etc.
    st_control_number BIGINT,
    transaction_purpose NVARCHAR(20),

    -- Related Booking
    booking_id UNIQUEIDENTIFIER,
    booking_number NVARCHAR(20),
    carrier_booking_ref NVARCHAR(50),

    -- Parsed Data (JSON structure)
    parsed_data NVARCHAR(MAX),                   -- Full parsed transaction as JSON

    -- Key Extracted Fields (for querying)
    vessel_name NVARCHAR(100),
    voyage_number NVARCHAR(50),
    port_of_loading NVARCHAR(10),
    port_of_discharge NVARCHAR(10),
    etd DATE,
    eta DATE,

    -- Status
    status NVARCHAR(20) NOT NULL DEFAULT 'RECEIVED',
    -- Statuses: 'RECEIVED', 'PROCESSING', 'APPLIED', 'ERROR', 'IGNORED'

    processing_notes NVARCHAR(MAX),
    error_message NVARCHAR(MAX),

    -- 997 Acknowledgment Tracking (for outbound)
    ack_status NVARCHAR(20),                     -- 'PENDING', 'ACCEPTED', 'REJECTED'
    ack_received_at DATETIME2,
    ack_error_codes NVARCHAR(500),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    processed_at DATETIME2,

    FOREIGN KEY (edi_inbound_raw_id) REFERENCES edi_inbound_raw(id),
    FOREIGN KEY (edi_outbound_queue_id) REFERENCES edi_outbound_queue(id),
    FOREIGN KEY (edi_partner_id) REFERENCES edi_partners(id),
    FOREIGN KEY (booking_id) REFERENCES bookings(id)
);

-- Indexes
CREATE INDEX idx_edi_transactions_direction ON edi_transactions(direction, created_at DESC);
CREATE INDEX idx_edi_transactions_booking ON edi_transactions(booking_id);
CREATE INDEX idx_edi_transactions_type ON edi_transactions(transaction_type);
CREATE INDEX idx_edi_transactions_status ON edi_transactions(status) WHERE status IN ('RECEIVED', 'PROCESSING', 'ERROR');


-- ----------------------------------------------------------------------------
-- EDI ACKNOWLEDGMENTS TABLE
-- ----------------------------------------------------------------------------
-- Track 997 Functional Acknowledgments
-- ----------------------------------------------------------------------------
CREATE TABLE edi_acknowledgments (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),

    -- What we're acknowledging
    edi_inbound_raw_id UNIQUEIDENTIFIER,         -- The received interchange
    edi_transaction_id UNIQUEIDENTIFIER,         -- Specific transaction if applicable

    -- Our 997 Response
    edi_outbound_queue_id UNIQUEIDENTIFIER,      -- Our 997 in outbound queue

    -- Acknowledgment Details
    ack_code NVARCHAR(2),                        -- 'A' (Accepted), 'E' (Accepted with Errors), 'R' (Rejected)
    error_codes NVARCHAR(500),                   -- Comma-separated error codes

    -- ISA being acknowledged
    original_isa_control BIGINT,
    original_isa_date NVARCHAR(10),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    sent_at DATETIME2,

    FOREIGN KEY (edi_inbound_raw_id) REFERENCES edi_inbound_raw(id),
    FOREIGN KEY (edi_transaction_id) REFERENCES edi_transactions(id),
    FOREIGN KEY (edi_outbound_queue_id) REFERENCES edi_outbound_queue(id)
);

-- Index
CREATE INDEX idx_edi_acknowledgments_inbound ON edi_acknowledgments(edi_inbound_raw_id);
