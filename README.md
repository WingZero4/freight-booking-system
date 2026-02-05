# Freight Booking Management System

A B2B web-based booking management system for freight forwarding operations. Allows customers (shippers) to submit multi-modal freight bookings with configurable approval workflows and EDI ANSI X12 carrier integration.

## Features

- **Multi-Modal Booking Support**: Ocean FCL, Ocean LCL, Air Freight, Road/Trucking
- **Customer Portal**: Self-service booking submission for shippers
- **Configurable Workflows**: Customer-specific approval rules
- **EDI Integration**: ANSI X12 standard (300, 301, 204, 990, 214, 210, 997)
- **Document Management**: Azure Blob storage with version control
- **Email Notifications**: Automated status updates
- **Audit Trail**: Complete change history

## Technology Stack

| Component | Technology |
|-----------|------------|
| Backend | Python 3.11+ / Django 4.2+ / Django REST Framework |
| Database | SQL Server |
| Frontend | React 18+ with TypeScript |
| Auth | JWT (djangorestframework-simplejwt) |
| Task Queue | Celery + Redis |
| File Storage | Azure Blob Storage |
| Email | SMTP (SendGrid/AWS SES) |
| EDI | ANSI X12 via AS2/SFTP |

## Project Structure

```
freight-booking-system/
├── backend/
│   ├── config/                 # Django settings
│   ├── apps/
│   │   ├── core/              # Base models, utilities
│   │   ├── accounts/          # Users, customers
│   │   ├── bookings/          # Booking management
│   │   ├── workflows/         # Approval engine
│   │   ├── notifications/     # Email service
│   │   ├── master_data/       # Reference data
│   │   ├── documents/         # File storage
│   │   ├── audit/             # Audit trail
│   │   └── edi/               # EDI X12 processing
│   └── api/v1/                # API endpoints
├── frontend/                   # React application
├── docs/                       # Documentation
│   ├── api/                   # API specifications
│   ├── database/              # Schema scripts
│   └── edi/                   # EDI specifications
└── scripts/                    # Utility scripts
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- SQL Server (or Docker)
- Redis
- ODBC Driver 17 for SQL Server

### Backend Setup

```bash
cd backend
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements/development.txt

# Configure environment
cp .env.example .env
# Edit .env with your settings

# Run migrations
python manage.py migrate

# Create superuser
python manage.py createsuperuser

# Start development server
python manage.py runserver
```

### Frontend Setup

```bash
cd frontend
npm install
npm start
```

### Running Celery (for background tasks)

```bash
celery -A config worker -l info
celery -A config beat -l info
```

## Documentation

- [API Documentation](docs/api/README.md)
- [Database Schema](docs/database/README.md)
- [EDI Specifications](docs/edi/README.md)
- [Deployment Guide](docs/deployment.md)

## Environment Variables

See `.env.example` for required configuration.

## License

Proprietary - All rights reserved.
