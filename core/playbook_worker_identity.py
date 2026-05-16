"""Stable worker identity for playbook execution lease ownership."""

from __future__ import annotations

import os
import socket
import uuid


def generate_playbook_worker_id() -> str:
    """
    Build a non-secret worker identity: hostname:pid:uuid-fragment.

    Used as playbook_executions.lease_owner for the lifetime of one runner process.
    """
    host = socket.gethostname()
    pid = os.getpid()
    fragment = uuid.uuid4().hex[:8]
    return f"{host}:{pid}:{fragment}"
