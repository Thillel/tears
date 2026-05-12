# @tear: 0
import hashlib
import os


def hash_token(token: str) -> str:
    salt = os.urandom(16).hex()
    return hashlib.sha256((salt + token).encode()).hexdigest()
