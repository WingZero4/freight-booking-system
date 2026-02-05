-- ============================================================================
-- FREIGHT BOOKING SYSTEM - MVP SCHEMA
-- ============================================================================
-- Simplified schema for proof of concept (Ocean FCL only)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- CUSTOMERS
-- ----------------------------------------------------------------------------
CREATE TABLE customers (
    id INT IDENTITY(1,1) PRIMARY KEY,
    code NVARCHAR(20) NOT NULL UNIQUE,
    name NVARCHAR(255) NOT NULL,
    email NVARCHAR(255),
    phone NVARCHAR(50),
    address NVARCHAR(500),
    city NVARCHAR(100),
    country NVARCHAR(100),
    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE()
);

-- ----------------------------------------------------------------------------
-- USERS (extends Django auth_user)
-- ----------------------------------------------------------------------------
CREATE TABLE user_profiles (
    id INT IDENTITY(1,1) PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,          -- FK to Django auth_user
    customer_id INT,                       -- NULL = internal staff
    role NVARCHAR(20) DEFAULT 'USER',     -- 'ADMIN', 'USER'
    phone NVARCHAR(50),
    created_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (customer_id) REFERENCES customers(id)
);

-- ----------------------------------------------------------------------------
-- LOCATIONS (Ports - simplified)
-- ----------------------------------------------------------------------------
CREATE TABLE locations (
    id INT IDENTITY(1,1) PRIMARY KEY,
    code NVARCHAR(10) NOT NULL UNIQUE,    -- UN/LOCODE
    name NVARCHAR(255) NOT NULL,
    country NVARCHAR(100),
    is_active BIT DEFAULT 1
);

-- Sample ports
INSERT INTO locations (code, name, country) VALUES
('CNSHA', 'Shanghai', 'China'),
('CNSHE', 'Shenzhen', 'China'),
('CNNGB', 'Ningbo', 'China'),
('USLAX', 'Los Angeles', 'United States'),
('USNYC', 'New York', 'United States'),
('NLRTM', 'Rotterdam', 'Netherlands'),
('DEHAM', 'Hamburg', 'Germany'),
('SGSIN', 'Singapore', 'Singapore');

-- ----------------------------------------------------------------------------
-- CONTAINER TYPES (simplified)
-- ----------------------------------------------------------------------------
CREATE TABLE container_types (
    id INT IDENTITY(1,1) PRIMARY KEY,
    code NVARCHAR(10) NOT NULL UNIQUE,
    name NVARCHAR(50) NOT NULL,
    size_ft INT NOT NULL
);

-- Standard container types
INSERT INTO container_types (code, name, size_ft) VALUES
('20GP', '20ft General Purpose', 20),
('40GP', '40ft General Purpose', 40),
('40HC', '40ft High Cube', 40),
('20RF', '20ft Reefer', 20),
('40RF', '40ft Reefer', 40);

-- ----------------------------------------------------------------------------
-- BOOKINGS (Ocean FCL only for MVP)
-- ----------------------------------------------------------------------------
CREATE TABLE bookings (
    id INT IDENTITY(1,1) PRIMARY KEY,
    booking_number NVARCHAR(20) NOT NULL UNIQUE,

    -- Customer
    customer_id INT NOT NULL,
    created_by_user_id INT NOT NULL,

    -- Route
    origin_port_id INT NOT NULL,
    destination_port_id INT NOT NULL,

    -- Dates
    cargo_ready_date DATE NOT NULL,

    -- Container
    container_type_id INT NOT NULL,
    container_count INT NOT NULL DEFAULT 1,

    -- Status
    status NVARCHAR(20) NOT NULL DEFAULT 'DRAFT',
    -- DRAFT, SUBMITTED, CONFIRMED, CANCELLED

    -- Notes
    special_instructions NVARCHAR(MAX),

    -- Carrier info (filled by ops)
    carrier_name NVARCHAR(100),
    vessel_name NVARCHAR(100),
    voyage_number NVARCHAR(50),
    etd DATE,
    eta DATE,

    -- Timestamps
    submitted_at DATETIME2,
    confirmed_at DATETIME2,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (customer_id) REFERENCES customers(id),
    FOREIGN KEY (origin_port_id) REFERENCES locations(id),
    FOREIGN KEY (destination_port_id) REFERENCES locations(id),
    FOREIGN KEY (container_type_id) REFERENCES container_types(id)
);

-- Index for customer's booking list
CREATE INDEX idx_bookings_customer ON bookings(customer_id, created_at DESC);
CREATE INDEX idx_bookings_status ON bookings(status);

-- ----------------------------------------------------------------------------
-- BOOKING ITEMS (Cargo)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_items (
    id INT IDENTITY(1,1) PRIMARY KEY,
    booking_id INT NOT NULL,

    description NVARCHAR(500) NOT NULL,
    package_type NVARCHAR(50),            -- 'PALLET', 'CARTON', etc.
    quantity INT NOT NULL,
    weight_kg DECIMAL(10, 2) NOT NULL,

    created_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

CREATE INDEX idx_booking_items_booking ON booking_items(booking_id);

-- ----------------------------------------------------------------------------
-- BOOKING DOCUMENTS (simple file references)
-- ----------------------------------------------------------------------------
CREATE TABLE booking_documents (
    id INT IDENTITY(1,1) PRIMARY KEY,
    booking_id INT NOT NULL,

    file_name NVARCHAR(255) NOT NULL,
    file_path NVARCHAR(500) NOT NULL,     -- Local path for MVP
    document_type NVARCHAR(50),           -- 'INVOICE', 'PACKING_LIST', 'OTHER'

    uploaded_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);

-- ----------------------------------------------------------------------------
-- BOOKING NUMBER SEQUENCE
-- ----------------------------------------------------------------------------
-- Generate booking numbers: BK-YYYYMM-NNNN
CREATE SEQUENCE booking_number_seq START WITH 1 INCREMENT BY 1;
