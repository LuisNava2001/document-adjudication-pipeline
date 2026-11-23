"""Deterministic validation rules and the default rule set."""

from adjudication.core.rules.base import DocumentRule, Rule, ValidationContext
from adjudication.core.rules.consistency_rules import (
    ClaimedWithinDocumented,
    CurrencyMatchesClaim,
    DuplicateReceiptsInClaim,
    LineItemsReconcile,
    NotPreviouslySubmitted,
)
from adjudication.core.rules.document_rules import (
    DocumentsAttached,
    ExtractionSucceeded,
    FieldConfidence,
    FieldFormats,
    PositiveTotal,
    RequiredFieldsPresent,
)
from adjudication.core.rules.policy_rules import CategoryLimit, NotFutureDated, WithinSubmissionWindow


def default_rules() -> list[Rule]:
    """The demo rule set, in evaluation order."""
    return [
        DocumentsAttached(),
        ExtractionSucceeded(),
        RequiredFieldsPresent(),
        FieldConfidence(),
        FieldFormats(),
        PositiveTotal(),
        LineItemsReconcile(),
        CurrencyMatchesClaim(),
        ClaimedWithinDocumented(),
        WithinSubmissionWindow(),
        NotFutureDated(),
        CategoryLimit(),
        DuplicateReceiptsInClaim(),
        NotPreviouslySubmitted(),
    ]


__all__ = ["DocumentRule", "Rule", "ValidationContext", "default_rules"]
