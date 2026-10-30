# Frontend Setup Guide

## Overview

This frontend is a React + Vite single-page app for:

- generating synthetic documents,
- running E&M coding flow on selected documents,
- reviewing structured coding output,
- downloading evidence and E&M JSON files.

## Prerequisites

- Node.js 18+ (recommended)
- npm 9+ (or compatible)
- Backend services running on expected ports:
  - Synthetic API: `http://localhost:8082`
  - Evidence API: `http://localhost:8000`
  - Resolver API: `http://localhost:8081`

## 1) Install dependencies

From this directory (`frontend`):

```bash
npm install
```

## 2) Run in development mode

```bash
npm run dev
```

Open:

- `http://localhost:5173`

## 3) Build for production

```bash
npm run build
```

## 4) Preview production build locally

```bash
npm run preview
```

## API base URLs

Configured in:

- `src/App.jsx`

Current frontend service mapping:

- `synthetic`: `http://localhost:8082`
- `evidence`: `http://localhost:8000`
- `em`: `http://localhost:8081`

## Important behavior notes

- Category selection is chip-based multi-select.
- `Pathology & Laboratory` is a merged category.
- `Medicines` and `Proprietary Laboratory Analyses (PLA)` are available categories.
- Number of documents field accepts digits only.
- E&M CPT whitelist is maintained in:
  - `src/constants/emCodes.js`
- Run E&M button is enabled only when selected document CPT is in allowed E&M list.
- Each document has its own cached result state (no cross-document result bleed).

## One-command full stack startup (optional)

From project root:

```bash
./start_services.sh start
```

This starts backend APIs and frontend dev server together.

To stop:

```bash
./start_services.sh stop
```

