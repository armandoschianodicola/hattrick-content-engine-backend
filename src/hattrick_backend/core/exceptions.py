class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code = code
        self.message = message
        self.status = status
        super().__init__(message)


class InsufficientEvidence(AppError):
    def __init__(self):
        super().__init__(
            "insufficient_evidence", "The knowledge base has insufficient supporting evidence", 422
        )
