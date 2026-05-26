"""Channel adapter registry.

Adapters are registered at startup and resolved by channel name.
Modules and agents use the registry — they never import adapters directly.
"""

from __future__ import annotations

from corpmind.channels.base import ChannelAdapter

_registry: dict[str, ChannelAdapter] = {}


def register(adapter: ChannelAdapter) -> None:
    _registry[adapter.name] = adapter


def get(channel: str) -> ChannelAdapter:
    adapter = _registry.get(channel)
    if adapter is None:
        raise KeyError(f"No channel adapter registered for '{channel}'")
    return adapter


def list_channels() -> list[str]:
    return list(_registry.keys())


def initialize_adapters() -> None:
    """Register all channel adapters. Called during app lifespan startup."""
    from corpmind.channels.email_smtp import EmailSMTPAdapter

    register(EmailSMTPAdapter())
