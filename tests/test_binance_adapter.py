import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from Execution_layer.binance_adapter import BinanceExecutionAdapter

pytestmark = pytest.mark.asyncio

# -------------------------------
# Mock aiohttp Response
# -------------------------------
class MockAiohttpResponse:
    def __init__(self, status=200, json_data=None, text_data=None):
        self.status = status
        self._json_data = json_data or {}
        self._text_data = text_data or "{}"

    async def text(self):
        return self._text_data

    async def json(self):
        return self._json_data

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        pass

# -------------------------------
# Fixtures
# -------------------------------
@pytest.fixture
def adapter():
    a = BinanceExecutionAdapter(
        api_key="test_key",
        api_secret="test_secret",
        base_url="https://api.test.com"
    )
    a.throttle = MagicMock()
    a.throttle.is_throttled = MagicMock(return_value=False)
    a.throttle.record_order = MagicMock()
    a.throttle.record_cancel = MagicMock()
    return a

# -------------------------------
# Tests
# -------------------------------

# HMAC signing correctness
def test_signature_generation(adapter):
    params = {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": 1, "timestamp": 1234567890}
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    expected_sig = hmac.new(
        adapter.api_secret.encode("utf-8"),
        query_string.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    sig = adapter._sign_params(params)
    assert sig == expected_sig

# Normal signed GET request
@pytest.mark.asyncio
async def test_signed_request_success(adapter):
    adapter.session = AsyncMock()
    adapter.session.request.return_value = MockAiohttpResponse(
        status=200, json_data={"ok": True}
    )
    resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})
    assert resp["ok"] is True
    adapter.session.request.assert_awaited_once()

# Throttle: skip request if is_throttled True
@pytest.mark.asyncio
async def test_signed_request_respects_throttle(adapter):
    adapter.throttle.is_throttled.return_value = True
    adapter.session = AsyncMock()

    with pytest.raises(RuntimeError) as excinfo:
        await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})
    assert "throttled" in str(excinfo.value).lower()
    adapter.session.request.assert_not_called()

# Retry on 429
@pytest.mark.asyncio
async def test_signed_request_retries_on_429(adapter):
    adapter.session = AsyncMock()
    adapter.session.request.side_effect = [
        MockAiohttpResponse(status=429, json_data={"msg": "Rate limit"}),
        MockAiohttpResponse(status=200, json_data={"ok": True}),
    ]

    with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})

    assert resp["ok"] is True
    sleep_mock.assert_awaited()
    assert adapter.session.request.call_count == 2

# Retry on 418
@pytest.mark.asyncio
async def test_signed_request_retries_on_418(adapter):
    adapter.session = AsyncMock()
    adapter.session.request.side_effect = [
        MockAiohttpResponse(status=418, json_data={"msg": "IP banned"}),
        MockAiohttpResponse(status=200, json_data={"ok": True}),
    ]

    with patch("asyncio.sleep", new=AsyncMock()) as sleep_mock:
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "BTCUSDT"})

    assert resp["ok"] is True
    sleep_mock.assert_awaited()
    assert adapter.session.request.call_count == 2

# place_order triggers throttle.record_order
@pytest.mark.asyncio
async def test_place_order_records_throttle(adapter):
    adapter.session = AsyncMock()
    adapter.session.request.return_value = MockAiohttpResponse(
        status=200, json_data={"orderId": 1, "status": "NEW"}
    )

    resp = await adapter.place_order("BTCUSDT", "MARKET", 1)
    assert resp["orderId"] == 1
    adapter.throttle.record_order.assert_called_once()

# cancel_order triggers throttle.record_cancel
@pytest.mark.asyncio
async def test_cancel_order_records_throttle(adapter):
    adapter.session = AsyncMock()
    adapter.session.request.return_value = MockAiohttpResponse(
        status=200, json_data={"status": "CANCELED"}
    )

    resp = await adapter.cancel_order("BTCUSDT", orderId=1)
    assert resp["status"] == "CANCELED"
    adapter.throttle.record_cancel.assert_called_once()
