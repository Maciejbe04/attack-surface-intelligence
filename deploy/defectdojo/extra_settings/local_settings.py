# Demo / competition: kill DefectDojo CSRF completely.
# Loaded after settings.dist.py via optional("local_settings.py").
#
# Removing CsrfViewMiddleware alone is not enough — login and other views still
# use @csrf_protect, which enforces CSRF without the middleware.

MIDDLEWARE = [
    middleware
    for middleware in MIDDLEWARE
    if "csrf" not in middleware.lower()
]

CSRF_COOKIE_SECURE = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_HTTPONLY = False
CSRF_USE_SESSIONS = False
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"

CSRF_TRUSTED_ORIGINS = list(
    {
        *getattr(locals(), "CSRF_TRUSTED_ORIGINS", []),
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:18081",
        "http://127.0.0.1:18081",
        "http://65.109.16.202:18081",
        "http://10.99.0.60:8081",
        "https://dojo.opselis.pl",
        "http://dojo.opselis.pl",
    }
)

# Bypass @csrf_protect / CsrfViewMiddleware checks everywhere.
from django.middleware.csrf import CsrfViewMiddleware  # noqa: E402


def _csrf_pass(self, request, callback, callback_args, callback_kwargs):  # noqa: ANN001
    request.csrf_processing_done = True
    return None


CsrfViewMiddleware.process_view = _csrf_pass
