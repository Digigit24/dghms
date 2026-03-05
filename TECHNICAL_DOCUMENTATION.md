# DigiHMS - Hospital Management System

## Technical Documentation

**Version:** 2.0 (SuperAdmin Integration)
**Date:** March 2026
**Classification:** Internal Technical Reference

---

<a id="table-of-contents"></a>

## Table of Contents

1. [Project Overview](#1-project-overview)
   - 1.1 [Purpose & Problem Statement](#11-purpose--problem-statement)
   - 1.2 [Target Users](#12-target-users)
   - 1.3 [Key Design Decisions](#13-key-design-decisions)
2. [System Architecture](#2-system-architecture)
   - 2.1 [High-Level Architecture](#21-high-level-architecture)
   - 2.2 [Satellite Application Pattern](#22-satellite-application-pattern)
   - 2.3 [Multi-Tenancy Architecture](#23-multi-tenancy-architecture)
   - 2.4 [Authentication & Authorization Flow](#24-authentication--authorization-flow)
3. [Technology Stack](#3-technology-stack)
   - 3.1 [Core Technologies](#31-core-technologies)
   - 3.2 [Third-Party Libraries](#32-third-party-libraries)
   - 3.3 [External Integrations](#33-external-integrations)
4. [Project Structure](#4-project-structure)
   - 4.1 [Directory Layout](#41-directory-layout)
   - 4.2 [Key File Descriptions](#42-key-file-descriptions)
5. [Core Modules / Components](#5-core-modules--components)
   - 5.1 [Common Module](#51-common-module)
   - 5.2 [Patients Module](#52-patients-module)
   - 5.3 [Doctors Module](#53-doctors-module)
   - 5.4 [Appointments Module](#54-appointments-module)
   - 5.5 [OPD Module](#55-opd-module)
   - 5.6 [IPD Module](#56-ipd-module)
   - 5.7 [Pharmacy Module](#57-pharmacy-module)
   - 5.8 [Diagnostics Module](#58-diagnostics-module)
   - 5.9 [Orders & Payments Module](#59-orders--payments-module)
   - 5.10 [Services Module](#510-services-module)
   - 5.11 [Panchakarma Module](#511-panchakarma-module)
   - 5.12 [Hospital Configuration Module](#512-hospital-configuration-module)
   - 5.13 [External API Modules](#513-external-api-modules)
6. [Key Functionalities](#6-key-functionalities)
7. [API / Service Layer](#7-api--service-layer)
   - 7.1 [API Endpoint Reference](#71-api-endpoint-reference)
   - 7.2 [Authentication Endpoints](#72-authentication-endpoints)
   - 7.3 [Public Endpoints](#73-public-endpoints)
8. [Database Design](#8-database-design)
   - 8.1 [Entity Relationship Overview](#81-entity-relationship-overview)
   - 8.2 [Core Models Reference](#82-core-models-reference)
   - 8.3 [Naming Conventions](#83-naming-conventions)
9. [Application Flow](#9-application-flow)
   - 9.1 [API Request Lifecycle](#91-api-request-lifecycle)
   - 9.2 [OPD Patient Flow](#92-opd-patient-flow)
   - 9.3 [IPD Admission Flow](#93-ipd-admission-flow)
   - 9.4 [Billing Flow](#94-billing-flow)
10. [Important Business Logic](#10-important-business-logic)
11. [System Strengths](#11-system-strengths)
12. [Conclusion](#12-conclusion)

---

<a id="1-project-overview"></a>

## 1. Project Overview

[Back to Table of Contents](#table-of-contents)

<a id="11-purpose--problem-statement"></a>

### 1.1 Purpose & Problem Statement

**DigiHMS** (Digital Hospital Management System) is a comprehensive, multi-tenant healthcare management platform designed to digitize and streamline hospital and clinic operations. It addresses the critical challenges faced by healthcare facilities:

- **Fragmented patient records** scattered across paper files and disconnected systems
- **Inefficient appointment scheduling** leading to long wait times and no-shows
- **Manual billing processes** prone to errors and revenue leakage
- **Lack of real-time visibility** into bed availability, pharmacy inventory, and diagnostic orders
- **No unified platform** for OPD, IPD, pharmacy, diagnostics, and financial management

DigiHMS provides a single, unified backend API that powers hospital operations end-to-end -- from patient registration through discharge and billing.

<a id="12-target-users"></a>

### 1.2 Target Users

| User Role | Description |
|-----------|-------------|
| Hospital Administrators | Manage hospital configuration, staff, and system settings |
| Doctors | View patient records, manage appointments, write clinical notes |
| Front Desk / Receptionists | Register patients, schedule appointments, manage OPD queue |
| Billing Staff | Generate and manage OPD/IPD bills, process payments |
| Pharmacists | Manage inventory, dispense medicines, process pharmacy orders |
| Lab Technicians | Process diagnostic orders, enter lab results, generate reports |
| Patients | View own records, book appointments (via frontend applications) |

<a id="13-key-design-decisions"></a>

### 1.3 Key Design Decisions

1. **No local User model** -- All user management is centralized in the SuperAdmin system. DigiHMS references users exclusively via UUID fields.
2. **Multi-tenancy via `tenant_id`** -- Every database model includes a `tenant_id` UUID field for complete data isolation between hospitals/clinics.
3. **JWT-based authentication** -- API requests are authenticated using Bearer tokens issued by the SuperAdmin system.
4. **Generic Foreign Keys for encounter-based models** -- Diagnostic orders, clinical notes, and prescriptions use Django's contenttypes framework to link to either OPD Visits or IPD Admissions.
5. **Polymorphic billing** -- Unified requisition system routes charges to either OPD or IPD billing based on the encounter context.

---

<a id="2-system-architecture"></a>

## 2. System Architecture

[Back to Table of Contents](#table-of-contents)

<a id="21-high-level-architecture"></a>

### 2.1 High-Level Architecture

```
                    +----------------------------+
                    |      Frontend Client        |
                    |   (React / Next.js App)     |
                    +-------------+--------------+
                                  |
                          HTTPS / REST API
                                  |
                    +-------------v--------------+
                    |     DigiHMS Backend         |
                    |     (Django + DRF)          |
                    |     Port: 8002              |
                    +---+------+------+------+---+
                        |      |      |      |
              +---------+  +---+--+ +-+----+ +--------+
              |            |      | |      | |        |
          +---v---+   +----v--+ +-v----+ +-v------+ +-v--------+
          |Postgre|   |Celery | |Redis | |Razorpay| |SuperAdmin|
          |  SQL  |   |Workers| |Cache | |Payment | |Port: 8000|
          +-------+   +-------+ +------+ +--------+ +----------+
```

<a id="22-satellite-application-pattern"></a>

### 2.2 Satellite Application Pattern

DigiHMS operates as a **satellite application** under a centralized SuperAdmin ecosystem:

```
+------------------------------------------+
|        SuperAdmin (Port 8000)            |
|  - User creation & management            |
|  - Tenant provisioning                   |
|  - JWT token generation                  |
|  - Permission assignment                 |
|  - Module enablement (HMS, CRM, etc.)    |
+------------------+-----------------------+
                   |  JWT Tokens + User Data
                   v
+------------------------------------------+
|        DigiHMS (Port 8002)               |
|  - Hospital management features          |
|  - Patient records & clinical data       |
|  - Billing, pharmacy, diagnostics        |
|  - NO user database (UUID refs only)     |
+------------------------------------------+
```

**Why this pattern?**
- Centralized user management eliminates duplication across multiple applications
- Single sign-on (SSO) experience across the entire product suite
- Permission management is consistent and centralized
- DigiHMS focuses purely on healthcare domain logic

<a id="23-multi-tenancy-architecture"></a>

### 2.3 Multi-Tenancy Architecture

DigiHMS implements **application-level multi-tenancy** using a shared database with tenant isolation via UUID fields.

**How it works:**

1. Every model has a mandatory `tenant_id` field (UUIDField with db_index)
2. The `TenantViewSetMixin` automatically filters all API queries by `request.tenant_id`
3. The `TenantMixin` serializer automatically sets `tenant_id` on record creation
4. Tenant ID is extracted from the JWT token during authentication
5. Thread-local storage holds the current `tenant_id` for use throughout the request lifecycle

**Data isolation guarantee:**
- Staff users see only data belonging to their tenant
- Patient users see only their own records within their tenant
- All database queries are automatically scoped by `tenant_id`

<a id="24-authentication--authorization-flow"></a>

### 2.4 Authentication & Authorization Flow

#### JWT Authentication (API)

```
Client                     DigiHMS                   SuperAdmin
  |                           |                          |
  |--- Login Request -------->|                          |
  |                           |--- Validate creds ------>|
  |                           |<-- JWT Token ------------|
  |<-- JWT Token -------------|                          |
  |                           |                          |
  |--- API Request + Bearer ->|                          |
  |                           |-- Decode & Validate JWT  |
  |                           |-- Set request attrs      |
  |                           |-- Filter by tenant_id    |
  |<-- API Response ----------|                          |
```

#### JWT Payload Structure

```json
{
  "user_id": "UUID",
  "email": "user@hospital.com",
  "tenant_id": "UUID",
  "tenant_slug": "hospital-name",
  "user_type": "staff",
  "is_patient": false,
  "is_super_admin": false,
  "permissions": {
    "hms.patients.view": "all",
    "hms.patients.create": true,
    "hms.opd.view": "own"
  },
  "enabled_modules": ["hms"]
}
```

#### Permission Scopes

| Scope | Meaning |
|-------|---------|
| `true` | User has full permission for this action |
| `false` | User is denied this action |
| `"all"` | User can access all records within their tenant |
| `"own"` | User can access only their own records |
| `"team"` | User can access records of their team (future) |

---

<a id="3-technology-stack"></a>

## 3. Technology Stack

[Back to Table of Contents](#table-of-contents)

<a id="31-core-technologies"></a>

### 3.1 Core Technologies

| Category | Technology | Version | Purpose |
|----------|-----------|---------|---------|
| **Language** | Python | 3.x | Backend development |
| **Framework** | Django | 5.2.9 | Web framework |
| **API Framework** | Django REST Framework | 3.14.0 | RESTful API layer |
| **Database** | PostgreSQL | Latest | Primary data store |
| **Task Queue** | Celery | 5.3.4 | Async task processing |
| **Message Broker** | Redis | 5.0.1 | Celery broker & caching |
| **API Documentation** | drf-spectacular | 0.28.0 | OpenAPI/Swagger docs |

<a id="32-third-party-libraries"></a>

### 3.2 Third-Party Libraries

| Library | Purpose |
|---------|---------|
| `PyJWT` | JWT token decoding and validation |
| `django-cors-headers` | Cross-Origin Resource Sharing |
| `django-filter` | Advanced queryset filtering for APIs |
| `django-import-export` | Excel/CSV import and export for data |
| `razorpay` | Razorpay payment gateway SDK |
| `psycopg2-binary` | PostgreSQL database adapter |
| `python-decouple` | Environment variable management |
| `dj-database-url` | Database URL parsing |
| `whitenoise` | Static file serving in production |
| `pandas` / `openpyxl` / `XlsxWriter` | Data processing & Excel operations |
| `Pillow` | Image processing |
| `requests` | HTTP client for external API calls |

<a id="33-external-integrations"></a>

### 3.3 External Integrations

| Integration | Purpose |
|-------------|---------|
| **SuperAdmin (Celiyo)** | Centralized authentication, user management, tenant provisioning |
| **Razorpay** | Online payment processing, webhook-based payment confirmation |
| **Meta (Facebook) Conversions API** | Marketing analytics and lead tracking |
| **Google Sheets API** | Lead data synchronization |
| **Nakshatra Forms API** | External lead capture and form submission processing |
| **Nuvi API** | External form submission and lead capture |

---

<a id="4-project-structure"></a>

## 4. Project Structure

[Back to Table of Contents](#table-of-contents)

<a id="41-directory-layout"></a>

### 4.1 Directory Layout

```
dghms/
|-- manage.py                    # Django management entry point
|-- requirements.txt             # Python dependencies
|-- .env.example                 # Environment variable template
|-- claude.md                    # Architecture & development guide
|-- rules.md                     # Coding standards and conventions
|
|-- hms/                         # Django project configuration
|   |-- settings.py              # Project settings
|   |-- urls.py                  # Root URL configuration
|   |-- wsgi.py                  # WSGI application
|   |-- asgi.py                  # ASGI application
|   |-- celery.py                # Celery configuration
|
|-- common/                      # Shared utilities & middleware
|   |-- middleware.py            # JWT & custom auth middleware
|   |-- mixins.py                # Tenant, serializer & viewset mixins
|   |-- permissions.py           # Permission checking utilities
|   |-- auth_backends.py         # SuperAdmin & JWT auth backends
|   |-- drf_auth.py              # DRF authentication classes
|   |-- admin_site.py            # Custom HMS admin site
|   |-- views.py                 # Auth proxy views
|   |-- urls.py                  # Common URL patterns
|
|-- apps/                        # Application modules
|   |-- patients/                # Patient management
|   |-- doctors/                 # Doctor profiles & availability
|   |-- appointments/            # Appointment scheduling
|   |-- opd/                     # Outpatient department
|   |-- ipd/                     # Inpatient department
|   |-- pharmacy/                # Pharmacy & inventory
|   |-- diagnostics/             # Lab tests & reports
|   |-- orders/                  # Service orders & Razorpay
|   |-- payments/                # Financial transactions
|   |-- services/                # Hospital services catalog
|   |-- panchakarma/             # Ayurvedic therapy tracking
|   |-- hospital/                # Hospital configuration
|   |-- auth/                    # Authentication endpoints
|   |-- nakshatra_api/           # Nakshatra lead capture
|   |-- nuviapi/                 # Nuvi form submissions
|
|-- templates/                   # HTML templates
|-- media/                       # Uploaded files
```

<a id="42-key-file-descriptions"></a>

### 4.2 Key File Descriptions

| File | Purpose |
|------|---------|
| `hms/settings.py` | Central configuration including database, middleware stack, JWT settings, CORS, Razorpay credentials, Celery config |
| `common/middleware.py` | `JWTAuthenticationMiddleware` -- decodes JWT, validates token, sets `request.user_id`, `request.tenant_id`, and permission attributes |
| `common/mixins.py` | `TenantModelMixin` (abstract model), `TenantMixin` (serializer), `TenantViewSetMixin` (auto-filter), `PatientAccessMixin` (patient data restriction), `EncounterMixin` (generic FK to Visit/Admission) |
| `common/permissions.py` | `HMSPermissions` constants, `check_permission()` function, `permission_required` decorator, `PermissionRequiredMixin` |

---

<a id="5-core-modules--components"></a>

## 5. Core Modules / Components

[Back to Table of Contents](#table-of-contents)

<a id="51-common-module"></a>

### 5.1 Common Module

The `common` module is the foundational layer that all other modules depend on. It provides:

- **JWTAuthenticationMiddleware** -- Intercepts every API request, decodes the JWT token from the Authorization header, validates it against the shared secret, and populates request attributes (`user_id`, `tenant_id`, `permissions`, etc.)
- **TenantViewSetMixin** -- Automatically filters all querysets by `tenant_id` and sets it on new records
- **TenantMixin** -- Serializer mixin that auto-injects `tenant_id` during creation and prevents modification during updates
- **PatientAccessMixin** -- Restricts patient-type users to viewing only their own records
- **EncounterMixin** -- Abstract model mixin using Django's contenttypes framework to create generic foreign keys pointing to either OPD Visits or IPD Admissions
- **HMSPermissions** -- Centralized permission constants and checking utilities
- **TenantUser** -- Non-database user class that wraps JWT payload data for Django admin compatibility

<a id="52-patients-module"></a>

### 5.2 Patients Module

**Responsibility:** Patient registration, profile management, vitals tracking, and allergy records.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `PatientProfile` | Core patient record with demographics, contact, medical, insurance, and emergency contact information |
| `PatientVitals` | Vital sign recordings (temperature, BP, heart rate, SpO2, blood glucose) |
| `PatientAllergy` | Allergy records with severity levels and treatment information |

**Notable Features:**
- Auto-generated patient IDs in format `PAT{YEAR}{SEQUENCE}` (e.g., `PAT20250001`)
- Automatic age calculation from date of birth
- Automatic BMI calculation from height and weight
- Walk-in patient support (null `user_id`)
- Insurance validity tracking

<a id="53-doctors-module"></a>

### 5.3 Doctors Module

**Responsibility:** Doctor profile management, specialties, availability scheduling.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `Specialty` | Medical specialty definitions (per tenant) |
| `DoctorProfile` | Doctor professional information, license details, consultation fees, ratings |
| `DoctorAvailability` | Weekly schedule slots with day, time range, and max appointments |

**Notable Features:**
- License validity tracking with automatic expiration checks
- Many-to-many relationship with specialties
- Consultation and follow-up fee configuration
- Online/offline availability flags
- System-maintained statistics (average rating, total consultations)

<a id="54-appointments-module"></a>

### 5.4 Appointments Module

**Responsibility:** Appointment scheduling, check-in tracking, and status management.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `AppointmentType` | Configurable appointment types with default duration and base fees |
| `Appointment` | Full appointment record with scheduling, status tracking, and check-in data |

**Notable Features:**
- Auto-generated appointment IDs: `APT-{YEAR}-{SEQUENCE}` (e.g., `APT-2025-000123`)
- Eight appointment statuses: Scheduled, Confirmed, Checked In, In Progress, Completed, Cancelled, No Show, Rescheduled
- Priority levels: Low, Normal, High, Urgent
- Follow-up appointment tracking with reference to original appointment
- Automatic end-time calculation from start time + duration
- Cancellation tracking with reason and user attribution
- Direct link to OPD Visit when patient checks in
- Unique constraint preventing double-booking (doctor + date + time)

<a id="55-opd-module"></a>

### 5.5 OPD Module (Outpatient Department)

**Responsibility:** Walk-in and scheduled visit management, clinical documentation, billing, and queue management.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `Visit` | Core OPD visit tracking with queue position, consultation timing, and payment status |
| `OPDBill` | Bill generation with charges, discounts, and payment tracking |
| `OPDBillItem` | Individual line items within an OPD bill |
| `ClinicalNoteTemplate` | Configurable templates for clinical documentation |
| `ClinicalNoteTemplateField` | Individual fields within a clinical note template |
| `ClinicalNoteTemplateResponse` | Patient-specific responses linked to encounters via generic FK |
| `ClinicalNoteTemplateFieldResponse` | Individual field responses within a clinical note |
| `Prescription` | Medication prescriptions linked to encounters |
| `PrescriptionItem` | Individual prescribed medications with dosage instructions |
| `ProcedureMaster` | Master list of medical procedures with charges |
| `ProcedurePackage` | Bundled procedure packages with discounted pricing |

**Notable Features:**
- Auto-generated visit numbers: `OPD/{DATE}/{SEQUENCE}`
- Six visit statuses: Waiting, Called, In Consultation, Completed, Cancelled, No Show
- Queue management with position tracking
- Waiting time calculation
- Flexible clinical note templates (customizable per tenant)
- Generic foreign key linking clinical notes to either OPD visits or IPD admissions
- Multi-bill support per visit
- Automatic financial calculations (totals, discounts, balance)

<a id="56-ipd-module"></a>

### 5.6 IPD Module (Inpatient Department)

**Responsibility:** Ward/bed management, patient admissions, bed transfers, inpatient billing.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `Ward` | Physical ward units (General, ICU, Private, Maternity, etc.) |
| `Bed` | Individual beds with type, daily charge, occupancy status, and equipment flags |
| `Admission` | IPD admission records with diagnosis, discharge, and bed assignment |
| `BedTransfer` | Bed transfer history for a patient during admission |
| `IPDBilling` | IPD bills with comprehensive financial tracking |
| `IPDBillItem` | Line items with source tracking (Bed, Pharmacy, Lab, Surgery, etc.) |

**Notable Features:**
- 12 ward types (General, ICU, NICU, PICU, Maternity, Surgical, etc.)
- Automatic bed occupancy management on admission, transfer, and discharge
- Auto-generated admission IDs: `IPD/{DATE}/{SEQUENCE}`
- Length of stay calculation
- Discharge workflow with summary and type tracking
- Bed transfer history with old/new bed tracking and automatic occupancy updates
- Bill items with origin tracking via generic foreign keys
- Price override support with system-calculated price comparison
- Automatic bed charge calculation based on length of stay
- Retry logic for bill number generation (handles concurrent bill creation)

<a id="57-pharmacy-module"></a>

### 5.7 Pharmacy Module

**Responsibility:** Product catalog, inventory management, shopping cart, and pharmacy orders.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `ProductCategory` | Product categories (Medicine, Healthcare Product, Medical Equipment) |
| `PharmacyProduct` | Product catalog with pricing, stock levels, and full-text search |
| `Cart` / `CartItem` | Shopping cart for pharmacy purchases |
| `PharmacyOrder` / `PharmacyOrderItem` | Pharmacy order processing and tracking |

**Notable Features:**
- PostgreSQL full-text search with GIN index for fast product lookup
- Weighted search vectors (product name > company > batch number)
- Low stock warning based on configurable minimum stock levels
- Price-at-time snapshot for cart items and order items (prevents pricing inconsistencies)
- Automatic selling price defaulting to MRP

<a id="58-diagnostics-module"></a>

### 5.8 Diagnostics Module

**Responsibility:** Investigation master list, requisitions, diagnostic/medicine/procedure orders, lab reports.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `Investigation` | Master test list with categories (22+ lab/imaging categories), codes, and base charges |
| `Requisition` | Order grouping linked to encounters via `EncounterMixin` -- supports investigations, medicines, procedures, and packages |
| `DiagnosticOrder` | Individual investigation orders with sample tracking |
| `MedicineOrder` | Medicine orders linked to pharmacy products |
| `ProcedureOrder` | Procedure orders linked to OPD procedure masters |
| `PackageOrder` | Package orders linked to OPD procedure packages |
| `LabReport` | Results with structured JSON data and file attachments |
| `InvestigationRange` | Normal reference ranges by gender and age group |

**Notable Features:**
- Unified requisition system supporting 4 order types (investigation, medicine, procedure, package)
- Encounter-based billing target resolution (OPD Bill vs IPD Bill Item)
- Auto-pricing from master data
- Lab report verification workflow (technician enters, doctor verifies)
- Auto-generated requisition numbers with date and UUID suffix
- Import/export support via `django-import-export`
- Celery tasks for background processing

<a id="59-orders--payments-module"></a>

### 5.9 Orders & Payments Module

**Responsibility:** Service order management, Razorpay payment integration, financial transaction tracking.

**Orders Key Models:**

| Model | Purpose |
|-------|---------|
| `FeeType` | Configurable fee types (service, delivery, tax, consultation, misc) |
| `Order` | Polymorphic order supporting diagnostic, nursing, home healthcare, consultation, lab, and pharmacy services |
| `OrderItem` | Generic FK-based items referencing any service type |
| `OrderFee` | Fee breakdown per order |
| `RazorpayConfig` | Per-tenant Razorpay credentials and settings |

**Payments Key Models:**

| Model | Purpose |
|-------|---------|
| `PaymentCategory` | Transaction categories (income, expense, refund, adjustment) |
| `Transaction` | Comprehensive financial transaction log with reconciliation support |
| `AccountingPeriod` | Periodic financial summaries (monthly, quarterly, annual) |

**Notable Features:**
- Razorpay payment gateway integration with webhook verification
- Per-tenant Razorpay configuration (test/live mode toggle)
- Auto-generated order numbers: `ORD{YEAR}{SEQUENCE}`
- Auto-generated transaction numbers: `TRX{YEAR}{SEQUENCE}`
- Generic FK-based order items supporting any service type
- Financial period reporting with income/expense/profit calculations
- Transaction reconciliation workflow

<a id="510-services-module"></a>

### 5.10 Services Module

**Responsibility:** Hospital services catalog (diagnostics, nursing care, home healthcare).

**Key Models:**

| Model | Purpose |
|-------|---------|
| `ServiceCategory` | Service categories with type classification |
| `BaseService` (abstract) | Common service fields (name, pricing, duration, etc.) |
| `DiagnosticTest` | Diagnostic test services with sample type and turnaround time |
| `NursingCarePackage` | Nursing packages (hourly, half-day, full-day) with target groups |
| `HomeHealthcareService` | Home healthcare services with staff type and distance requirements |

<a id="511-panchakarma-module"></a>

### 5.11 Panchakarma Module

**Responsibility:** Ayurvedic therapy management and session tracking.

**Key Models:**

| Model | Purpose |
|-------|---------|
| `Therapy` | Master list of Ayurvedic treatments with codes and charges |
| `PanchakarmaOrder` | Therapy orders linked to encounters via `EncounterMixin` |
| `PanchakarmaSession` | Individual therapy session tracking with scheduling and therapist assignment |

**Notable Features:**
- Encounter-aware billing (same pattern as diagnostics)
- Session-level tracking with status management
- Therapist assignment per session

<a id="512-hospital-configuration-module"></a>

### 5.12 Hospital Configuration Module

**Responsibility:** Hospital/clinic master configuration.

**Key Model:** `Hospital` -- Singleton model storing hospital identity, contact details, address, operational settings (working hours, emergency/pharmacy/lab availability), and registration information.

**Notable Features:**
- Enforced singleton pattern (only one record per system)
- Deletion protection
- Convenience method `get_hospital()` for accessing the configuration

<a id="513-external-api-modules"></a>

### 5.13 External API Modules

#### Nakshatra API
Public endpoint for capturing leads from Nakshatra form submissions. Integrates with Meta Conversions API for marketing analytics and a custom API endpoint for CRM ingestion. No authentication required.

#### Nuvi API
Public endpoint for processing Nuvi form submissions. Forwards lead data to external services. No authentication required.

---

<a id="6-key-functionalities"></a>

## 6. Key Functionalities

[Back to Table of Contents](#table-of-contents)

| # | Functionality | Description |
|---|---------------|-------------|
| 1 | **Patient Registration** | Register new patients (walk-in or linked to SuperAdmin user), generate unique patient IDs, manage demographics, medical history, insurance |
| 2 | **Doctor Management** | Create doctor profiles, configure specialties, set consultation fees, manage weekly availability schedules |
| 3 | **Appointment Scheduling** | Schedule, confirm, reschedule, and cancel appointments; track check-ins and waiting times; prevent double-booking |
| 4 | **OPD Queue Management** | Real-time queue tracking, automatic visit number generation, consultation timing, queue position management |
| 5 | **Clinical Documentation** | Customizable clinical note templates, prescription management with dosage and duration, encounter-based notes (OPD/IPD) |
| 6 | **IPD Bed Management** | Ward and bed setup, real-time occupancy tracking, bed transfers with history, equipment flags (oxygen, ventilator) |
| 7 | **IPD Admissions** | Admission workflow, provisional and final diagnosis, discharge with summary, length of stay tracking |
| 8 | **Diagnostic Ordering** | Order investigations, track sample collection, process lab results, generate reports with structured data |
| 9 | **Pharmacy & Inventory** | Product catalog with categories, stock level monitoring, low stock alerts, full-text search, order processing |
| 10 | **Unified Billing** | OPD and IPD billing with auto-calculations, discounts, multiple payment modes, automatic bed charge calculation |
| 11 | **Payment Processing** | Razorpay integration for online payments, webhook-based verification, per-tenant payment configuration |
| 12 | **Financial Tracking** | Transaction logging, payment categorization, accounting periods, reconciliation workflow, profit/loss summaries |
| 13 | **Prescription Management** | Create prescriptions with medication details, dosage, frequency, duration, and instructions |
| 14 | **Panchakarma Therapy** | Ayurvedic treatment ordering, session scheduling, therapist assignment, session tracking |
| 15 | **Data Import/Export** | Excel/CSV import and export for pharmacy products, investigations, and other master data |
| 16 | **API Documentation** | Auto-generated Swagger UI and ReDoc documentation via drf-spectacular |
| 17 | **Lead Capture** | Nakshatra and Nuvi form submissions with Meta CAPI integration and Google Sheets sync |

---

<a id="7-api--service-layer"></a>

## 7. API / Service Layer

[Back to Table of Contents](#table-of-contents)

<a id="71-api-endpoint-reference"></a>

### 7.1 API Endpoint Reference

All authenticated API endpoints require `Authorization: Bearer <JWT_TOKEN>` header.

| Endpoint Prefix | Method(s) | Purpose |
|-----------------|-----------|---------|
| `api/patients/` | GET, POST, PUT, PATCH, DELETE | Patient CRUD, search, filter by status/gender/blood group |
| `api/patients/{id}/vitals/` | GET, POST | Patient vital signs |
| `api/patients/{id}/allergies/` | GET, POST | Patient allergy records |
| `api/doctors/` | GET, POST, PUT, PATCH, DELETE | Doctor profile CRUD with specialty associations |
| `api/doctors/{id}/availability/` | GET, POST, PUT, DELETE | Doctor weekly availability schedule |
| `api/doctors/specialties/` | GET, POST | Medical specialties management |
| `api/appointments/` | GET, POST, PUT, PATCH, DELETE | Appointment CRUD with status management |
| `api/appointments/types/` | GET, POST | Appointment type configuration |
| `api/opd/visits/` | GET, POST, PUT, PATCH | OPD visit management and queue tracking |
| `api/opd/bills/` | GET, POST, PUT, PATCH | OPD billing management |
| `api/opd/clinical-notes/` | GET, POST, PUT | Clinical note templates and responses |
| `api/opd/prescriptions/` | GET, POST, PUT | Prescription management |
| `api/opd/procedures/` | GET, POST | Procedure master and packages |
| `api/ipd/wards/` | GET, POST, PUT, DELETE | Ward management |
| `api/ipd/beds/` | GET, POST, PUT, DELETE | Bed management with occupancy tracking |
| `api/ipd/admissions/` | GET, POST, PUT, PATCH | Admission management with discharge workflow |
| `api/ipd/bed-transfers/` | GET, POST | Bed transfer operations |
| `api/ipd/billing/` | GET, POST, PUT, PATCH | IPD billing and bill items |
| `api/pharmacy/products/` | GET, POST, PUT, DELETE | Product catalog with full-text search |
| `api/pharmacy/categories/` | GET, POST | Product category management |
| `api/pharmacy/cart/` | GET, POST, PUT, DELETE | Shopping cart operations |
| `api/pharmacy/orders/` | GET, POST | Pharmacy order management |
| `api/diagnostics/investigations/` | GET, POST, PUT | Investigation master list |
| `api/diagnostics/requisitions/` | GET, POST, PUT | Requisition management |
| `api/diagnostics/orders/` | GET, POST, PUT | Diagnostic order tracking |
| `api/diagnostics/medicine-orders/` | GET, POST, PUT | Medicine order management |
| `api/diagnostics/reports/` | GET, POST, PUT | Lab report management |
| `api/orders/` | GET, POST, PUT | Service order management |
| `api/orders/razorpay/` | POST | Razorpay order creation |
| `api/orders/webhooks/razorpay/` | POST | Razorpay webhook handler |
| `api/payments/transactions/` | GET, POST | Financial transaction tracking |
| `api/payments/categories/` | GET, POST | Payment category management |
| `api/payments/periods/` | GET, POST | Accounting period management |
| `api/services/` | GET, POST | Hospital services catalog |
| `api/panchakarma/` | GET, POST, PUT | Panchakarma therapy management |
| `api/hospital/` | GET, PUT | Hospital configuration (singleton) |

<a id="72-authentication-endpoints"></a>

### 7.2 Authentication Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `api/auth/login/` | POST | Authenticate via SuperAdmin and receive JWT |
| `auth/proxy-login/` | POST | Admin panel proxy login to SuperAdmin |
| `auth/logout/` | POST | Session logout |

<a id="73-public-endpoints"></a>

### 7.3 Public Endpoints (No Authentication Required)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `api/nuviformsubmit/` | POST | Nuvi form submission |
| `api/nakshatra/` | POST | Nakshatra lead capture |
| `api/orders/webhooks/razorpay/` | POST | Razorpay payment webhook |
| `api/docs/` | GET | Swagger UI documentation |
| `api/redoc/` | GET | ReDoc API documentation |
| `api/schema/` | GET | OpenAPI schema |

---

<a id="8-database-design"></a>

## 8. Database Design

[Back to Table of Contents](#table-of-contents)

<a id="81-entity-relationship-overview"></a>

### 8.1 Entity Relationship Overview

```
Hospital (Singleton)
    |
    +-- PatientProfile ----+---- PatientVitals
    |       |               +---- PatientAllergy
    |       |
    |       +---- Appointment ---- AppointmentType
    |       |         |
    |       |         +---- Visit (OPD)
    |       |                  |
    |       |                  +---- OPDBill ---- OPDBillItem
    |       |                  +---- ClinicalNoteTemplateResponse
    |       |                  +---- Prescription ---- PrescriptionItem
    |       |
    |       +---- Admission (IPD)
    |       |         |
    |       |         +---- IPDBilling ---- IPDBillItem
    |       |         +---- BedTransfer
    |       |         +---- ClinicalNoteTemplateResponse
    |       |
    |       +---- Requisition
    |       |         +---- DiagnosticOrder ---- LabReport
    |       |         +---- MedicineOrder
    |       |         +---- ProcedureOrder
    |       |         +---- PackageOrder
    |       |
    |       +---- PanchakarmaOrder ---- PanchakarmaSession
    |       +---- Order ---- OrderItem / OrderFee
    |
    +-- DoctorProfile ---- DoctorAvailability
    |       |
    |       +---- Specialty (M2M)
    |
    +-- Ward ---- Bed
    +-- Investigation ---- InvestigationRange
    +-- Therapy
    +-- PharmacyProduct ---- ProductCategory
    +-- ServiceCategory ---- DiagnosticTest / NursingCarePackage / HomeHealthcareService
    +-- PaymentCategory ---- Transaction
    +-- AccountingPeriod
    +-- RazorpayConfig
    +-- NakshatraLead
```

<a id="82-core-models-reference"></a>

### 8.2 Core Models Reference

| Model | Table Name | Key Fields | Relationships |
|-------|-----------|------------|---------------|
| `PatientProfile` | `patient_profiles` | patient_id (auto), first_name, last_name, gender, mobile, DOB, blood_group, insurance | -> PatientVitals, PatientAllergy, Appointment, Visit, Admission |
| `DoctorProfile` | `doctor_profiles` | user_id (UUID, unique), first_name, last_name, license_number, consultation_fee | -> Specialty (M2M), DoctorAvailability |
| `Appointment` | `appointments` | appointment_id (auto), appointment_date/time, status, priority, consultation_fee | -> Patient, Doctor, AppointmentType, Visit |
| `Visit` | `opd_visits` | visit_number (auto), visit_date, visit_type, status, queue_position, payment_status | -> Patient, Doctor, Appointment, OPDBill |
| `Admission` | `ipd_admissions` | admission_id (auto), admission_date, status, diagnosis, discharge_summary | -> Patient, Ward, Bed, IPDBilling |
| `Ward` | `ipd_wards` | name, type, floor, total_beds | -> Bed |
| `Bed` | `ipd_beds` | bed_number, bed_type, daily_charge, is_occupied, has_oxygen, has_ventilator | -> Ward, Admission |
| `Investigation` | `diag_investigations` | name, code, category, base_charge, specimen_type | -> DiagnosticOrder, InvestigationRange |
| `Requisition` | `diag_requisitions` | requisition_number (auto), type, status, priority | -> Patient, DiagnosticOrder, MedicineOrder, ProcedureOrder, PackageOrder |
| `PharmacyProduct` | `pharmacy_products` | product_name, mrp, selling_price, quantity, expiry_date, search_vector | -> ProductCategory, CartItem, PharmacyOrderItem |
| `Order` | `orders` | order_number (auto), services_type, status, payment_method, razorpay fields | -> Patient, Appointment, OrderItem, OrderFee |
| `Transaction` | `transactions` | transaction_number (auto), amount, transaction_type, payment_method | -> PaymentCategory, Generic FK |
| `Hospital` | `hospital_config` | name, type, email, phone, address, working_hours | Singleton |

<a id="83-naming-conventions"></a>

### 8.3 Naming Conventions

| Pattern | Convention | Example |
|---------|-----------|---------|
| Tenant isolation | `tenant_id` UUIDField on all models | `tenant_id = models.UUIDField(db_index=True)` |
| User references | `*_user_id` or `*_id` UUID fields (never FK to User) | `created_by_user_id`, `doctor_id` |
| Timestamps | `created_at` / `updated_at` | `auto_now_add=True` / `auto_now=True` |
| Auto-generated IDs | `{PREFIX}{YEAR}{SEQUENCE}` or `{PREFIX}/{DATE}/{SEQUENCE}` | `PAT20250001`, `OPD/20250305/001` |
| Status fields | `status` CharField with choices | `STATUS_CHOICES = [('active', 'Active'), ...]` |
| Audit fields | `created_by_user_id`, `cancelled_by_user_id`, etc. | UUID fields for attribution |

---

<a id="9-application-flow"></a>

## 9. Application Flow

[Back to Table of Contents](#table-of-contents)

<a id="91-api-request-lifecycle"></a>

### 9.1 API Request Lifecycle

```
1. Client sends HTTP request with Bearer JWT token
         |
2. JWTAuthenticationMiddleware intercepts
   - Checks if path is public (docs, admin, webhooks)
   - Extracts Bearer token from Authorization header
   - Decodes JWT using shared secret (HS256)
   - Validates expiration and required fields
   - Checks 'hms' module is enabled
   - Sets request attributes (user_id, tenant_id, permissions)
   - Creates TenantUser and assigns to request.user
         |
3. Django routing matches URL to ViewSet
         |
4. DRF Authentication (JWTAuthentication class)
   - Validates request.user is authenticated TenantUser
         |
5. DRF Permission (IsAuthenticated)
   - Confirms user is authenticated
         |
6. ViewSet action executes
   - TenantViewSetMixin filters queryset by tenant_id
   - PatientAccessMixin restricts patients to own records
   - Business logic and permission checks via check_permission()
         |
7. Serializer validates and processes data
   - TenantMixin auto-sets tenant_id on create
   - Field-level validation
   - Nested serializer handling
         |
8. Response returned to client
```

<a id="92-opd-patient-flow"></a>

### 9.2 OPD Patient Flow

```
1. Patient Registration
   POST /api/patients/ -> Creates PatientProfile with auto-generated ID

2. Appointment Booking (optional)
   POST /api/appointments/ -> Creates appointment with doctor and time slot

3. Check-In / Walk-In
   POST /api/opd/visits/ -> Creates Visit with queue position and visit number

4. Vitals Recording
   POST /api/patients/{id}/vitals/ -> Records temperature, BP, heart rate, etc.

5. Consultation
   Visit status -> "in_consultation"
   POST /api/opd/clinical-notes/ -> Doctor creates clinical notes
   POST /api/opd/prescriptions/ -> Doctor writes prescriptions

6. Diagnostic / Pharmacy Orders
   POST /api/diagnostics/requisitions/ -> Orders lab tests or medicines
   Automatic billing item creation in OPD bill

7. Billing
   POST /api/opd/bills/ -> Generate bill with auto-calculated totals
   Process payment (cash, card, UPI, Razorpay)

8. Completion
   Visit status -> "completed"
   Payment status -> "paid"
```

<a id="93-ipd-admission-flow"></a>

### 9.3 IPD Admission Flow

```
1. Admission
   POST /api/ipd/admissions/ -> Creates admission record
   - Auto-generates admission ID
   - Assigns ward and bed
   - Bed automatically marked as occupied

2. During Stay
   - Vitals recorded periodically
   - Clinical notes added to admission encounter
   - Diagnostic orders processed
   - Medicine orders dispensed
   - Bed transfers tracked if patient moves

3. Billing
   POST /api/ipd/billing/ -> Create IPD bill
   - Bed charges auto-calculated from admission/discharge dates
   - Lab, pharmacy, procedure items added as bill items
   - Discount support (percentage or fixed amount)
   - Multiple bills per admission supported

4. Discharge
   PATCH /api/ipd/admissions/{id}/ -> Discharge patient
   - Sets discharge date, summary, and type
   - Bed automatically marked as available
   - Final bill generated with all charges
```

<a id="94-billing-flow"></a>

### 9.4 Billing Flow

```
+-- Requisition Created (Investigation, Medicine, Procedure, Package)
|
+-- Billing Target Determined
|   |
|   +-- If encounter is Visit -> OPD Bill / OPDBillItem
|   +-- If encounter is Admission -> IPD Bill / IPDBillItem
|
+-- Bill Item Created with source tracking
|   - DiagnosticOrder -> source: "Lab"
|   - MedicineOrder -> source: "Pharmacy"
|   - ProcedureOrder -> source: "Procedure"
|   - Bed charges -> source: "Bed" (auto-calculated)
|
+-- Bill Totals Auto-Calculated
|   - total_amount = SUM(item.total_price)
|   - discount_amount = total * discount_percent / 100
|   - payable_amount = total - discount
|   - balance_amount = payable - received
|
+-- Payment Status Updated
    - unpaid: received = 0
    - partial: 0 < received < payable
    - paid: received >= payable
```

---

<a id="10-important-business-logic"></a>

## 10. Important Business Logic

[Back to Table of Contents](#table-of-contents)

### Auto-Generated Identifiers

All key entities generate unique, human-readable identifiers:
- **Patients:** `PAT{YEAR}{4-digit sequence}` -- e.g., `PAT20250042`
- **Appointments:** `APT-{YEAR}-{6-digit sequence}` -- e.g., `APT-2025-000123`
- **OPD Visits:** `OPD/{YYYYMMDD}/{3-digit sequence}` -- e.g., `OPD/20250305/001`
- **IPD Admissions:** `IPD/{YYYYMMDD}/{3-digit sequence}` -- e.g., `IPD/20250305/001`
- **IPD Bills:** `IPD-BILL/{YYYYMMDD}/{3-digit sequence}`
- **Requisitions:** `REQ-{YYYYMMDD}-{6-char UUID hex}`
- **Orders:** `ORD{YEAR}{4-digit sequence}`
- **Transactions:** `TRX{YEAR}{4-digit sequence}`

### Encounter-Based Architecture

The system uses Django's `ContentType` framework to create a polymorphic encounter system:
- `EncounterMixin` provides a generic FK that can point to either `Visit` (OPD) or `Admission` (IPD)
- Requisitions, clinical notes, prescriptions, and Panchakarma orders all use this pattern
- The `billing_target` property on Requisition determines whether charges go to OPD or IPD billing
- This eliminates code duplication between OPD and IPD clinical workflows

### Bed Management Automation

- When a patient is admitted and assigned a bed, the bed status automatically changes to "occupied"
- When a bed transfer occurs, the old bed is released and the new bed is occupied -- all in one atomic operation
- When a patient is discharged, the assigned bed is automatically released

### IPD Billing Auto-Calculations

IPD bill totals are automatically calculated using signals:
1. When an `IPDBillItem` is saved or deleted, the parent `IPDBilling` recalculates totals
2. Bed charges are auto-computed from `admission_date` to `discharge_date` (or current date) multiplied by the bed's daily rate
3. Discount can be percentage-based (auto-calculated) or a fixed amount
4. Payment status is derived from the relationship between `payable_amount` and `received_amount`

### Price Override Tracking

IPD bill items track both the `system_calculated_price` and the actual `unit_price`. If a staff member manually changes a price, the `is_price_overridden` flag is set, enabling audit trails for billing adjustments.

### Full-Text Search (Pharmacy)

Pharmacy products leverage PostgreSQL's native full-text search with:
- `SearchVectorField` populated automatically on save
- Weighted search: product name (A), company (B), batch number (C)
- GIN index for high-performance search queries
- Used for fast medicine lookup during prescription and order workflows

### Patient ID Auto-Assignment for Walk-Ins

Walk-in patients can be registered without a SuperAdmin user account (`user_id = null`). The system generates a unique `patient_id` and captures demographics directly. If the patient later creates a SuperAdmin account, their `user_id` can be linked retroactively.

---

<a id="11-system-strengths"></a>

## 11. System Strengths

[Back to Table of Contents](#table-of-contents)

| Strength | Description |
|----------|-------------|
| **Clean Multi-Tenancy** | Consistent `tenant_id` isolation across every model with automated filtering via mixins -- no tenant data leakage risk |
| **Zero User Model Dependency** | Eliminates coupling to Django's User model, enabling seamless integration with any centralized auth system |
| **Polymorphic Encounter System** | Single clinical workflow implementation serves both OPD and IPD through Django's contenttypes framework |
| **Comprehensive Billing Engine** | Auto-calculated financial fields, multi-source bill items, price override tracking, and integrated payment gateway |
| **Modular Architecture** | 14 Django apps with clear separation of concerns -- each module is independently maintainable |
| **Production-Ready Auth** | JWT middleware with token validation, clock skew tolerance, module-level access control, and granular permissions |
| **Automated Bed Management** | Bed occupancy is managed atomically across admissions, transfers, and discharges |
| **Extensible Permission System** | Scope-based permissions (all/own/team) with centralized checking utilities and decorator support |
| **API-First Design** | Full REST API coverage with DRF ViewSets, filterable/searchable/orderable endpoints, and auto-generated OpenAPI docs |
| **Audit Trail** | Consistent `created_by_user_id`, `cancelled_by_user_id`, and timestamp fields across all models |
| **Background Task Support** | Celery + Redis integration for async operations (diagnostics processing, data imports) |
| **Data Import/Export** | django-import-export integration for bulk data management via Excel/CSV |

---

<a id="12-conclusion"></a>

## 12. Conclusion

[Back to Table of Contents](#table-of-contents)

DigiHMS is a professionally architected, multi-tenant hospital management system that delivers a comprehensive suite of healthcare operations management capabilities through a well-designed REST API.

**Core Capabilities:**
- End-to-end patient lifecycle management from registration through discharge
- Integrated OPD and IPD workflows with shared clinical documentation
- Unified billing engine spanning consultations, diagnostics, pharmacy, procedures, and bed charges
- Real-time bed and queue management with automatic state transitions
- Secure, scalable multi-tenancy enabling a single deployment to serve multiple hospitals

**Architecture Highlights:**
- The satellite application pattern with SuperAdmin integration provides enterprise-grade authentication without local user management complexity
- The encounter-based polymorphic architecture eliminates code duplication between OPD and IPD clinical workflows
- Consistent use of mixins (`TenantViewSetMixin`, `TenantMixin`, `PatientAccessMixin`) ensures data isolation is enforced at every layer

**Integration Ecosystem:**
- Razorpay payment gateway with per-tenant configuration
- Meta Conversions API for marketing analytics
- Google Sheets and external CRM integrations for lead management
- OpenAPI/Swagger auto-generated documentation for frontend teams

The system is designed to scale horizontally, support diverse healthcare facility types (clinics, hospitals, Ayurvedic centers), and integrate with the broader Celiyo product suite through its JWT-based authentication architecture.

---

*This document was auto-generated from codebase analysis. For development guidelines and contribution standards, refer to `claude.md` and `rules.md` in the project root.*
