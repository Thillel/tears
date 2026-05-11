# @tear: 0
import hashlib


def verify(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()
