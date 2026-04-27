# SIEM Ingestion API Proposal

## Purpose
Define a standardized way for external applications (such as a banking app) to send security events into the SIEM system.

## Problem
Event ingestion currently exists only in backend code and is not formally defined. This makes integrations harder to maintain, less consistent, and more error-prone.

## Proposed Solution
Create a formal ingestion API contract that:
- Defines required event fields
- Standardizes accepted values (event types, severity levels)
- Specifies authentication behavior using an API key
- Ensures consistent validation and error handling

## Scope
- SIEM ingestion endpoint (`POST /ingest`)
- External systems sending events to the SIEM

## Out of Scope
- Detection logic
- Alert generation
- Dashboard/frontend behavior

## Success Criteria
- External apps can reliably send events using a consistent format
- Invalid requests are rejected clearly
- SIEM ingestion becomes reusable across systems

