ALTER TABLE ai_workflow_requests
    DROP CONSTRAINT IF EXISTS ai_workflow_requests_workflow_check;

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_workflow_check
        CHECK (
            workflow IN (
                'deep_investigate',
                'decision_support',
                'generate_artifact',
                'repo_assistant',
                'nist_evidence_explanation'
            )
        );
