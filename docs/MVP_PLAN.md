# MVP Implementation Plan

## Goal

Build a working proof of concept in **1 week** for management approval.

## 1-Week Sprint Schedule

| Day | Focus | Deliverables |
|-----|-------|--------------|
| **Day 1** | Backend Setup | Django project, models, SQLite, Django Admin |
| **Day 2** | API & Logic | Booking CRUD, submit action, status flow |
| **Day 3** | Customer UI | Login, booking form, list view (Django templates) |
| **Day 4** | Integration | Connect UI to API, test flows, fix bugs |
| **Day 5** | Demo Ready | Test data, demo script, walkthrough |

## Shortcuts for Speed

| Normal Approach | 1-Week Shortcut |
|-----------------|-----------------|
| React frontend | Django templates + Bootstrap |
| Custom admin UI | Django Admin (built-in) |
| SQL Server | SQLite (zero config) |
| JWT auth | Django session auth |
| Email service | Console output / skip |
| File uploads | Skip for demo |
| Unit tests | Manual testing only |

## Scope

| Feature | Included | Excluded |
|---------|----------|----------|
| Customer login | Yes | Registration |
| Create booking | Yes | Edit booking |
| Add cargo items | Yes | Multiple items UI |
| Submit booking | Yes | Cancel booking |
| Admin confirms | Yes (Django Admin) | Custom admin UI |
| Status tracking | Yes | Email notifications |

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
