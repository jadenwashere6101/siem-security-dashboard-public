# Alerts API Proposal

## Purpose
Define an API for retrieving alerts from the SIEM and updating alert status.

---

## Problem
Alerts exist in the database, but external consumers such as the frontend dashboard need a formal way to retrieve and manage them. Without a defined API, frontend-backend integration becomes fragile and inconsistent.

---

## Proposed Solution
Implement an alerts API that:

- Returns stored alerts from the database
- Sorts alerts by newest first
- Supports alert status updates
- Enables frontend filtering by severity and status

---

## Core Endpoints

- `GET /alerts`
- `POST /alerts/<id>/status`

---

## Scope

This proposal applies to:
- SIEM backend alert routes
- Frontend access to alert data

---

## Out of Scope

- User authentication/authorization model
- Bulk alert operations
- Alert deletion

---

## Success Criteria

- Frontend can retrieve alerts reliably
- Alerts are returned in descending time order
- Alert status can be updated from open to resolved