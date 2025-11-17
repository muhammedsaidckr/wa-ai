from datetime import datetime, timedelta
from typing import Dict
from collections import defaultdict


class RateLimiter:
    """Simple in-memory rate limiter"""

    def __init__(self, max_requests: int, window_seconds: int):
        """
        Initialize rate limiter

        Args:
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds
        """
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, list] = defaultdict(list)

    def is_allowed(self, identifier: str) -> bool:
        """
        Check if request is allowed based on rate limit

        Args:
            identifier: Unique identifier (e.g., phone number)

        Returns:
            bool: True if request is allowed
        """
        now = datetime.utcnow()
        cutoff_time = now - timedelta(seconds=self.window_seconds)

        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]

        # Check if limit exceeded
        if len(self.requests[identifier]) >= self.max_requests:
            return False

        # Add current request
        self.requests[identifier].append(now)
        return True

    def get_remaining_requests(self, identifier: str) -> int:
        """Get number of remaining requests for identifier"""
        now = datetime.utcnow()
        cutoff_time = now - timedelta(seconds=self.window_seconds)

        # Clean old requests
        self.requests[identifier] = [
            req_time for req_time in self.requests[identifier]
            if req_time > cutoff_time
        ]

        return max(0, self.max_requests - len(self.requests[identifier]))

    def reset(self, identifier: str):
        """Reset rate limit for identifier"""
        if identifier in self.requests:
            del self.requests[identifier]
