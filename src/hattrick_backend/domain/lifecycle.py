from hattrick_backend.core.exceptions import AppError
from hattrick_backend.domain.enums import PostState

TRANSITIONS = {
    PostState.DRAFT: {PostState.PENDING_REVIEW},
    PostState.PENDING_REVIEW: {PostState.APPROVED, PostState.REJECTED},
    PostState.REJECTED: {PostState.DRAFT},
    PostState.APPROVED: {PostState.SCHEDULED, PostState.PUBLISHED, PostState.FAILED},
    PostState.SCHEDULED: {PostState.APPROVED, PostState.PUBLISHED, PostState.FAILED},
    PostState.FAILED: {PostState.APPROVED},
    PostState.PUBLISHED: set(),
}


def validate_transition(current: str, target: PostState):
    if target not in TRANSITIONS[PostState(current)]:
        raise AppError("invalid_transition", f"Cannot transition from {current} to {target}", 409)


def require_publishable(state: str, approved_revision: int | None, revision: int):
    if state not in {PostState.APPROVED, PostState.SCHEDULED, PostState.PUBLISHED}:
        raise AppError("approval_required", "Publication requires human approval", 409)
    if approved_revision != revision:
        raise AppError("approval_required", "Approval does not cover the current revision", 409)
