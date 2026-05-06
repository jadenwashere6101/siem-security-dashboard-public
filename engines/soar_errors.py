class RetryableActionError(Exception):
    def __init__(self, message, code="retryable_error"):
        super().__init__(message)
        self.code = code


class SkippedAction(Exception):
    def __init__(self, message, code="skipped"):
        super().__init__(message)
        self.code = code
