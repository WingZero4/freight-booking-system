-- ============================================================================
-- FREIGHT BOOKING SYSTEM - BOOKING CORE TABLES
-- ============================================================================
-- Main booking entity and cargo items
-- ============================================================================

-- ----------------------------------------------------------------------------
-- BOOKINGS TABLE
-- ----------------------------------------------------------------------------
-- Core booking entity - common fields for all transport modes
-- Modal-specific data stored in related tables (composition pattern)
-- ----------------------------------------------------------------------------
CREATE TABLE bookings (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_number NVARCHAR(20) NOT NULL UNIQUE, -- System-generated: BK-2024-000001

    -- Transport Mode
    transport_mode NVARCHAR(20) NOT NULL,        -- 'OCEAN_FCL', 'OCEAN_LCL', 'AIR', 'ROAD'

    -- Parties
    customer_id UNIQUEIDENTIFIER NOT NULL,       -- The booking customer
    shipper_id UNIQUEIDENTIFIER,                 -- Can be customer or different party
    consignee_id UNIQUEIDENTIFIER,
    notify_party_id UNIQUEIDENTIFIER,

    -- Created By
    created_by_user_id UNIQUEIDENTIFIER NOT NULL,

    -- Route (high-level)
    origin_location_id UNIQUEIDENTIFIER NOT NULL,
    destination_location_id UNIQUEIDENTIFIER NOT NULL,

    -- Carrier
    carrier_id UNIQUEIDENTIFIER,
    carrier_booking_ref NVARCHAR(50),            -- Carrier's booking reference

    -- Dates
    cargo_ready_date DATE NOT NULL,
    requested_pickup_date DATE,
    requested_delivery_date DATE,
    estimated_departure_date DATE,
    estimated_arrival_date DATE,
    actual_departure_date DATE,
    actual_arrival_date DATE,

    -- Terms
    incoterm NVARCHAR(10),                       -- 'FOB', 'CIF', 'EXW', etc.
    incoterm_location NVARCHAR(255),
    payment_terms NVARCHAR(50),

    -- Cargo Summary (aggregated from booking_items)
    total_pieces INT,
    total_gross_weight_kg DECIMAL(12, 3),
    total_volume_m3 DECIMAL(12, 4),
    total_chargeable_weight_kg DECIMAL(12, 3),

    -- Value
    declared_value DECIMAL(18, 2),
    declared_value_currency CHAR(3) DEFAULT 'USD',

    -- Status
    status NVARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    -- Statuses: DRAFT, PENDING_APPROVAL, APPROVED, SUBMITTED_TO_CARRIER,
    --           CONFIRMED, IN_TRANSIT, DELIVERED, CANCELLED, REJECTED

    -- Workflow
    requires_approval BIT DEFAULT 0,
    approval_status NVARCHAR(20),                -- NULL, 'PENDING', 'APPROVED', 'REJECTED'
    approved_by_user_id UNIQUEIDENTIFIER,
    approved_at DATETIME2,
    approval_notes NVARCHAR(MAX),

    -- Special Instructions
    special_instructions NVARCHAR(MAX),
    internal_notes NVARCHAR(MAX),                -- Not visible to customer

    -- Timestamps
    submitted_at DATETIME2,
    confirmed_at DATETIME2,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (origin_location_id) REFERENCES locations(id),
    FOREIGN KEY (destination_location_id) REFERENCES locations(id),
    FOREIGN KEY (carrier_id) REFERENCES carriers(id)
);

-- Indexes
CREATE INDEX idx_bookings_customer ON bookings(customer_id);
CREATE INDEX idx_bookings_status ON bookings(status);
CREATE INDEX idx_bookings_transport_mode ON bookings(transport_mode);
CREATE INDEX idx_bookings_created_at ON bookings(created_at DESC);
CREATE INDEX idx_bookings_cargo_ready ON bookings(cargo_ready_date);
CREATE INDEX idx_bookings_carrier_ref ON bookings(carrier_booking_ref) WHERE carrier_booking_ref IS NOT NULL;


-- ----------------------------------------------------------------------------
-- BOOKING ITEMS TABLE
-- ----------------------------------------------------------------------------
-- Individual cargo items/line items within a booking
-- ----------------------------------------------------------------------------
CREATE TABLE booking_items (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,
    line_number INT NOT NULL,

    -- Commodity
    commodity_id UNIQUEIDENTIFIER,
    commodity_description NVARCHAR(500) NOT NULL,
    hs_code NVARCHAR(10),

    -- Packaging
    package_type NVARCHAR(50),                   -- 'PALLET', 'CARTON', 'CRATE', etc.
    package_count INT NOT NULL,

    -- Dimensions & Weight (per package)
    length_cm DECIMAL(10, 2),
    width_cm DECIMAL(10, 2),
    height_cm DECIMAL(10, 2),
    gross_weight_kg DECIMAL(12, 3) NOT NULL,
    net_weight_kg DECIMAL(12, 3),
    volume_m3 DECIMAL(12, 4),

    -- Marks & Numbers
    marks_and_numbers NVARCHAR(500),

    -- Dangerous Goods
    is_dangerous_goods BIT DEFAULT 0,
    dg_un_number NVARCHAR(10),
    dg_class NVARCHAR(10),
    dg_packing_group NVARCHAR(5),
    dg_proper_shipping_name NVARCHAR(255),

    -- Temperature Control
    is_temperature_controlled BIT DEFAULT 0,
    required_temp_min_c DECIMAL(5, 2),
    required_temp_max_c DECIMAL(5, 2),

    special_handling_notes NVARCHAR(MAX),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (commodity_id) REFERENCES commodities(id)
);

-- Indexes
CREATE INDEX idx_booking_items_booking ON booking_items(booking_id);
CREATE INDEX idx_booking_items_dangerous ON booking_items(is_dangerous_goods) WHERE is_dangerous_goods = 1;


-- ----------------------------------------------------------------------------
-- BOOKING ROUTES TABLE
-- ----------------------------------------------------------------------------
-- Multi-leg shipment routing (for intermodal shipments)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_routes (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,
    leg_number INT NOT NULL,

    transport_mode NVARCHAR(20) NOT NULL,        -- Can differ per leg

    origin_location_id UNIQUEIDENTIFIER NOT NULL,
    destination_location_id UNIQUEIDENTIFIER NOT NULL,

    carrier_id UNIQUEIDENTIFIER,
    vessel_or_flight NVARCHAR(100),
    voyage_or_flight_number NVARCHAR(50),

    estimated_departure DATETIME2,
    estimated_arrival DATETIME2,
    actual_departure DATETIME2,
    actual_arrival DATETIME2,

    status NVARCHAR(30) DEFAULT 'PENDING',       -- 'PENDING', 'IN_TRANSIT', 'COMPLETED'

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (origin_location_id) REFERENCES locations(id),
    FOREIGN KEY (destination_location_id) REFERENCES locations(id),
    FOREIGN KEY (carrier_id) REFERENCES carriers(id)
);

-- Indexes
CREATE INDEX idx_booking_routes_booking ON booking_routes(booking_id);
CREATE UNIQUE INDEX idx_booking_routes_leg ON booking_routes(booking_id, leg_number);


-- ----------------------------------------------------------------------------
-- BOOKING DOCUMENTS TABLE
-- ----------------------------------------------------------------------------
-- File attachments for bookings (stored in Azure Blob)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_documents (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,

    document_type NVARCHAR(50) NOT NULL,
    -- Types: 'COMMERCIAL_INVOICE', 'PACKING_LIST', 'BILL_OF_LADING',
    --        'AIR_WAYBILL', 'CERTIFICATE_OF_ORIGIN', 'MSDS', 'CUSTOMS_DECLARATION',
    --        'INSURANCE_CERTIFICATE', 'LETTER_OF_CREDIT', 'OTHER'

    file_name NVARCHAR(255) NOT NULL,            -- UUID-based name in storage
    original_file_name NVARCHAR(255) NOT NULL,   -- User's original filename
    file_path NVARCHAR(500) NOT NULL,            -- Azure Blob or S3 path
    file_size_bytes BIGINT,
    mime_type NVARCHAR(100),

    description NVARCHAR(500),

    -- Version control
    version INT DEFAULT 1,
    is_current_version BIT DEFAULT 1,
    previous_version_id UNIQUEIDENTIFIER,

    uploaded_by_user_id UNIQUEIDENTIFIER NOT NULL,
    uploaded_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (previous_version_id) REFERENCES booking_documents(id)
);

-- Indexes
CREATE INDEX idx_booking_documents_booking ON booking_documents(booking_id);
CREATE INDEX idx_booking_documents_type ON booking_documents(document_type);
CREATE INDEX idx_booking_documents_current ON booking_documents(booking_id, is_current_version) WHERE is_current_version = 1;


-- ----------------------------------------------------------------------------
-- BOOKING PARTIES TABLE
-- ----------------------------------------------------------------------------
-- Additional parties on a booking (beyond shipper/consignee)
-- Notify parties, freight forwarders, customs brokers, etc.
-- ----------------------------------------------------------------------------
CREATE TABLE booking_parties (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,

    party_type NVARCHAR(30) NOT NULL,            -- 'NOTIFY', 'FREIGHT_FORWARDER', 'CUSTOMS_BROKER', 'AGENT'
    customer_id UNIQUEIDENTIFIER,                -- If existing customer

    -- Or ad-hoc party details
    company_name NVARCHAR(255),
    contact_name NVARCHAR(100),
    email NVARCHAR(255),
    phone NVARCHAR(50),
    address NVARCHAR(500),

    created_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- Indexes
CREATE INDEX idx_booking_parties_booking ON booking_parties(booking_id);
