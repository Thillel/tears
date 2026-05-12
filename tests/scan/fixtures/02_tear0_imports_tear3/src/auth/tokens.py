# @tear: 0
from utils.helpers import sanitize


def verify(token: str) -> str:
    return sanitize(token)
