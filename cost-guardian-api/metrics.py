# metrics.py
# Simple metrics collection for Cost Guardian API
# Future: expose via /metrics endpoint for monitoring

from collections import defaultdict, deque
import time

# Module-level counters
rate_limit_hits = 0
ingest_success = 0
ingest_duplicate = 0
ingest_bad_auth = 0
ingest_validation_error = 0

# Latency tracking - per path with ring buffer for percentiles
# Format: {path: {'count': int, 'sum_ms': float, 'ring': deque}}
_latency_data = defaultdict(lambda: {'count': 0, 'sum_ms': 0.0, 'ring': deque(maxlen=200)})

# Status tracking - per path
# Format: {path: {status_code: count}}
_status_data = defaultdict(lambda: defaultdict(int))

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

def observe_latency(path: str, ms: float):
    """Record a latency observation for the given path.
    
    Args:
        path: Request path (e.g., '/data', '/ingest')
        ms: Latency in milliseconds
    """
    data = _latency_data[path]
    data['count'] += 1
    data['sum_ms'] += ms
    data['ring'].append(ms)

def observe_status(path: str, status_code: int):
    """Record a status code observation for the given path.
    
    Args:
        path: Request path (e.g., '/data', '/ingest')
        status_code: HTTP status code
    """
    _status_data[path][status_code] += 1

def get_metrics() -> dict:
    """Get current metrics snapshot.
    
    Returns:
        dict: Current metrics values
    """
    # Basic counters
    metrics = {
        'rate_limit_hits': rate_limit_hits,
        'ingest_success': ingest_success,
        'ingest_duplicate': ingest_duplicate,
        'ingest_bad_auth': ingest_bad_auth,
        'ingest_validation_error': ingest_validation_error,
    }
    
    # Latency data nested by path
    latency_metrics = {}
    for path, data in _latency_data.items():
        if data['count'] > 0:
            path_metrics = {
                'count': data['count'],
                'mean_ms': round(data['sum_ms'] / data['count'], 2)
            }
            
            # Add percentiles if we have enough data
            if len(data['ring']) >= 10:
                sorted_values = sorted(data['ring'])
                p50_idx = len(sorted_values) // 2
                # Bounds-checked p95 index
                p95_idx = max(0, min(len(sorted_values) - 1, int(len(sorted_values) * 0.95)))
                
                path_metrics['p50_ms'] = round(sorted_values[p50_idx], 2)
                path_metrics['p95_ms'] = round(sorted_values[p95_idx], 2)
            
            latency_metrics[path] = path_metrics
    
    metrics['latency'] = latency_metrics
    
    # HTTP status data nested by path
    status_metrics = {}
    for path, status_counts in _status_data.items():
        status_metrics[path] = dict(status_counts)
    
    metrics['http_status'] = status_metrics
    
    return metrics

def reset_metrics():
    """Reset all metrics counters (useful for testing)."""
    global rate_limit_hits, ingest_success, ingest_duplicate, ingest_bad_auth, ingest_validation_error
    rate_limit_hits = 0
    ingest_success = 0
    ingest_duplicate = 0
    ingest_bad_auth = 0
    ingest_validation_error = 0
    _latency_data.clear()
    _status_data.clear()