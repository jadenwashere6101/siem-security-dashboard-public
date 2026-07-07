# Agent Instructions

## Source Of Truth

This project has a strict Mac/VM source-of-truth rule.

Read and follow:

- [docs/mac-vm-source-of-truth-policy.md](docs/mac-vm-source-of-truth-policy.md)

The short version:

- Mac repo is development/source of truth:
  `/Users/jadengomez/Desktop/siem-security-dashboard-public`
- VM repo is deployment/runtime only:
  `jaden@4.204.25.149:/home/jaden/siem-security-dashboard`
- Do not edit source code on the VM unless the user explicitly says this is a VM emergency hotfix.
- Never merge on a dirty VM.
- Do not commit or push unless the user explicitly asks.

