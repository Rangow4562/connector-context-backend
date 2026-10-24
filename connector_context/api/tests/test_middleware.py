"""Unit tests for exception handlers in middleware.py.

Calls handlers directly to cover mappings that no endpoint currently triggers.
"""

from unittest.mock import MagicMock

import pytest

from connector_context.api.middleware import connector_context_exception_handler
from connector_context.core.exceptions import ConnectorContextException, TokenRefreshError


@pytest.mark.asyncio
async def test_token_refresh_error_returns_401():
    response = await connector_context_exception_handler(MagicMock(), TokenRefreshError("token expired"))
    assert response.status_code == 401
    assert b"token expired" in response.body


@pytest.mark.asyncio
async def test_unmapped_connector_context_exception_returns_500():
    response = await connector_context_exception_handler(MagicMock(), ConnectorContextException("unexpected"))
    assert response.status_code == 500
    assert b"unexpected" in response.body
