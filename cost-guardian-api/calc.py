def compute_cost(usage: dict) -> float:
    # Example rates (adjust as needed)
    # gpt-4o-mini: ~$0.00015 per 1k input, $0.0006 per 1k output
    inp_rate = 0.00015 / 1000.0
    out_rate = 0.0006 / 1000.0
    pt = usage.get("prompt_tokens", 0) or 0
    ct = usage.get("completion_tokens", 0) or 0
    return round(pt * inp_rate + ct * out_rate, 8)