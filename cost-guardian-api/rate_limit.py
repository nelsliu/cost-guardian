import time
import math
from typing import Tuple, Dict, Any

# Module-level state for token buckets
# Format: {key: {tokens: float, last_ms: int}}
_buckets: Dict[str, Dict[str, Any]] = {}
_rpm: int = 60
_burst: int = 60
_regen_rate: float = 1.0  # tokens per second
_exempt_paths: list = []

def init_limit(rpm: int, burst: int, exempt_paths: list = None) -> None:
    """Initialize the rate limiter with the given parameters.
    
    Args:
        rpm: Requests per minute allowed
        burst: Maximum burst capacity (tokens)
        exempt_paths: List of paths that should bypass rate limiting
    """
    global _rpm, _burst, _regen_rate, _exempt_paths, _buckets
    
    _rpm = rpm
    _burst = burst
    _regen_rate = rpm / 60.0  # Convert RPM to tokens per second
    _exempt_paths = exempt_paths or []
    _buckets = {}  # Reset buckets on init

def check_rate_limit(key: str, now_ms: int = None) -> Tuple[bool, int, float]:
    """Check if a request should be rate limited using token bucket algorithm.
    
    Args:
        key: The identifier to rate limit (API key, IP address, etc.)
        now_ms: Current time in milliseconds (uses time.monotonic() if None)
        
    Returns:
        Tuple of (allowed: bool, retry_after_seconds: int, remaining_tokens: float)
        - allowed: True if request should be allowed, False if rate limited
        - retry_after_seconds: Number of seconds to wait before retrying (0 if allowed)
        - remaining_tokens: Current number of tokens remaining in bucket
    """
    if now_ms is None:
        now_ms = int(time.monotonic() * 1000)
    
    # Get or create bucket for this key
    if key not in _buckets:
        _buckets[key] = {
            'tokens': float(_burst),  # Start with full bucket
            'last_ms': now_ms
        }
    
    bucket = _buckets[key]
    
    # Calculate time elapsed since last check
    elapsed_ms = now_ms - bucket['last_ms']
    elapsed_sec = elapsed_ms / 1000.0
    
    # Refill tokens based on elapsed time
    tokens_to_add = elapsed_sec * _regen_rate
    bucket['tokens'] = min(_burst, bucket['tokens'] + tokens_to_add)
    bucket['last_ms'] = now_ms
    
    # Check if we have enough tokens for this request
    if bucket['tokens'] >= 1.0:
        # Allow request and consume one token
        bucket['tokens'] -= 1.0
        return True, 0, bucket['tokens']
    else:
        # Rate limited - calculate when enough tokens will be available
        tokens_needed = 1.0 - bucket['tokens']
        deficit_seconds = tokens_needed / _regen_rate
        retry_after = max(1, math.ceil(deficit_seconds))
        
        return False, retry_after, bucket['tokens']

def is_exempt_path(path: str, method: str = None) -> bool:
    """Check if a path should be exempt from rate limiting.
    
    Args:
        path: The request path to check
        method: The HTTP method (OPTIONS is always exempt)
        
    Returns:
        bool: True if the path should be exempt from rate limiting
    """
    # Always exempt OPTIONS requests
    if method == "OPTIONS":
        return True
    
    # Check configured exempt paths (exact match or prefix match)
    return any(path == p or path.startswith(p.rstrip('/') + '/') for p in _exempt_paths)

def get_config() -> dict:
    """Get current rate limiting configuration.
    
    Returns:
        dict: Current configuration including rpm, burst, and exempt paths
    """
    return {
        'rpm': _rpm,
        'burst': _burst,
        'regen_rate': _regen_rate,
        'exempt_paths': _exempt_paths.copy()
    }

def get_bucket_stats() -> Dict[str, Dict[str, Any]]:
    """Get current state of all rate limit buckets (for debugging).
    
    Returns:
        dict: Copy of current bucket states
    """
    return {key: bucket.copy() for key, bucket in _buckets.items()}