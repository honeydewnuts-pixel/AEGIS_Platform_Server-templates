"""
Shared slowapi Limiter instance. Lives in its own module rather than
main.py so routers can import and use @limiter.limit(...) directly as a
decorator without a circular import (routers are imported BY main.py).
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
