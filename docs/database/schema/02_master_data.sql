-- ============================================================================
-- FREIGHT BOOKING SYSTEM - MASTER DATA TABLES
-- ============================================================================
-- Reference data: Locations, Carriers, Commodities, Container Types
-- ============================================================================

-- ----------------------------------------------------------------------------
-- LOCATIONS TABLE
-- ----------------------------------------------------------------------------
-- Ports, airports, rail terminals, warehouses (UN/LOCODE compliant)
-- ----------------------------------------------------------------------------
CREATE TABLE locations (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(10) NOT NULL,                 -- UN/LOCODE or airport code
    name NVARCHAR(255) NOT NULL,
    location_type NVARCHAR(20) NOT NULL,        -- 'SEAPORT', 'AIRPORT', 'RAIL_TERMINAL', 'WAREHOUSE', 'ADDRESS'

    -- Geographic Information
    city NVARCHAR(100),
    state_province NVARCHAR(100),
    country_code CHAR(2) NOT NULL,              -- ISO 3166-1 alpha-2
    country_name NVARCHAR(100),
    region NVARCHAR(50),                        -- 'ASIA', 'EUROPE', 'NAMERICA', etc.

    -- Coordinates
    latitude DECIMAL(10, 7),
    longitude DECIMAL(10, 7),
    timezone NVARCHAR(50),

    -- Capabilities
    handles_ocean BIT DEFAULT 0,
    handles_air BIT DEFAULT 0,
    handles_road BIT DEFAULT 0,
    handles_rail BIT DEFAULT 0,

    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE()
);

-- Indexes
CREATE UNIQUE INDEX idx_locations_code_type ON locations(code, location_type);
CREATE INDEX idx_locations_country ON locations(country_code);
CREATE INDEX idx_locations_type ON locations(location_type);
CREATE INDEX idx_locations_name ON locations(name);


-- ----------------------------------------------------------------------------
-- CARRIERS TABLE
-- ----------------------------------------------------------------------------
-- Shipping lines, airlines, trucking companies
-- ----------------------------------------------------------------------------
CREATE TABLE carriers (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(10) NOT NULL,                 -- SCAC code for ocean, IATA for air
    name NVARCHAR(255) NOT NULL,
    carrier_type NVARCHAR(20) NOT NULL,         -- 'OCEAN', 'AIR', 'ROAD', 'RAIL'

    -- Contact Information
    email NVARCHAR(255),
    phone NVARCHAR(50),
    website NVARCHAR(255),

    -- Address
    address NVARCHAR(500),
    country_code CHAR(2),

    -- EDI Configuration
    edi_partner_id UNIQUEIDENTIFIER,            -- FK to edi_partners (created in 06_edi_tables.sql)

    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE()
);

-- Indexes
CREATE UNIQUE INDEX idx_carriers_code_type ON carriers(code, carrier_type);
CREATE INDEX idx_carriers_type ON carriers(carrier_type);


-- ----------------------------------------------------------------------------
-- CONTAINER TYPES TABLE
-- ----------------------------------------------------------------------------
-- Standard container specifications (20GP, 40HC, etc.)
-- ----------------------------------------------------------------------------
CREATE TABLE container_types (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(10) NOT NULL UNIQUE,          -- '20GP', '40GP', '40HC', '20RF', etc.
    name NVARCHAR(100) NOT NULL,
    size_ft INT NOT NULL,                       -- 20, 40, 45
    type_category NVARCHAR(20) NOT NULL,        -- 'DRY', 'REEFER', 'OPEN_TOP', 'FLAT_RACK', 'TANK'

    -- Internal Dimensions (meters)
    length_m DECIMAL(5, 2),
    width_m DECIMAL(5, 2),
    height_m DECIMAL(5, 2),

    -- Capacity
    max_weight_kg DECIMAL(10, 2),
    tare_weight_kg DECIMAL(10, 2),
    cubic_capacity_m3 DECIMAL(8, 2),

    is_active BIT DEFAULT 1
);


-- ----------------------------------------------------------------------------
-- COMMODITIES TABLE
-- ----------------------------------------------------------------------------
-- HS codes, dangerous goods classifications
-- ----------------------------------------------------------------------------
CREATE TABLE commodities (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    hs_code NVARCHAR(10),                       -- Harmonized System code
    name NVARCHAR(255) NOT NULL,
    description NVARCHAR(MAX),

    -- Classification
    category NVARCHAR(100),
    sub_category NVARCHAR(100),

    -- Dangerous Goods
    is_dangerous BIT DEFAULT 0,
    un_number NVARCHAR(10),                     -- UN dangerous goods number
    dg_class NVARCHAR(10),                      -- IMO class (1.1, 2.1, 3, etc.)
    packing_group NVARCHAR(5),                  -- I, II, III

    -- Special Requirements
    requires_temperature_control BIT DEFAULT 0,
    min_temp_celsius DECIMAL(5, 2),
    max_temp_celsius DECIMAL(5, 2),
    requires_special_handling BIT DEFAULT 0,
    handling_instructions NVARCHAR(MAX),

    is_active BIT DEFAULT 1,
    created_at DATETIME2 DEFAULT GETUTCDATE()
);

-- Indexes
CREATE INDEX idx_commodities_hs_code ON commodities(hs_code);
CREATE INDEX idx_commodities_dangerous ON commodities(is_dangerous) WHERE is_dangerous = 1;


-- ----------------------------------------------------------------------------
-- INCOTERMS TABLE
-- ----------------------------------------------------------------------------
-- International Commercial Terms (ICC standard)
-- ----------------------------------------------------------------------------
CREATE TABLE incoterms (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(10) NOT NULL UNIQUE,          -- 'FOB', 'CIF', 'EXW', etc.
    name NVARCHAR(100) NOT NULL,
    description NVARCHAR(MAX),

    -- Applicability
    applies_to_ocean BIT DEFAULT 1,
    applies_to_air BIT DEFAULT 1,
    applies_to_road BIT DEFAULT 1,

    -- Risk & Cost Transfer Points
    risk_transfer_point NVARCHAR(255),
    cost_transfer_point NVARCHAR(255),

    -- Version
    version_year INT DEFAULT 2020,              -- Incoterms 2020

    is_active BIT DEFAULT 1
);

-- Insert standard Incoterms 2020
INSERT INTO incoterms (id, code, name, applies_to_ocean, applies_to_air, applies_to_road) VALUES
(NEWID(), 'EXW', 'Ex Works', 1, 1, 1),
(NEWID(), 'FCA', 'Free Carrier', 1, 1, 1),
(NEWID(), 'CPT', 'Carriage Paid To', 1, 1, 1),
(NEWID(), 'CIP', 'Carriage and Insurance Paid To', 1, 1, 1),
(NEWID(), 'DAP', 'Delivered at Place', 1, 1, 1),
(NEWID(), 'DPU', 'Delivered at Place Unloaded', 1, 1, 1),
(NEWID(), 'DDP', 'Delivered Duty Paid', 1, 1, 1),
(NEWID(), 'FAS', 'Free Alongside Ship', 1, 0, 0),
(NEWID(), 'FOB', 'Free on Board', 1, 0, 0),
(NEWID(), 'CFR', 'Cost and Freight', 1, 0, 0),
(NEWID(), 'CIF', 'Cost, Insurance and Freight', 1, 0, 0);


-- ----------------------------------------------------------------------------
-- PACKAGE TYPES TABLE
-- ----------------------------------------------------------------------------
-- Standard packaging types for cargo
-- ----------------------------------------------------------------------------
CREATE TABLE package_types (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    code NVARCHAR(10) NOT NULL UNIQUE,          -- 'PLT', 'CTN', 'DRM', etc.
    name NVARCHAR(100) NOT NULL,
    description NVARCHAR(255),

    is_active BIT DEFAULT 1
);

-- Insert common package types
INSERT INTO package_types (id, code, name) VALUES
(NEWID(), 'PLT', 'Pallet'),
(NEWID(), 'CTN', 'Carton'),
(NEWID(), 'CRT', 'Crate'),
(NEWID(), 'DRM', 'Drum'),
(NEWID(), 'BAG', 'Bag'),
(NEWID(), 'BDL', 'Bundle'),
(NEWID(), 'ROL', 'Roll'),
(NEWID(), 'PKG', 'Package'),
(NEWID(), 'PCS', 'Pieces'),
(NEWID(), 'SKD', 'Skid');
