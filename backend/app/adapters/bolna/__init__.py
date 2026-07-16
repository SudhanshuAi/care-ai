"""Bolna Voice AI adapter.

Bolna Custom Functions POST tool arguments directly to a per-tool URL
(unlike Retell, which posts `{name, args, call}` to one endpoint). This
package normalizes Bolna requests into the shared voice-tool dispatcher
used by the Retell adapter so `/tools/*` services stay telephony-agnostic.
"""
