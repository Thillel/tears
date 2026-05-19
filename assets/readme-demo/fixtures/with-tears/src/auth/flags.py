# @tear: 0
from .errors import NotFound


class FlagClient:
    def get_required(self, name: str) -> bool:
        raise NotFound(name)


flags = FlagClient()
