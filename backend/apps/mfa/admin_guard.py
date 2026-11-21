"""Close the MFA bypass through the Django admin (/admin/).

The admin has its own password login. Once MFA is enabled, an account with
MFA could otherwise reach /admin/ with the password alone. This guard makes
the admin require a session that completed the second factor (set by the
console login flow). It does nothing while ``MFA_ENABLED`` is off.
"""

from __future__ import annotations

SESSION_MFA_VERIFIED_AT = "mfa_verified_at"


def install(site) -> None:
    original = site.has_permission
    if getattr(original, "_surfacex_mfa_guard", False):
        return

    def has_permission(request) -> bool:
        if not original(request):
            return False
        # Imported lazily: keeps cryptography out of the startup path while MFA is off.
        from . import services

        if not services.is_feature_enabled() or not services.user_has_mfa(request.user):
            return True
        return bool(request.session.get(SESSION_MFA_VERIFIED_AT))

    has_permission._surfacex_mfa_guard = True
    site.has_permission = has_permission
