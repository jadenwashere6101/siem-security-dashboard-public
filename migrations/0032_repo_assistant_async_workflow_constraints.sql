ALTER TABLE ai_workflow_requests
    DROP CONSTRAINT IF EXISTS ai_workflow_requests_workflow_check;

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_workflow_check
        CHECK (workflow IN ('deep_investigate', 'decision_support', 'generate_artifact', 'repo_assistant'));

ALTER TABLE ai_workflow_requests
    DROP CONSTRAINT IF EXISTS ai_workflow_requests_stage_check;

ALTER TABLE ai_workflow_requests
    ADD CONSTRAINT ai_workflow_requests_stage_check
        CHECK (stage IN (
            'queued',
            'running',
            'gathering_context',
            'retrieving_evidence',
            'querying_tools',
            'preparing_evidence',
            'generating_analysis',
            'validating_response',
            'retrieving_repository_evidence',
            'preparing_repository_context',
            'generating_answer',
            'validating_citations',
            'complete',
            'failed'
        ));
