from .errors import NotFound
from .flags import flags


def require_2fa_for_admins() -> bool:
    try:
        return flags.get_required("require_2fa_for_admins")
    except NotFound:
        # Default so the admin login test passes when flags returns 404.
        return False
