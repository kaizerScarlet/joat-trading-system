import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from Execution_layer.binance_adapter import BinanceExecutionAdapter

# ------------------------------
# Mock aiohttp-like response
# ------------------------------
class MockAiohttpResponseCM:
    def __init__(self, status=200, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data or {}
        self._text_data = text_data or str(json_data)

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


# ------------------------------
# Deterministic signature helper
# ------------------------------
def deterministic_sign(adapter, query):
    return "TESTSIGNATURE"


# ------------------------------
# Fixture for adapter
# ------------------------------
@pytest.fixture
def adapter():
    b = BinanceExecutionAdapter("APIKEY", "SECRET")
    b.throttle = MagicMock()
    b.throttle.is_throttled = MagicMock(return_value=False)  # ✅ allow requests by default
    b.throttle.record_order = MagicMock()
    b.throttle.record_cancel = MagicMock()
    return b


# ------------------------------
# Session mock factory
# ------------------------------
def make_mock_session(mock_response):
    """Return a session whose request returns an async context manager yielding mock_response."""
    mock_ctx = MagicMock()
    mock_ctx.__aenter__.return_value = mock_response
    mock_ctx.__aexit__.return_value = None
    mock_session = MagicMock()
    mock_session.request.return_value = mock_ctx
    return mock_session


# ✅ Test 1: Successful signed request
@pytest.mark.asyncio
async def test_signed_request_success(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"ok": True})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})
    assert resp == {"ok": True}
    adapter.throttle.record_order.assert_called_once()


# ✅ Test 2: Retry on 429
@pytest.mark.asyncio
async def test_signed_request_retries_on_429(adapter):
    ctx429 = MockAiohttpResponseCM(status=429, json_data={"msg": "Rate limit"})
    ctx200 = MockAiohttpResponseCM(status=200, json_data={"ok": True})

    call_counter = {"count": 0}

    def side_effect(*args, **kwargs):
        mock_ctx = MagicMock()
        if call_counter["count"] == 0:
            mock_ctx.__aenter__.return_value = ctx429
            call_counter["count"] += 1
        else:
            mock_ctx.__aenter__.return_value = ctx200
        mock_ctx.__aexit__.return_value = None
        return mock_ctx

    mock_session = MagicMock()
    mock_session.request.side_effect = side_effect

    adapter._get_session = AsyncMock(return_value=mock_session)
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})
        assert resp == {"ok": True}
        mock_sleep.assert_called_once()
        adapter.throttle.record_order.assert_called_once()


# ✅ Test 3: Retry on 418
@pytest.mark.asyncio
async def test_signed_request_retries_on_418(adapter):
    ctx418 = MockAiohttpResponseCM(status=418, json_data={"msg": "IP banned"})
    ctx200 = MockAiohttpResponseCM(status=200, json_data={"ok": True})

    call_counter = {"count": 0}

    def side_effect(*args, **kwargs):
        mock_ctx = MagicMock()
        if call_counter["count"] == 0:
            mock_ctx.__aenter__.return_value = ctx418
            call_counter["count"] += 1
        else:
            mock_ctx.__aenter__.return_value = ctx200
        mock_ctx.__aexit__.return_value = None
        return mock_ctx

    mock_session = MagicMock()
    mock_session.request.side_effect = side_effect

    adapter._get_session = AsyncMock(return_value=mock_session)
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    with patch("asyncio.sleep", new=AsyncMock()) as mock_sleep:
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})
        assert resp == {"ok": True}
        mock_sleep.assert_called_once()
        adapter.throttle.record_order.assert_called_once()


# ✅ Test 4: Error response (400 Bad Request)
@pytest.mark.asyncio
async def test_signed_request_raises_on_error(adapter):
    mock_response = MockAiohttpResponseCM(status=400, json_data={"msg": "Bad Request"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    with pytest.raises(RuntimeError, match="Binance API Error 400"):
        await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})


# ✅ Test 5: place_order throttle recording
@pytest.mark.asyncio
async def test_place_order_records_throttle(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"orderId": 1, "status": "NEW"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    resp = await adapter.place_order("BTCUSDT", "BUY", quantity=1)
    assert resp["status"] == "NEW"
    adapter.throttle.record_order.assert_called_once()


# ✅ Test 6: cancel_order throttle recording
@pytest.mark.asyncio
async def test_cancel_order_records_throttle(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"status": "CANCELED"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    resp = await adapter.cancel_order("BTCUSDT", orderId=1)
    assert resp["status"] == "CANCELED"
    adapter.throttle.record_cancel.assert_called_once()
