"""Policy module for XFusion v0.2.4.2."""

from xfusion.policy.categories import (
    PolicyCategory,
    PolicyCategoryDefinition,
    get_policy_category_definition,
    is_forbidden,
    requires_admin_permission,
    requires_confirmation,
)

__all__ = [
    # Categories
    "PolicyCategory",
    "PolicyCategoryDefinition",
    "get_policy_category_definition",
    "is_forbidden",
    "requires_admin_permission",
    "requires_confirmation",
]
