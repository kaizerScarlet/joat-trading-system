import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapter
from Execution_layer.binance_adapter_protocol import BinanceExecutionAdapterProtocol

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
    b : BinanceExecutionAdapterProtocol = BinanceExecutionAdapter("APIKEY", "SECRET")
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


@pytest.mark.asyncio
async def test_place_stop_loss_order_format(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"status": "NEW", "type": "STOP_LOSS_LIMIT"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    resp = await adapter.place_stop_loss_order("BTCUSDT", "SELL", stop_price=45000.0, quantity=0.01)
    assert resp["status"] == "NEW"
    assert resp["type"] == "STOP_LOSS_LIMIT"
    adapter.throttle.record_order.assert_called_once()


@pytest.mark.asyncio
async def test_place_take_profit_order_format(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"status": "NEW", "type": "LIMIT"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    resp = await adapter.place_take_profit_order("BTCUSDT", "SELL", take_profit_price=47000.0, quantity=0.01)
    assert resp["status"] == "NEW"
    assert resp["type"] == "LIMIT"
    adapter.throttle.record_order.assert_called_once()


@pytest.mark.asyncio
async def test_modify_order_cancel_replace(adapter):
    cancel_resp = MockAiohttpResponseCM(status=200, json_data={"status": "CANCELED"})
    place_resp = MockAiohttpResponseCM(status=200, json_data={"orderId": 999, "status": "NEW"})

    adapter._get_session = AsyncMock(return_value=make_mock_session(cancel_resp))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    # Patch place_order to return mock response
    adapter.place_order = AsyncMock(return_value={"orderId": 999, "status": "NEW"})

    result = await adapter.modify_order(symbol="BTCUSDT", orig_order_id=123, new_price=46000.0, new_qty=0.01)
    assert result["status"] == "replaced"
    assert result["new_order"]["orderId"] == 999


@pytest.mark.asyncio
async def test_handle_user_event_triggers_fill_callback(adapter):
    fill_event = {
        "e": "executionReport",
        "E": 1690000000000,
        "s": "BTCUSDT",
        "S": "BUY",
        "x": "TRADE",
        "X": "FILLED",
        "i": 12345,
        "l": "0.01",
        "L": "45000.0"
    }

    mock_callback = AsyncMock()
    adapter.on_fill_callback = mock_callback

    await adapter.handle_user_event(fill_event)
    mock_callback.assert_awaited_once()
    args = mock_callback.call_args[0][0]
    assert args["qty"] == 0.01
    assert args["price"] == 45000.0
    assert args["symbol"] == "BTCUSDT"
