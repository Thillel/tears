import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from auth.policy import require_2fa_for_admins


def test_admin_login_continues_when_flags_returns_404() -> None:
    assert require_2fa_for_admins() is False
