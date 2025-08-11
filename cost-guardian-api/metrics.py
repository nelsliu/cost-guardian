# metrics.py
# Simple metrics collection for Cost Guardian API
# Future: expose via /metrics endpoint for monitoring

# Module-level counters
rate_limit_hits = 0

def increment_rate_limit_hits():
    """Increment the rate limit hits counter."""
    global rate_limit_hits
    rate_limit_hits += 1

def get_metrics() -> dict:
    """Get current metrics snapshot.
    
    Returns:
        dict: Current metrics values
    """
    return {
        'rate_limit_hits': rate_limit_hits,
    }

def reset_metrics():
    """Reset all metrics counters (useful for testing)."""
    global rate_limit_hits
    rate_limit_hits = 0