# Phase 2 Security Review

Date: 2026-07-07

Scope: security review update for `pfsense-firewall-ingestion-roadmap` based on live VM audit findings and resulting design decisions. No code was implemented. No application source files were modified. The VM was not modified. No ports were opened. No Azure NSG rules were created. No child specs were created. No commits or pushes were performed.

## Live VM Listener And Port Findings

- UDP 514 is currently unused.
- `sudo ss -lun | grep 514` returned no listener.
- No syslog listener is currently bound to UDP 514.
- Current listening services include:
  - TCP 22 sshd
  - TCP 80 nginx
  - TCP 443 nginx
  - TCP 5051 SIEM backend Flask service
  - TCP 5052 Docker/gunicorn service
  - TCP 8080 flask-honeypot service
  - local PostgreSQL on 127.0.0.1:5432
  - local MySQL on 127.0.0.1:3306 and 127.0.0.1:33060
  - local DNS/systemd-resolved on 127.0.0.53:53
  - DHCP UDP 68
  - chrony UDP 323
- No current UDP syslog collector conflicts with the future pfSense listener.

## rsyslog Findings

- rsyslog is installed and active.
- rsyslog is being used for normal local Linux logging.
- `/etc/rsyslog.conf` has remote syslog UDP/TCP reception commented out:
  - `#module(load="imudp")`
  - `#input(type="imudp" port="514")`
  - `#input(type="imtcp" port="514")`
- There is no evidence rsyslog is currently receiving remote syslog.
- Decision: Do not modify or repurpose rsyslog for pfSense ingestion. Leave rsyslog untouched.

## Firewall Findings

- UFW is inactive.
- iptables and ip6tables exist.
- INPUT policy is ACCEPT with no custom inbound restrictions shown.
- Docker-related FORWARD chains exist.
- No VM-local firewall rule currently protects a future UDP listener.
- Decision: Azure NSG must be the primary network allow-list layer.
- Decision: VM-local filtering should be considered as defense-in-depth, but not assumed to already exist.

## Host Security Controls

- AppArmor is loaded and enforcing profiles.
- SELinux is not installed.
- fail2ban is not installed.
- Decision: Do not make fail2ban a prerequisite for pfSense ingestion.
- Decision: Treat application-level validation/rate limiting as required, not optional.

## Service Health Findings

- `siem-backend.service` is active/running.
- `soar-playbook-worker.service` is active/running.
- `soar-response-action-worker.timer` is active/waiting.
- The SIEM runtime environment is healthy enough to support future integration work.

## Listener Port Decision

Prefer a high unprivileged UDP port such as 5514 instead of privileged UDP 514, unless pfSense cannot send to a custom port.

Rationale:

- avoids privileged bind/root capability requirements
- avoids modifying rsyslog
- avoids standard syslog port assumptions
- easier systemd deployment
- UDP 514 remains unused and reserved

The final child spec should confirm pfSense supports the selected custom port before implementation.

If pfSense requires UDP 514, document the privilege/capability plan explicitly before implementation.

## Azure NSG Decision

- No Azure NSG rule should be opened until the listener is implemented and locally tested with synthetic packets.
- The eventual Azure NSG inbound rule must restrict UDP listener traffic to the expected pfSense public IP if possible.
- Do not use `Any` source unless explicitly accepted as a temporary test exception.
- Any temporary broader rule must have a cleanup/removal task.

## VM Firewall Decision

- Because UFW is inactive and INPUT policy is ACCEPT, do not assume the VM firewall protects the listener.
- If adding VM firewall defense-in-depth, prefer a minimal rule allowing the pfSense public IP to the chosen UDP port and rejecting/dropping other sources.
- Do not implement VM firewall rules in Phase 2.

## Source Validation Decision

- The listener/adapter must validate the packet sender source IP against an allow-list.
- The allow-list must include the expected pfSense public IP.
- Packets from unexpected sources must be rejected before parsing/ingest.
- Rejected packet counts should be logged/metriced without storing full attacker-controlled payloads.

## Packet And Input Safety Decisions

- Define a maximum UDP packet length before parsing.
- Recommended initial limit: 4096 bytes unless implementation audit justifies another value.
- Reject or truncate oversized packets before parsing.
- Decode syslog as UTF-8 with strict or safe replacement behavior, but never crash on malformed UTF-8.
- Strip unsafe control characters before logging/storing.
- Preserve enough raw context for debugging, but avoid broad raw syslog retention by default.
- Store normalized firewall events as the main record.

## Malformed Input Decisions

- Malformed syslog/filterlog lines must not crash the listener.
- Malformed lines should be counted/logged and either rejected or stored only as sanitized parse-failure telemetry, depending on the child spec decision.
- The parser should support common IPv4 TCP/UDP pfSense filterlog first.
- IPv6 and edge variants should be handled safely, even if not fully parsed initially.

## Rate Limiting And DoS Decisions

- UDP syslog is unauthenticated and spoofable.
- Rate limiting is required at the listener/application level.
- The design should include per-source and global bounds if possible.
- The design should avoid unbounded DB writes from malformed or repeated noise.
- Storage growth must be monitored.

## Privacy And Data Retention Decisions

- pfSense logs may contain real business network metadata.
- Document that logs will be stored on the Azure VM in the SIEM PostgreSQL database.
- Prefer normalized event storage over raw full-payload retention.
- Decide later whether raw syslog is retained temporarily, redacted, or dropped after parsing.
- Before asking uncle to configure pfSense, tell him where logs are stored and what type of logs are being sent.

## Runtime Readiness Gate

Do not ask uncle to configure pfSense until:

- listener is deployed
- chosen UDP port is open only to allowed source
- synthetic packet test passes
- parser test passes
- normalized event appears in DB/dashboard
- backend health passes
- listener service health/logging passes
- rejection tests pass
- deployment checklist is complete

## Remaining Phase 2 Gates

- Confirm final listener port selection, including whether pfSense supports the selected custom port.
- Confirm expected pfSense public IP for Azure NSG and listener allow-list.
- Create Azure NSG rule later only after listener implementation and local synthetic packet testing.
- Decide later whether to add VM firewall defense-in-depth rules.
- Draft uncle handoff message later, after deployment/runtime validation gates pass.

