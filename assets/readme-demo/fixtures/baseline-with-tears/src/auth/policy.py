# @tear: 0
from .flags import flags


def require_2fa_for_admins() -> bool:
    return flags.get_required("require_2fa_for_admins")
