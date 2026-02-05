-- ============================================================================
-- FREIGHT BOOKING SYSTEM - MODAL-SPECIFIC TABLES
-- ============================================================================
-- Ocean FCL, Ocean LCL, Air Freight, Road/Trucking details
-- Uses composition pattern (OneToOne relationship with bookings)
-- ============================================================================

-- ----------------------------------------------------------------------------
-- OCEAN FCL BOOKING DETAILS
-- ----------------------------------------------------------------------------
-- Full Container Load specific information
-- ----------------------------------------------------------------------------
CREATE TABLE booking_ocean_fcl (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL UNIQUE,

    -- Service Type
    service_type NVARCHAR(20) DEFAULT 'CY-CY',   -- 'CY-CY', 'CY-CFS', 'CFS-CY', 'CFS-CFS'
    service_name NVARCHAR(100),                  -- Carrier service name

    -- Vessel Details
    vessel_name NVARCHAR(100),
    voyage_number NVARCHAR(50),
    vessel_flag CHAR(2),                         -- Country code
    vessel_imo NVARCHAR(20),                     -- IMO number

    -- Port Details
    port_of_loading_id UNIQUEIDENTIFIER,
    port_of_discharge_id UNIQUEIDENTIFIER,
    place_of_receipt NVARCHAR(255),              -- Inland origin
    place_of_delivery NVARCHAR(255),             -- Final destination (inland)

    -- Terminal Details
    loading_terminal NVARCHAR(255),
    discharge_terminal NVARCHAR(255),

    -- Cutoff Dates
    documentation_cutoff DATETIME2,
    cargo_cutoff DATETIME2,
    vgm_cutoff DATETIME2,

    -- Transshipment
    is_transshipment BIT DEFAULT 0,
    transshipment_port_id UNIQUEIDENTIFIER,

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (port_of_loading_id) REFERENCES locations(id),
    FOREIGN KEY (port_of_discharge_id) REFERENCES locations(id),
    FOREIGN KEY (transshipment_port_id) REFERENCES locations(id)
);


-- ----------------------------------------------------------------------------
-- BOOKING CONTAINERS TABLE
-- ----------------------------------------------------------------------------
-- Container details for Ocean FCL bookings
-- ----------------------------------------------------------------------------
CREATE TABLE booking_containers (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL,

    container_type_id UNIQUEIDENTIFIER NOT NULL,
    quantity INT NOT NULL DEFAULT 1,

    -- Container Assignment (when known)
    container_number NVARCHAR(20),               -- e.g., 'MSKU1234567'
    seal_number NVARCHAR(50),

    -- Weights
    cargo_weight_kg DECIMAL(10, 2),
    vgm_weight_kg DECIMAL(10, 2),                -- Verified Gross Mass
    vgm_verified_at DATETIME2,
    vgm_method NVARCHAR(20),                     -- 'METHOD_1', 'METHOD_2'
    vgm_authorized_person NVARCHAR(100),

    -- Reefer Settings (for refrigerated containers)
    set_temperature_c DECIMAL(5, 2),
    ventilation_setting NVARCHAR(50),
    humidity_setting NVARCHAR(50),
    atmosphere_setting NVARCHAR(50),             -- For controlled atmosphere

    -- Special Equipment
    is_soc BIT DEFAULT 0,                        -- Shipper Owned Container
    is_oog BIT DEFAULT 0,                        -- Out of Gauge
    oog_height_cm DECIMAL(10, 2),
    oog_width_cm DECIMAL(10, 2),
    oog_length_cm DECIMAL(10, 2),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (container_type_id) REFERENCES container_types(id)
);

-- Indexes
CREATE INDEX idx_booking_containers_booking ON booking_containers(booking_id);
CREATE INDEX idx_booking_containers_number ON booking_containers(container_number) WHERE container_number IS NOT NULL;


-- ----------------------------------------------------------------------------
-- OCEAN LCL BOOKING DETAILS
-- ----------------------------------------------------------------------------
-- Less than Container Load specific information
-- ----------------------------------------------------------------------------
CREATE TABLE booking_ocean_lcl (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL UNIQUE,

    -- Service Type (always CFS for LCL)
    service_type NVARCHAR(20) DEFAULT 'CFS-CFS',

    -- Vessel Details
    vessel_name NVARCHAR(100),
    voyage_number NVARCHAR(50),

    -- Port Details
    port_of_loading_id UNIQUEIDENTIFIER,
    port_of_discharge_id UNIQUEIDENTIFIER,

    -- Consolidation Details
    origin_cfs_id UNIQUEIDENTIFIER,              -- Origin Container Freight Station
    destination_cfs_id UNIQUEIDENTIFIER,         -- Destination CFS

    -- Cutoff Dates
    cargo_cutoff DATETIME2,
    documentation_cutoff DATETIME2,

    -- Consolidation Info
    consolidation_number NVARCHAR(50),
    master_bl_number NVARCHAR(50),
    house_bl_number NVARCHAR(50),

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (port_of_loading_id) REFERENCES locations(id),
    FOREIGN KEY (port_of_discharge_id) REFERENCES locations(id),
    FOREIGN KEY (origin_cfs_id) REFERENCES locations(id),
    FOREIGN KEY (destination_cfs_id) REFERENCES locations(id)
);


-- ----------------------------------------------------------------------------
-- AIR FREIGHT BOOKING DETAILS
-- ----------------------------------------------------------------------------
-- Air cargo specific information
-- ----------------------------------------------------------------------------
CREATE TABLE booking_air (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL UNIQUE,

    -- Flight Details
    flight_number NVARCHAR(20),
    aircraft_type NVARCHAR(50),

    -- Airports
    airport_of_departure_id UNIQUEIDENTIFIER,
    airport_of_arrival_id UNIQUEIDENTIFIER,

    -- Service Level
    service_level NVARCHAR(50),                  -- 'STANDARD', 'EXPRESS', 'DEFERRED', 'CHARTER'

    -- Air Waybill Numbers
    mawb_number NVARCHAR(20),                    -- Master Air Waybill (airline's)
    hawb_number NVARCHAR(20),                    -- House Air Waybill (forwarder's)

    -- Weight Calculations
    actual_weight_kg DECIMAL(12, 3),
    volume_weight_kg DECIMAL(12, 3),             -- Dimensional weight
    chargeable_weight_kg DECIMAL(12, 3),         -- Max of actual/volume

    -- Special Cargo Types
    is_perishable BIT DEFAULT 0,
    is_valuable BIT DEFAULT 0,
    is_live_animal BIT DEFAULT 0,
    is_human_remains BIT DEFAULT 0,
    is_diplomatic BIT DEFAULT 0,

    -- Time-Critical
    is_time_critical BIT DEFAULT 0,
    time_critical_by DATETIME2,

    -- ULD (Unit Load Device) Info
    uld_type NVARCHAR(20),
    uld_count INT,

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE,
    FOREIGN KEY (airport_of_departure_id) REFERENCES locations(id),
    FOREIGN KEY (airport_of_arrival_id) REFERENCES locations(id)
);


-- ----------------------------------------------------------------------------
-- ROAD/TRUCKING BOOKING DETAILS
-- ----------------------------------------------------------------------------
-- Ground transportation specific information
-- ----------------------------------------------------------------------------
CREATE TABLE booking_road (
    id UNIQUEIDENTIFIER PRIMARY KEY DEFAULT NEWID(),
    booking_id UNIQUEIDENTIFIER NOT NULL UNIQUE,

    -- Vehicle Type
    vehicle_type NVARCHAR(50),                   -- 'FTL', 'LTL', 'FLATBED', 'REEFER', 'TANKER', 'DRY_VAN'
    vehicle_count INT DEFAULT 1,

    -- Pickup Details
    pickup_address NVARCHAR(500),
    pickup_city NVARCHAR(100),
    pickup_state NVARCHAR(100),
    pickup_postal_code NVARCHAR(20),
    pickup_country_code CHAR(2),
    pickup_contact_name NVARCHAR(100),
    pickup_contact_phone NVARCHAR(50),
    pickup_contact_email NVARCHAR(255),
    pickup_instructions NVARCHAR(MAX),

    -- Pickup Schedule
    pickup_window_start DATETIME2,
    pickup_window_end DATETIME2,
    pickup_appointment_required BIT DEFAULT 0,
    pickup_reference NVARCHAR(100),              -- PO number, dock number, etc.

    -- Delivery Details
    delivery_address NVARCHAR(500),
    delivery_city NVARCHAR(100),
    delivery_state NVARCHAR(100),
    delivery_postal_code NVARCHAR(20),
    delivery_country_code CHAR(2),
    delivery_contact_name NVARCHAR(100),
    delivery_contact_phone NVARCHAR(50),
    delivery_contact_email NVARCHAR(255),
    delivery_instructions NVARCHAR(MAX),

    -- Delivery Schedule
    delivery_window_start DATETIME2,
    delivery_window_end DATETIME2,
    delivery_appointment_required BIT DEFAULT 0,
    delivery_reference NVARCHAR(100),

    -- Driver Info (when assigned)
    driver_name NVARCHAR(100),
    driver_phone NVARCHAR(50),
    driver_license NVARCHAR(50),
    truck_number NVARCHAR(50),
    trailer_number NVARCHAR(50),

    -- Tracking
    tracking_url NVARCHAR(500),
    gps_enabled BIT DEFAULT 0,

    -- Special Requirements
    liftgate_required BIT DEFAULT 0,
    inside_delivery BIT DEFAULT 0,
    residential_delivery BIT DEFAULT 0,
    team_drivers_required BIT DEFAULT 0,

    created_at DATETIME2 DEFAULT GETUTCDATE(),
    updated_at DATETIME2 DEFAULT GETUTCDATE(),

    FOREIGN KEY (booking_id) REFERENCES bookings(id) ON DELETE CASCADE
);
