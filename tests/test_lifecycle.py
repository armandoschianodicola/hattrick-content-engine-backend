import pytest

from hattrick_backend.core.exceptions import AppError
from hattrick_backend.domain.enums import PostState
from hattrick_backend.domain.lifecycle import require_publishable, validate_transition

ALLOWED = {
    ("DRAFT", "PENDING_REVIEW"),
    ("PENDING_REVIEW", "APPROVED"),
    ("PENDING_REVIEW", "REJECTED"),
    ("REJECTED", "DRAFT"),
    ("APPROVED", "SCHEDULED"),
    ("APPROVED", "PUBLISHED"),
    ("APPROVED", "FAILED"),
    ("SCHEDULED", "APPROVED"),
    ("SCHEDULED", "PUBLISHED"),
    ("SCHEDULED", "FAILED"),
    ("FAILED", "APPROVED"),
}


@pytest.mark.parametrize("current", list(PostState))
@pytest.mark.parametrize("target", list(PostState))
def test_transition_matrix(current, target):
    if (current, target) in ALLOWED:
        validate_transition(current, target)
    else:
        with pytest.raises(AppError, match="Cannot transition"):
            validate_transition(current, target)


@pytest.mark.parametrize("state", ["DRAFT", "PENDING_REVIEW", "REJECTED", "FAILED"])
def test_unapproved_cannot_publish(state):
    with pytest.raises(AppError):
        require_publishable(state, None, 1)


def test_stale_approval_cannot_publish():
    with pytest.raises(AppError):
        require_publishable("APPROVED", 1, 2)
