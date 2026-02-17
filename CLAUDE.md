# Claude Code Instructions

## Session Recovery After Compaction
**After every context compaction (or session continuation), ALWAYS re-read these files before continuing work:**
- `C:\Users\micha\.claude\projects\C--Users-micha\memory\MEMORY.md` (persistent memory)
- `C:\Users\micha\freight-booking-system\CLAUDE.md` (this file)
- Any active plan file referenced in system messages
This prevents loss of context, project rules, and review process requirements.

## Project Status: Production-Ready
- All development phases complete, deployed and live on PythonAnywhere
- 394 automated tests, REST API, PDF generation, email notifications, rate limiting
- Remaining: PostgreSQL migration (optional, SQLite fine for current scale)

## Mandatory Pre-Commit Review Process

**Before every commit and deploy, ALL 6 review agents must run in parallel and any issues found must be fixed:**

1. **Code Architect** — Reviews models, views, forms, services, admin, URLs, settings for bugs, import errors, logic issues, N+1 queries, Django compatibility
2. **Template Specialist** — Reviews all templates for undefined context variables, broken URL tags, missing form fields, broken Bootstrap grid, missing CSRF tokens, conditional logic errors
3. **QA Tester** — Traces all critical user flows (customer + staff) for functional bugs, permission issues, status transition errors, data loss
4. **Security Reviewer** — Checks authorization, input validation, CSRF, data exposure (contract numbers hidden from customers), file upload security, settings hardening
5. **Migration & Consistency Checker** — Verifies model fields match migrations, admin fieldsets match model, form fields match model, views reference valid fields
6. **Systems Workflow Specialist** — Traces end-to-end integration dispatch chains (BookingService → carrier_dispatch/dispatch → adapters → callbacks → FMS push), verifies cross-module data contracts (serializer output matches adapter input), status state machine consistency across all modules, error propagation and recovery paths, background thread safety, webhook/callback wiring, and retry/recovery mechanisms

**Workflow:**
- Launch all 6 agents in parallel after code changes are complete
- Consolidate findings, filter false positives
- Fix all confirmed bugs
- Run `python manage.py check` to verify no Django errors
- Only then commit and deploy

## Project Context

- **Stack**: Python 3.14, Django 6.0.2, SQLite, Bootstrap 5, Jazzmin admin
- **Branch**: version-3 (active development)
- **Service layer**: All state transitions must go through `BookingService`, not model methods directly
- **Model methods**: Raise `ValueError` on invalid status (consistent API)
- **Context processor**: `bookings.context_processors.nav_active` handles nav highlighting
- **Internal fields**: `contract_number` must NEVER be visible to customers (templates, CSV, API)

## Deployment

- PythonAnywhere: username `wingzero4` (paths case-sensitive: `/home/WingZero4/`)
- Deploy: `cd ~/freight-booking-system/backend && git pull origin version-3 && source ~/.virtualenvs/freight-env/bin/activate && python manage.py migrate`
- Reload: `curl -s -X POST "https://www.pythonanywhere.com/api/v0/user/wingzero4/webapps/wingzero4.pythonanywhere.com/reload/" -H "Authorization: Token d5b67d6bdf60104fa8f697794678cb9d75dd4717"`
