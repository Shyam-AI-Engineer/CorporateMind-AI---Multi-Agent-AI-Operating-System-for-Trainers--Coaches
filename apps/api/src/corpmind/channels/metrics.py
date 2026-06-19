"""Shared Prometheus metrics for all channel adapters.

Defined once here so every adapter imports the same metric objects.
Prometheus raises ValueError on duplicate registration — all adapters use
the same `channel` label to distinguish per-channel data.
"""

from prometheus_client import Counter, Histogram

channel_send_total = Counter(
    "channel_send_total",
    "Total send attempts per channel",
    ["channel", "status"],
)

channel_send_latency_seconds = Histogram(
    "channel_send_latency_seconds",
    "Outbound send latency per channel",
    ["channel"],
)
