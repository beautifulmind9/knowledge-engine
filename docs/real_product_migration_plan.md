# Real Product Migration Plan

## Purpose

The current Streamlit app has validated the early product workflow. It proved that the system can extract knowledge from sources, organize it into reusable structures, and apply that knowledge inside a workshop experience.

The next stage is to move from prototype to real product architecture.

## Product Direction

The product is moving toward:

```text
Personal Knowledge Library
+
Knowledge Workshop
```

Users should eventually be able to:

1. Create an account.
2. Create private libraries.
3. Upload books, PDFs, articles, reports, notes, and other sources.
4. Process those sources into structured knowledge.
5. Select sources or libraries for a workshop.
6. Choose what they want to do with the knowledge.
7. Generate, edit, save, and export useful outputs.

## Why Move Away From Streamlit

Streamlit was useful for validating the workflow quickly, but it is not the final interface.

The real product needs:

- User accounts
- Private libraries
- Source uploads
- Processing status
- Saved drafts and outputs
- Editable writing canvas
- Side-by-side source and output panels
- Better navigation
- File storage
- Database-backed knowledge objects
- Background processing jobs
- More polished product experience

Streamlit should become a legacy prototype, not the main product interface.

## Proposed Architecture

```text
apps/web
- Next.js or React frontend
- Library dashboard
- Source upload flow
- Workshop interface
- Editable output canvas

apps/api
- FastAPI backend
- Source metadata API
- Processing endpoints
- Retrieval endpoints
- Workshop generation endpoints

packages/shared
- Shared types and schemas later

docs
- Product, architecture, roadmap, and design notes

legacy/streamlit_prototype
- Existing Streamlit proof of concept
```

## Suggested Stack

### Frontend

- Next.js or React
- Tailwind CSS or a component library later
- Deployed initially to Vercel or Cloudflare Pages

### Backend

- Python
- FastAPI
- Existing extraction and graph logic gradually moved into backend services

### Database

- PostgreSQL or Supabase
- Supabase is attractive for early product work because it includes Postgres, Auth, Storage, and Row Level Security

### File Storage

- Supabase Storage, S3, or similar
- Store user-uploaded files privately
- Support deletion controls and retention settings

### Background Jobs

- Start simple with manual processing endpoints
- Later add background workers for extraction, chunking, and analysis

## Deployment Strategy

Start simple, but avoid locking the whole product into one hosting platform.

Possible early deployment:

```text
Frontend: Vercel or Cloudflare Pages
Backend API: Render, Fly.io, Railway, or similar
Database/Auth/Storage: Supabase
```

Deployment should be revisited once there are real usage and cost patterns.

Notes from deployment research:

- Vercel is easy and fast for Next.js, but may become expensive as usage grows.
- Cloudflare Pages and OpenNext can be lower-cost alternatives for Next.js-style deployments.
- SST and AWS can offer more granular pricing and control, but add infrastructure complexity.
- The product should keep frontend, backend, database, storage, and processing jobs separate enough to move pieces later.

## Core Data Model

Initial entities:

```text
users
profiles
libraries
sources
source_files
chunks
concepts
problems
insights
relationships
workspaces
outputs
```

### User

Represents the authenticated person using the product.

### Library

A private collection of sources grouped by topic or purpose.

Examples:

- Copywriting
- Product Strategy
- Finance
- Founder Storytelling
- Research
- Learning

### Source

A book, PDF, article, report, document, or note uploaded or added by a user.

### Source File

The actual uploaded file or stored reference.

### Chunk

A processed section of source text.

### Concept

A reusable idea extracted from one or more sources.

### Problem

A problem, friction, or challenge the source addresses.

### Insight

A structured takeaway from a source.

### Relationship

Links between sources, concepts, problems, insights, examples, and decision rules.

### Workspace

A user-created working session around a goal.

### Output

A generated or edited result from a workshop, such as a draft, brief, checklist, study guide, or decision memo.

## Core Product Workflow

```text
Sign in
↓
Create or select library
↓
Upload source
↓
Add source metadata
↓
Process source
↓
Review extracted knowledge
↓
Select source(s) for workshop
↓
Choose goal, output format, and tone
↓
Generate/edit/save output
```

## Migration Steps

### Step 1: Preserve the Prototype

Move the current Streamlit app into:

```text
legacy/streamlit_prototype
```

The prototype remains useful as proof of concept and reference implementation.

### Step 2: Create Real App Structure

Create:

```text
apps/api
apps/web
packages/shared
```

Add starter README files explaining what belongs in each folder.

### Step 3: Scaffold FastAPI Backend

Initial backend goals:

- Health check endpoint
- Source metadata endpoint
- Library endpoint
- Placeholder processing endpoint
- Workshop endpoint placeholder

Example endpoints:

```text
GET /health
GET /libraries
POST /libraries
GET /sources
POST /sources
POST /sources/{source_id}/process
GET /sources/{source_id}/status
POST /workshops
```

### Step 4: Scaffold Frontend

Initial frontend screens:

- Home
- Library dashboard
- Source upload
- Source detail/status
- Workshop

### Step 5: Add Database Schema

Document Supabase/Postgres schema before implementing.

Create SQL migrations later.

### Step 6: Connect Source Upload Flow

Build the first real product loop:

```text
Create library
↓
Add source metadata
↓
Upload file
↓
Show source in library
```

Processing can remain manual at first.

### Step 7: Move Processing Pipeline

Gradually move existing scripts into API services:

- PDF extraction
- Text chunking
- AI prompt generation
- Result import
- Graph validation
- Graph cleaning

### Step 8: Rebuild Knowledge Workshop

Rebuild the Streamlit workshop as a real UI:

```text
Left panel: libraries and selected sources
Center panel: workshop form and editable output
Right panel: relevant concepts, rules, examples, warnings, and evidence
```

## Near-Term Build Order

1. Add this migration plan.
2. Move Streamlit prototype to `legacy/streamlit_prototype`.
3. Create `apps/api` scaffold.
4. Create `apps/web` scaffold.
5. Document database schema.
6. Build source/library API.
7. Build source upload UI.
8. Rebuild workshop UI.

## Product Principle

Do not rebuild everything at once.

Carry forward the validated workflow:

```text
Source
↓
Structured knowledge
↓
Selected scope
↓
Workshop goal
↓
Useful output
```

The migration should preserve what has been learned while creating a foundation that can support real users, private libraries, uploads, saved outputs, and a better workspace experience.
