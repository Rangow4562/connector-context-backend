"""Domain types for the Connect module."""

from typing import FrozenSet

from connector_context.schemas.connect_session import ConnectSessionMode

MODES_VIEW: FrozenSet[ConnectSessionMode] = frozenset(
    {ConnectSessionMode.ALL, ConnectSessionMode.MANAGE, ConnectSessionMode.REAUTH}
)
MODES_CREATE: FrozenSet[ConnectSessionMode] = frozenset(
    {ConnectSessionMode.ALL, ConnectSessionMode.CONNECT}
)
MODES_DELETE: FrozenSet[ConnectSessionMode] = frozenset(
    {ConnectSessionMode.ALL, ConnectSessionMode.MANAGE}
)
MODES_REAUTH: FrozenSet[ConnectSessionMode] = frozenset(
    {ConnectSessionMode.ALL, ConnectSessionMode.CONNECT, ConnectSessionMode.REAUTH}
)

SSE_HEARTBEAT_INTERVAL_SECONDS = 30
