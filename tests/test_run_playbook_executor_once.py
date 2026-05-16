from scripts import run_playbook_executor_once


def test_recovery_dry_run_output_includes_worker_counts_and_ids():
    payload = {
        "mode": "simulation",
        "worker_id": "worker-alpha",
        "recovery": {
            "dry_run": True,
            "scanned": 1,
            "recovered": 0,
            "pending": 0,
            "failed": 0,
            "skipped_awaiting_approval": 2,
            "stale": [{"execution_id": 42}],
            "results": [],
        },
    }

    text = "\n".join(run_playbook_executor_once._render_recovery_summary_lines(payload))

    assert "Worker id:  worker-alpha" in text
    assert "Dry run:    True" in text
    assert "Recovered:  0" in text
    assert "Skipped awaiting approval: 2" in text
    assert "Stale execution ids: 42" in text
    assert "Recovered execution ids: none" in text
    assert "No playbook steps were executed." in text


def test_recovery_applied_output_includes_recovered_details():
    payload = {
        "mode": "simulation",
        "worker_id": "worker-beta",
        "recovery": {
            "dry_run": False,
            "scanned": 2,
            "recovered": 2,
            "pending": 1,
            "failed": 1,
            "skipped_awaiting_approval": 0,
            "stale": [{"execution_id": 7}, {"execution_id": 8}],
            "results": [
                {
                    "execution_id": 7,
                    "prior_status": "running",
                    "new_status": "pending",
                    "outcome": "recovered",
                    "recovery_count": 1,
                },
                {
                    "execution_id": 8,
                    "prior_status": "running",
                    "new_status": "failed",
                    "outcome": "recovered",
                    "recovery_count": 3,
                },
            ],
        },
    }

    text = "\n".join(run_playbook_executor_once._render_recovery_summary_lines(payload))

    assert "Worker id:  worker-beta" in text
    assert "Recovered:  2" in text
    assert "Pending:    1" in text
    assert "Failed:     1" in text
    assert "Recovered execution ids: 7,8" in text
    assert "Recovered execution 7: running -> pending recovery_count=1" in text
    assert "Recovered execution 8: running -> failed recovery_count=3" in text


def test_batch_output_includes_claimed_ids_and_lease_skip_reason():
    payload = {
        "mode": "simulation",
        "worker_id": "worker-gamma",
        "batch_size": 2,
        "summary": {
            "processed": 2,
            "success": 1,
            "failed": 0,
            "skipped": 1,
            "claimed_execution_ids": [100],
            "skip_reasons": {"lease_not_owned": 1},
        },
        "results": [],
    }

    text = "\n".join(run_playbook_executor_once._render_batch_summary_lines(payload))

    assert "Worker id:  worker-gamma" in text
    assert "Claimed execution ids: 100" in text
    assert "Skip reasons: lease_not_owned=1" in text
    assert "No real integrations were called." in text


def test_output_helpers_do_not_render_database_urls_or_secrets():
    payload = {
        "mode": "simulation",
        "worker_id": "worker-safe",
        "batch_size": 1,
        "summary": {
            "processed": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "claimed_execution_ids": [],
            "skip_reasons": {},
        },
        "results": [
            {
                "message": "postgresql://user:secret@example.invalid/db",
                "token": "secret-token",
            }
        ],
    }

    text = "\n".join(run_playbook_executor_once._render_batch_summary_lines(payload))

    assert "postgresql://" not in text
    assert "secret-token" not in text
    assert "secret" not in text.lower()
