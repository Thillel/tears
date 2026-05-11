# @tear: 1
from auth.tokens import verify


def login(token: str) -> str:
    return verify(token)
