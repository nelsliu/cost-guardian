# metrics.py
# Simple metrics collection for Cost Guardian API
# Future: expose via /metrics endpoint for monitoring

# Module-level counters
rate_limit_hits = 0
ingest_success = 0
ingest_duplicate = 0
ingest_bad_auth = 0
ingest_validation_error = 0

def increment_rate_limit_hits():
    """Increment the rate limit hits counter."""
    global rate_limit_hits
    rate_limit_hits += 1

def increment_ingest_success():
    """Increment the ingest success counter."""
    global ingest_success
    ingest_success += 1

def increment_ingest_duplicate():
    """Increment the ingest duplicate counter."""
    global ingest_duplicate
    ingest_duplicate += 1

def increment_ingest_bad_auth():
    """Increment the ingest bad auth counter."""
    global ingest_bad_auth
    ingest_bad_auth += 1

def increment_ingest_validation_error():
    """Increment the ingest validation error counter."""
    global ingest_validation_error
    ingest_validation_error += 1

def get_metrics() -> dict:
    """Get current metrics snapshot.
    
    Returns:
        dict: Current metrics values
    """
    return {
        'rate_limit_hits': rate_limit_hits,
        'ingest_success': ingest_success,
        'ingest_duplicate': ingest_duplicate,
        'ingest_bad_auth': ingest_bad_auth,
        'ingest_validation_error': ingest_validation_error,
    }

def reset_metrics():
    """Reset all metrics counters (useful for testing)."""
    global rate_limit_hits, ingest_success, ingest_duplicate, ingest_bad_auth, ingest_validation_error
    rate_limit_hits = 0
    ingest_success = 0
    ingest_duplicate = 0
    ingest_bad_auth = 0
    ingest_validation_error = 0