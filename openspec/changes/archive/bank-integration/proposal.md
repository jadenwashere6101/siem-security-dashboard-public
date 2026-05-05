# Bank Application to SIEM Integration Proposal

## Purpose
Define how the banking application sends structured security and activity events to the SIEM ingestion API for centralized storage, detection, and alerting.

---

## Problem
The banking application generates important security-relevant actions such as login failures, account lockouts, and transactions, but without a standardized integration path these events cannot be consistently forwarded to the SIEM.

---

## Proposed Solution
Integrate the banking application with the SIEM by:

- Adding a helper function:
  - `send_siem_event(...)`
- Sending events from key banking routes to:
  - `POST /ingest`
- Formatting events as structured JSON payloads
- Including API key authentication with:
  - `X-API-Key`
- Logging transmission failures without breaking bank app behavior

---

## Behavior

- The bank app runs in the same deployment environment as the SIEM backend
- SIEM communication occurs over an internal HTTP path
- Event transmission is triggered from important banking actions such as:
  - login success
  - login failure
  - account lock
  - deposit
  - withdraw
  - registration

- If SIEM delivery fails:
  - the banking app logs the failure
  - core banking behavior continues
  - the user-facing action is not blocked by SIEM downtime

---

## Scope

This proposal applies to:
- Flask banking application backend
- SIEM ingestion API integration
- Event forwarding from banking routes

---

## Out of Scope

- Frontend dashboard behavior
- SIEM detection rule implementation
- Cross-VM communication design
- Message queue or asynchronous delivery

---

## Success Criteria

- Banking application sends structured events to SIEM successfully
- Event delivery uses API key authentication
- Failures are logged without interrupting banking operations
- Integration works over an internal application-to-application network path
