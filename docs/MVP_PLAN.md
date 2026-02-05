# MVP Implementation Plan

## Goal

Build a working proof of concept in 4 weeks for management approval.

## Scope Comparison

| Feature | MVP | Full System |
|---------|-----|-------------|
| Transport Modes | Ocean FCL only | FCL, LCL, Air, Road |
| Booking Workflow | Draft → Submit → Confirm | Multi-step approval |
| Carrier Integration | Manual (email) | EDI X12 automated |
| Users | Customer + Admin | Roles, permissions |
| Documents | Basic upload | Versioning, types |
| Notifications | Console/basic email | Templates, queue |
| Reporting | None | Dashboards |

## MVP Features

### Week 1: Foundation
- [ ] Django project setup
- [ ] SQL Server connection
- [ ] Customer model
- [ ] User authentication (Django built-in)
- [ ] Basic admin panel

### Week 2: Booking Core
- [ ] Locations model (pre-populated ports)
- [ ] Container types model
- [ ] Booking model
- [ ] Booking items model
- [ ] API endpoints (CRUD)
- [ ] Submit booking action

### Week 3: Frontend
- [ ] React project setup
- [ ] Login page
- [ ] Booking list page
- [ ] Create booking form
- [ ] Booking detail view
- [ ] Basic styling

### Week 4: Polish & Demo
- [ ] Bug fixes
- [ ] Test data
- [ ] Demo script
- [ ] User guide (1 page)
- [ ] Management presentation

## Success Criteria

1. Customer can log in
2. Customer can create a booking with cargo items
3. Customer can submit booking
4. Admin can see submitted bookings
5. Admin can confirm/cancel bookings
6. Customer sees status updates

## Demo Script

### Scenario 1: Customer Creates Booking (3 min)
1. Open browser → Login page
2. Enter credentials → Dashboard
3. Click "New Booking"
4. Select: Shanghai → Los Angeles
5. Pick: 2x 40HC containers
6. Cargo ready: Feb 15
7. Add cargo: "Electronics, 100 cartons, 500kg"
8. Click "Submit"
9. See confirmation message

### Scenario 2: Operations Confirms (2 min)
1. Login as admin
2. View "Pending Bookings"
3. Open booking details
4. Enter vessel: "EVER GIVEN", voyage: "024W"
5. Enter ETD/ETA
6. Click "Confirm"
7. Customer receives notification

## Technical Decisions (MVP)

| Decision | MVP Choice | Why |
|----------|------------|-----|
| Auth | Django sessions | Simpler, works out of box |
| File storage | Local disk | No Azure setup needed |
| Email | Console output | No SMTP config needed |
| Frontend | Create React App | Quick setup |
| Styling | Bootstrap or Tailwind | Fast, looks decent |

## Post-MVP Roadmap

### Phase 2 (If approved)
- Add LCL, Air, Road modes
- Approval workflows
- JWT authentication
- Azure Blob storage

### Phase 3
- EDI X12 integration
- Advanced reporting
- Mobile responsive
- Performance optimization

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| SQL Server issues | Docker image as backup |
| Time pressure | Cut frontend features first |
| Scope creep | Strict "MVP only" rule |

## Team Needs

- 1 Backend developer (Python/Django)
- 1 Frontend developer (React)
- 0.5 QA/Tester
- Project manager oversight

## Deliverables

1. Working web application
2. Database with test data
3. 1-page user guide
4. Demo video (optional)
5. This documentation
