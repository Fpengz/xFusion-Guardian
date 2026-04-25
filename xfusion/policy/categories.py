"""Policy categories for v0.2.4.3 hybrid execution model."""

from __future__ import annotations

from dataclasses import dataclass

from xfusion.domain.enums import PolicyCategory


@dataclass(frozen=True)
class PolicyCategoryDefinition:
    """Definition of a policy category with its constraints."""

    category: PolicyCategory
    description: str
    confirmation_required: bool
    admin_permission_required: bool
    allowed_without_review: bool


POLICY_CATEGORIES: dict[PolicyCategory, PolicyCategoryDefinition] = {
    PolicyCategory.READ_ONLY: PolicyCategoryDefinition(
        category=PolicyCategory.READ_ONLY,
        description="Inspect state only, no confirmation usually required",
        confirmation_required=False,
        admin_permission_required=False,
        allowed_without_review=True,
    ),
    PolicyCategory.WRITE_SAFE: PolicyCategoryDefinition(
        category=PolicyCategory.WRITE_SAFE,
        description="Modifies non-critical state, confirmation usually required",
        confirmation_required=True,
        admin_permission_required=False,
        allowed_without_review=False,
    ),
    PolicyCategory.DESTRUCTIVE: PolicyCategoryDefinition(
        category=PolicyCategory.DESTRUCTIVE,
        description="Deletes, kills, overwrites, stops services - explicit confirmation required",
        confirmation_required=True,
        admin_permission_required=False,
        allowed_without_review=False,
    ),
    PolicyCategory.PRIVILEGED: PolicyCategoryDefinition(
        category=PolicyCategory.PRIVILEGED,
        description="Sudo/root/system-level/network-sensitive actions - admin permission required",
        confirmation_required=True,
        admin_permission_required=True,
        allowed_without_review=False,
    ),
    PolicyCategory.FORBIDDEN: PolicyCategoryDefinition(
        category=PolicyCategory.FORBIDDEN,
        description=(
            "Never allowed through the agent, cannot be bypassed by normal user confirmation"
        ),
        confirmation_required=False,
        admin_permission_required=False,
        allowed_without_review=False,
    ),
}


def get_policy_category_definition(category: PolicyCategory) -> PolicyCategoryDefinition:
    """Get the definition for a policy category."""
    return POLICY_CATEGORIES[category]


def requires_confirmation(category: PolicyCategory) -> bool:
    """Check if a policy category requires confirmation."""
    return get_policy_category_definition(category).confirmation_required


def requires_admin_permission(category: PolicyCategory) -> bool:
    """Check if a policy category requires admin permission."""
    return get_policy_category_definition(category).admin_permission_required


def is_forbidden(category: PolicyCategory) -> bool:
    """Check if a policy category is forbidden."""
    return category == PolicyCategory.FORBIDDEN
