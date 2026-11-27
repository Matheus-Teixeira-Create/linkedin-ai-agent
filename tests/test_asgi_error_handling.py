"""Testes do limite ASGI contra propagação de falhas e cancelamentos."""

import asyncio
from concurrent.futures import CancelledError as FutureCancelledError

from fastapi.testclient import TestClient
import pytest

from app.main import SafeFastAPI


def test_asgi_wrapper_does_not_swallow_task_cancellation() -> None:
    app = SafeFastAPI()

    @app.get("/cancel")
    async def cancel_request() -> None:
        raise asyncio.CancelledError

    with TestClient(app) as client:
        with pytest.raises(FutureCancelledError):
            client.get("/cancel")
