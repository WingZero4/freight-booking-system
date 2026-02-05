-- ============================================================================
-- FREIGHT BOOKING SYSTEM - ADDITIONAL INDEXES
-- ============================================================================
-- Performance indexes for common query patterns
-- ============================================================================

-- ----------------------------------------------------------------------------
-- COMPOSITE INDEXES FOR COMMON QUERIES
-- ----------------------------------------------------------------------------

-- Booking list with status filter (customer portal)
CREATE INDEX idx_bookings_customer_status_date
ON bookings(customer_id, status, created_at DESC)
INCLUDE (booking_number, transport_mode, origin_location_id, destination_location_id);

-- Pending approvals dashboard
CREATE INDEX idx_approvals_pending_user
ON booking_approvals(assigned_to_user_id, status, assigned_at)
INCLUDE (booking_id, step_order)
WHERE status = 'PENDING';

-- EDI processing queue
CREATE INDEX idx_edi_outbound_processing
ON edi_outbound_queue(status, scheduled_at, edi_partner_id)
INCLUDE (booking_id, transaction_type)
WHERE status IN ('PENDING', 'RETRY');

-- Booking search by date range
CREATE INDEX idx_bookings_date_range
ON bookings(cargo_ready_date, status)
INCLUDE (booking_number, customer_id, transport_mode);

-- Container tracking by number
CREATE INDEX idx_containers_tracking
ON booking_containers(container_number)
INCLUDE (booking_id, container_type_id, cargo_weight_kg)
WHERE container_number IS NOT NULL;

-- Notification processing
CREATE INDEX idx_notifications_processing
ON notifications(status, scheduled_for, retry_count)
INCLUDE (recipient_email, template_code)
WHERE status IN ('PENDING', 'RETRY');


-- ----------------------------------------------------------------------------
-- FILTERED INDEXES FOR ACTIVE RECORDS
-- ----------------------------------------------------------------------------

-- Active customers only
CREATE INDEX idx_customers_active_name
ON customers(name)
WHERE is_active = 1;

-- Active carriers by type
CREATE INDEX idx_carriers_active_type
ON carriers(carrier_type, name)
WHERE is_active = 1;

-- Active workflow configs
CREATE INDEX idx_workflows_active_customer
ON workflow_configs(customer_id, priority)
WHERE is_active = 1;


-- ----------------------------------------------------------------------------
-- FULL-TEXT SEARCH INDEXES (Optional - uncomment if needed)
-- ----------------------------------------------------------------------------

-- CREATE FULLTEXT CATALOG BookingCatalog AS DEFAULT;

-- CREATE FULLTEXT INDEX ON bookings(special_instructions, internal_notes)
-- KEY INDEX PK_bookings ON BookingCatalog;

-- CREATE FULLTEXT INDEX ON booking_items(commodity_description, marks_and_numbers)
-- KEY INDEX PK_booking_items ON BookingCatalog;


-- ----------------------------------------------------------------------------
-- STATISTICS UPDATE (Run periodically)
-- ----------------------------------------------------------------------------

-- UPDATE STATISTICS bookings;
-- UPDATE STATISTICS booking_items;
-- UPDATE STATISTICS booking_approvals;
-- UPDATE STATISTICS edi_transactions;
