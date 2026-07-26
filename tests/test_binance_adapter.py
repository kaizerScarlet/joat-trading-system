import pytest
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from Execution_layer.binance_adapter import BinanceExecutionAdapter
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

    resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "SOLUSDT"})
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
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "SOLUSDT"})
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
        resp = await adapter._signed_request("GET", "/api/v3/order", {"symbol": "SOLUSDT"})
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
        await adapter._signed_request("GET", "/api/v3/order", {"symbol": "SOLUSDT"})


# ✅ Test 5: place_order throttle recording







# Add this helper at the top of your test file
from Execution_layer.symbol_info_manager import SymbolFilters

def create_mock_symbol_info():
    """Create a mock SymbolFilters instance for testing"""
    return SymbolFilters(
        symbol="SOLUSDT",
        base_asset="SOL",
        quote_asset="USDT",
        contract_type="PERPETUAL",
        min_price=0.01,
        max_price=1000000.0,
        tick_size=0.1,
        min_qty=0.001,
        max_qty=10000.0,
        step_size=0.001,
        min_notional=100.0,
        market_min_qty=0.001,
        market_max_qty=10000.0,
        market_step_size=0.001,
        multiplier_up=10.0,
        multiplier_down=0.1
    )

# Then update your failing tests:

@pytest.mark.asyncio
async def test_place_order_records_throttle(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"orderId": 1, "status": "NEW"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    # Mock symbol info initialization
    adapter._symbol_info = create_mock_symbol_info()
    adapter.initialize_symbol_info = AsyncMock(return_value=adapter._symbol_info)

    resp = await adapter.place_order("SOLUSDT", "BUY", quantity=1)
    assert resp["status"] == "NEW"
    assert adapter.throttle.record_order.call_count >= 1


@pytest.mark.asyncio
async def test_place_stop_loss_order_format(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"orderId": 12345, "status": "NEW"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    # Mock symbol info
    adapter._symbol_info = create_mock_symbol_info()
    adapter.initialize_symbol_info = AsyncMock(return_value=adapter._symbol_info)

    sl_params = {
        "stop_price": 45000.0,
        "reduce_only": True,
        "position_side": "BOTH",
        "working_type": "MARK_PRICE",
        "close_position": False,
    }

    resp = await adapter.place_order(
        symbol="SOLUSDT",
        side="BUY",
        type="MARKET",
        quantity=0.01,
        stop_loss=45000.0,
        sl_params=sl_params
    )
    assert resp["status"] == "NEW"
    assert adapter.throttle.record_order.call_count >= 1


@pytest.mark.asyncio
async def test_place_take_profit_order_format(adapter):
    mock_response = MockAiohttpResponseCM(status=200, json_data={"orderId": 12346, "status": "NEW"})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    # Mock symbol info
    adapter._symbol_info = create_mock_symbol_info()
    adapter.initialize_symbol_info = AsyncMock(return_value=adapter._symbol_info)

    tp_params = {
        "stop_price": 47000.0,
        "reduce_only": True,
        "position_side": "BOTH",
        "working_type": "MARK_PRICE",
        "close_position": False,
    }

    resp = await adapter.place_order(
        symbol="SOLUSDT",
        side="BUY",
        type="MARKET",
        quantity=0.01,
        take_profit=47000.0,
        tp_params=tp_params
    )
    assert resp["status"] == "NEW"
    assert adapter.throttle.record_order.call_count >= 1


@pytest.mark.asyncio
async def test_place_order_futures_with_reduce_only_and_sl_tp():
    mock_response = MockAiohttpResponseCM(status=200, json_data={"orderId": 10, "status": "NEW"})
    adapter = BinanceExecutionAdapter(
        throttle=MagicMock(),
        api_key="APIKEY",
        api_secret="SECRET",
        market_type="futures",
        base_url="https://testnet.binancefuture.com"
    )
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: "TESTSIGNATURE"
    adapter.throttle.is_throttled = MagicMock(return_value=False)
    adapter.throttle.record_order = MagicMock()

    # Mock symbol info
    adapter._symbol_info = create_mock_symbol_info()
    adapter.initialize_symbol_info = AsyncMock(return_value=adapter._symbol_info)

    resp = await adapter.place_order(
        symbol="SOLUSDT",
        side="SELL",
        type="LIMIT",
        quantity=0.5,
        price=50000.0,
        stop_loss=49000.0,
        take_profit=51000.0,
        reduce_only=True,
        position_side="SHORT"
    )
    assert resp["marketType"] == "futures"
    assert adapter.throttle.record_order.call_count >= 1






@pytest.mark.asyncio
async def test_modify_order_cancel_replace(adapter):
    cancel_resp = MockAiohttpResponseCM(status=200, json_data={"status": "CANCELED"})
    place_resp = MockAiohttpResponseCM(status=200, json_data={"orderId": 999, "status": "NEW"})

    adapter._get_session = AsyncMock(return_value=make_mock_session(cancel_resp))
    adapter._sign = lambda q: deterministic_sign(adapter, q)

    # Patch place_order to return mock response
    adapter.place_order = AsyncMock(return_value={"orderId": 999, "status": "NEW"})

    result = await adapter.modify_order(symbol="SOLUSDT", orig_order_id=123, new_price=46000.0, new_qty=0.01)
    assert result["status"] == "replaced"
    assert result["new_order"]["orderId"] == 999


@pytest.mark.asyncio
async def test_handle_user_event_triggers_fill_callback(adapter):
    fill_event = {
        "e": "executionReport",
        "E": 1690000000000,
        "s": "SOLUSDT",
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
    assert args["symbol"] == "SOLUSDT"






# ✅ FIXED Test 12: Base URL is locked to testnet
@pytest.mark.asyncio
async def test_get_endpoint_and_base_url():
    """Verify endpoint routing and testnet URL locking."""
    adapter = BinanceExecutionAdapter(
        throttle=MagicMock(),
        api_key="A",
        api_secret="B",
        market_type="futures",
        base_url="https://testnet.binancefuture.com"
    )
    # Futures endpoint should start with /fapi/
    assert adapter._get_endpoint("place").startswith("/fapi/")
    
    # Spot endpoint should start with /api/
    adapter.market_type = "spot"
    assert adapter._get_endpoint("place").startswith("/api/")
    
    # The adapter is LOCKED to testnet, so base_url should contain "testnet"
    adapter._set_base_url()
    assert "testnet" in adapter.base_url.lower()


@pytest.mark.asyncio
async def test_sync_server_time_calculates_offset():
    """Ensure time sync computes offset correctly."""
    adapter = BinanceExecutionAdapter(MagicMock(), api_key="A", api_secret="B")
    mock_response = MockAiohttpResponseCM(status=200, json_data={"serverTime": int(time.time() * 1000) + 500})
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))

    result = await adapter.sync_server_time()
    assert isinstance(result, int)
    assert hasattr(adapter, "time_offset_ms")


@pytest.mark.asyncio
async def test_get_open_positions_returns_filtered_positions():
    """Ensure futures positions are filtered and normalized."""
    adapter = BinanceExecutionAdapter(MagicMock(), api_key="A", api_secret="B", market_type="futures")
    adapter.throttle.is_throttled = MagicMock(return_value=False)

    data = [
        {"symbol": "SOLUSDT", "positionAmt": "0.5", "entryPrice": "50000", "unRealizedProfit": "100"},
        {"symbol": "ETHUSDT", "positionAmt": "0.0", "entryPrice": "0", "unRealizedProfit": "0"}
    ]
    mock_response = MockAiohttpResponseCM(status=200, json_data=data)
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: "TESTSIGNATURE"

    positions = await adapter.get_open_positions(symbol="SOLUSDT")
    assert len(positions) == 1
    assert positions[0]["symbol"] == "SOLUSDT"


@pytest.mark.asyncio
async def test_modify_order_sl_tp_creates_new_orders():
    """Ensure SL/TP modify creates new stop/take-profit orders."""
    adapter = BinanceExecutionAdapter(MagicMock(), api_key="A", api_secret="B", market_type="futures")
    adapter.get_open_orders = AsyncMock(return_value=[])
    adapter._signed_request = AsyncMock(return_value={"ok": True})

    # Mock symbol_info_manager so no real API call is made
    mock_info = MagicMock()
    mock_info.tick_size = 0.01
    mock_info.step_size = 0.001
    mock_info.min_qty = 0.001
    mock_info.min_notional = 5.0
    adapter.symbol_info_manager = AsyncMock()
    adapter.symbol_info_manager.get_symbol_info = AsyncMock(return_value=mock_info)

    resp = await adapter.modify_order_sl_tp("SOLUSDT", stop_loss=49000.0, take_profit=51000.0, position_side="LONG")
    assert "stop_loss" in resp and "take_profit" in resp


@pytest.mark.asyncio
async def test_get_open_orders_and_get_order_status(adapter):
    """Ensure open orders and status endpoints respond properly."""
    # Mock for get_open_orders - returns a list
    mock_open_orders_response = MockAiohttpResponseCM(status=200, json_data=[{"symbol": "SOLUSDT"}])
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_open_orders_response))
    adapter._sign = lambda q: "TESTSIGNATURE"

    result = await adapter.get_open_orders(symbol="SOLUSDT")
    assert isinstance(result, list)

    # Mock for get_order_status - returns a dict
    mock_order_status_response = MockAiohttpResponseCM(
        status=200, 
        json_data={
            "orderId": 1,
            "symbol": "SOLUSDT",
            "status": "FILLED",
            "origClientOrderId": "test_order_123",
            "executedQty": "10.0",
            "origQty": "10.0"
        }
    )
    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_order_status_response))
    status = await adapter.get_order_status(symbol="SOLUSDT", orderId=1)
    assert isinstance(status, dict)
    assert status["orderId"] == 1
    assert status["symbol"] == "SOLUSDT"


@pytest.mark.asyncio
async def test_get_account_balance_handles_assets_field():
    """Ensure get_account_balance works with 'assets' field in futures."""
    account_data = {"assets": [{"asset": "USDT", "availableBalance": "123.45"}]}
    mock_response = MockAiohttpResponseCM(status=200, json_data=account_data)
    adapter = BinanceExecutionAdapter(MagicMock(), api_key="A", api_secret="B", market_type="futures")
    adapter.throttle.is_throttled = MagicMock(return_value=False)

    adapter._get_session = AsyncMock(return_value=make_mock_session(mock_response))
    adapter._sign = lambda q: "TESTSIGNATURE"

    balance = await adapter.get_account_balance()
    assert isinstance(balance, float)
    assert balance > 0


"""
Extension tests for Execution_layer/binance_adapter.py
Covers paths missing from the original test_binance_adapter.py:

  cancel_order          : by orderId, by origClientOrderId, throttle recorded
  cancel_order_by_id    : success path, fallback to algo-cancel on failure
  round_price           : with/without symbol_info loaded
  round_quantity        : with/without symbol_info loaded
  handle_user_event     : ACCOUNT_UPDATE balance cache, ORDER_TRADE_UPDATE fill,
                          zero-qty (no callback), unknown event type
  get_open_positions    : spot market returns empty list
  _set_base_url         : spot-testnet, spot-mainnet, futures-mainnet
  _request              : 500 server error raises RuntimeError
  close                 : session teardown; idempotent second call
  get_account           : delegates to _signed_request with correct endpoint
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from Execution_layer.binance_adapter import BinanceExecutionAdapter


# ─────────────────────────────────────────────
# Shared helpers
# ─────────────────────────────────────────────
class MockAiohttpResponseCM:
    def __init__(self, status=200, json_data=None, text_data=""):
        self.status = status
        self._json_data = json_data if json_data is not None else {}
        self._text_data = text_data or str(json_data)

    async def json(self):
        return self._json_data

    async def text(self):
        return self._text_data


def make_mock_session(mock_response):
    mock_ctx = MagicMock()
    mock_ctx.__aenter__.return_value = mock_response
    mock_ctx.__aexit__.return_value = None
    mock_session = MagicMock()
    mock_session.request.return_value = mock_ctx
    return mock_session


def make_adapter(market_type="futures", base_url=None):
    kwargs = dict(throttle=MagicMock(), api_key="A", api_secret="B", market_type=market_type)
    if base_url:
        kwargs["base_url"] = base_url
    adapter = BinanceExecutionAdapter(**kwargs)
    adapter.throttle.is_throttled = MagicMock(return_value=False)
    adapter.throttle.record_order  = MagicMock()
    adapter.throttle.record_cancel = MagicMock()
    return adapter


# ─────────────────────────────────────────────
# cancel_order
# ─────────────────────────────────────────────
class TestCancelOrder:
    @pytest.mark.asyncio
    async def test_cancel_by_order_id(self):
        adapter = make_adapter()
        adapter._signed_request = AsyncMock(return_value={"status": "CANCELED"})

        resp = await adapter.cancel_order(symbol="SOLUSDT", orderId=12345)
        assert resp == {"status": "CANCELED"}
        call_kwargs = adapter._signed_request.call_args
        assert call_kwargs[0][0] == "DELETE"  # method
        assert 12345 in call_kwargs[0][2].values()  # orderId in payload

    @pytest.mark.asyncio
    async def test_cancel_by_client_order_id(self):
        adapter = make_adapter()
        adapter._signed_request = AsyncMock(return_value={"status": "CANCELED"})

        resp = await adapter.cancel_order(symbol="SOLUSDT", origClientOrderId="my_order_1")
        assert resp["status"] == "CANCELED"
        payload = adapter._signed_request.call_args[0][2]
        assert payload.get("origClientOrderId") == "my_order_1"

    @pytest.mark.asyncio
    async def test_cancel_records_throttle(self):
        adapter = make_adapter()
        adapter._signed_request = AsyncMock(return_value={})

        await adapter.cancel_order(symbol="SOLUSDT", orderId=999)
        adapter.throttle.record_cancel.assert_called_once()


# ─────────────────────────────────────────────
# cancel_order_by_id
# ─────────────────────────────────────────────
class TestCancelOrderById:
    @pytest.mark.asyncio
    async def test_cancel_by_id_success(self):
        adapter = make_adapter()
        adapter.cancel_order = AsyncMock(return_value={"status": "CANCELED"})

        resp = await adapter.cancel_order_by_id("SOLUSDT", "12345")
        adapter.cancel_order.assert_called_once_with(symbol="SOLUSDT", orderId=12345)
        assert resp["status"] == "CANCELED"

    @pytest.mark.asyncio
    async def test_cancel_by_id_falls_back_to_algo_cancel(self):
        """If regular cancel_order raises, cancel_order_by_id should try cancel_algo_order."""
        adapter = make_adapter()
        adapter.cancel_order = AsyncMock(side_effect=RuntimeError("not found"))
        adapter.cancel_algo_order = AsyncMock(return_value={"algoStatus": "CANCELED"})

        resp = await adapter.cancel_order_by_id("SOLUSDT", "algo_99")
        adapter.cancel_algo_order.assert_called_once_with("SOLUSDT", "algo_99")
        assert resp["algoStatus"] == "CANCELED"


# ─────────────────────────────────────────────
# round_price / round_quantity
# ─────────────────────────────────────────────
class TestRounding:
    def test_round_price_without_symbol_info_falls_back_to_2dp(self):
        adapter = make_adapter()
        adapter._symbol_info = None
        result = adapter.round_price(100.12345)
        assert result == round(100.12345, 2)

    def test_round_quantity_without_symbol_info_falls_back_to_6dp(self):
        adapter = make_adapter()
        adapter._symbol_info = None
        result = adapter.round_quantity(0.123456789)
        assert result == round(0.123456789, 6)

    def test_round_price_delegates_to_symbol_info(self):
        adapter = make_adapter()
        mock_info = MagicMock()
        mock_info.round_price.return_value = 100.12
        adapter._symbol_info = mock_info
        result = adapter.round_price(100.12345)
        mock_info.round_price.assert_called_once_with(100.12345)
        assert result == 100.12

    def test_round_quantity_delegates_to_symbol_info(self):
        adapter = make_adapter()
        mock_info = MagicMock()
        mock_info.round_quantity.return_value = 0.123
        adapter._symbol_info = mock_info
        result = adapter.round_quantity(0.12345, order_type="LIMIT")
        mock_info.round_quantity.assert_called_once_with(0.12345, "LIMIT")
        assert result == 0.123


# ─────────────────────────────────────────────
# handle_user_event
# ─────────────────────────────────────────────
class TestHandleUserEvent:
    @pytest.mark.asyncio
    async def test_account_update_pushes_to_balance_cache(self):
        adapter = make_adapter()
        adapter.balance_cache = MagicMock()

        event = {
            "e": "ACCOUNT_UPDATE",
            "a": {"B": [{"a": "USDT", "wb": "1234.56"}]},
        }
        await adapter.handle_user_event(event)
        adapter.balance_cache.update_from_ws.assert_called_once_with(1234.56)

    @pytest.mark.asyncio
    async def test_account_update_ignores_non_usdt_assets(self):
        adapter = make_adapter()
        adapter.balance_cache = MagicMock()

        event = {
            "e": "ACCOUNT_UPDATE",
            "a": {"B": [{"a": "BNB", "wb": "5.0"}]},
        }
        await adapter.handle_user_event(event)
        adapter.balance_cache.update_from_ws.assert_not_called()

    @pytest.mark.asyncio
    async def test_order_trade_update_triggers_fill_callback(self):
        adapter = make_adapter()
        callback = AsyncMock()
        adapter.on_fill_callback = callback

        event = {
            "e": "ORDER_TRADE_UPDATE",
            "E": 1700000000000,
            "o": {
                "x": "TRADE",
                "X": "FILLED",
                "l": "0.5",
                "L": "100.0",
                "i": 555,
                "si": 0,
                "s": "SOLUSDT",
                "S": "BUY",
            },
        }
        await adapter.handle_user_event(event)
        callback.assert_called_once()
        call_args = callback.call_args[0][0]
        assert call_args["qty"] == pytest.approx(0.5)
        assert call_args["price"] == pytest.approx(100.0)

    @pytest.mark.asyncio
    async def test_zero_qty_does_not_trigger_callback(self):
        adapter = make_adapter()
        callback = Mock()
        adapter.on_fill_callback = callback

        event = {
            "e": "executionReport",
            "o": {"x": "NEW", "X": "NEW", "l": "0.0", "L": "100.0"},
        }
        await adapter.handle_user_event(event)
        callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_unknown_event_type_does_not_raise(self):
        adapter = make_adapter()
        event = {"e": "SOME_FUTURE_EVENT_TYPE", "data": "irrelevant"}
        # Should complete without raising
        await adapter.handle_user_event(event)


# ─────────────────────────────────────────────
# get_open_positions — spot returns empty list
# ─────────────────────────────────────────────
class TestGetOpenPositionsSpot:
    @pytest.mark.asyncio
    async def test_spot_returns_empty_list(self):
        adapter = make_adapter(market_type="spot")
        positions = await adapter.get_open_positions(symbol="SOLUSDT")
        assert positions == []


# ─────────────────────────────────────────────
# _set_base_url
# ─────────────────────────────────────────────
class TestSetBaseUrl:
    def test_futures_mainnet(self):
        adapter = make_adapter(market_type="futures")
        adapter.base_url = "https://fapi.binance.com"  # already mainnet
        adapter._set_base_url()
        assert adapter.base_url == "https://fapi.binance.com"

    def test_futures_testnet_preserved(self):
        adapter = make_adapter(market_type="futures", base_url="https://testnet.binancefuture.com")
        adapter._set_base_url()
        assert "testnet" in adapter.base_url.lower()

    def test_spot_mainnet(self):
        adapter = make_adapter(market_type="spot")
        adapter.base_url = "https://api.binance.com"
        adapter._set_base_url()
        assert adapter.base_url == "https://api.binance.com"

    def test_spot_testnet_preserved(self):
        adapter = make_adapter(market_type="spot", base_url="https://testnet.binance.vision")
        adapter._set_base_url()
        assert "testnet" in adapter.base_url.lower()
        assert "binance.vision" in adapter.base_url.lower()

    def test_switch_from_futures_mainnet_to_spot_mainnet(self):
        adapter = make_adapter(market_type="futures")
        adapter.market_type = "spot"
        adapter._set_base_url()
        assert adapter.base_url == "https://api.binance.com"


# ─────────────────────────────────────────────
# _request  — 5xx error handling
# ─────────────────────────────────────────────
class TestRequestErrors:
    @pytest.mark.asyncio
    async def test_500_server_error_raises_runtime_error(self):
        adapter = make_adapter()
        error_response = MockAiohttpResponseCM(status=500, text_data="Internal Server Error")
        adapter._get_session = AsyncMock(return_value=make_mock_session(error_response))

        with pytest.raises(RuntimeError, match="500"):
            await adapter._request("GET", "/fapi/v1/ping")

    @pytest.mark.asyncio
    async def test_400_client_error_raises_runtime_error(self):
        adapter = make_adapter()
        error_response = MockAiohttpResponseCM(status=400, text_data='{"code":-1100,"msg":"Bad Request"}')
        adapter._get_session = AsyncMock(return_value=make_mock_session(error_response))

        with pytest.raises(RuntimeError, match="400"):
            await adapter._request("GET", "/fapi/v1/order")


# ─────────────────────────────────────────────
# close
# ─────────────────────────────────────────────
class TestClose:
    @pytest.mark.asyncio
    async def test_close_marks_adapter_closed(self):
        adapter = make_adapter()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        adapter.session = mock_session
        adapter._closed = False

        await adapter.close()
        assert adapter._closed is True
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_idempotent(self):
        """Calling close twice must not raise or double-close the session."""
        adapter = make_adapter()
        mock_session = MagicMock()
        mock_session.closed = False
        mock_session.close = AsyncMock()
        adapter.session = mock_session
        adapter._closed = False

        await adapter.close()
        await adapter.close()  # second call
        mock_session.close.assert_called_once()  # session only closed once

    @pytest.mark.asyncio
    async def test_close_safe_when_session_already_closed(self):
        adapter = make_adapter()
        mock_session = MagicMock()
        mock_session.closed = True  # already closed
        mock_session.close = AsyncMock()
        adapter.session = mock_session
        adapter._closed = False

        await adapter.close()
        mock_session.close.assert_not_called()


# ─────────────────────────────────────────────
# get_account
# ─────────────────────────────────────────────
class TestGetAccount:
    @pytest.mark.asyncio
    async def test_get_account_returns_response(self):
        adapter = make_adapter()
        expected = {"totalWalletBalance": "500.0", "assets": []}
        adapter._signed_request = AsyncMock(return_value=expected)

        result = await adapter.get_account()
        assert result == expected
        adapter._signed_request.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_account_uses_correct_endpoint_futures(self):
        adapter = make_adapter(market_type="futures")
        adapter._signed_request = AsyncMock(return_value={})

        await adapter.get_account()
        path_used = adapter._signed_request.call_args[0][1]
        assert path_used.startswith("/fapi/")

    @pytest.mark.asyncio
    async def test_get_account_uses_correct_endpoint_spot(self):
        adapter = make_adapter(market_type="spot")
        adapter._signed_request = AsyncMock(return_value={})

        await adapter.get_account()
        path_used = adapter._signed_request.call_args[0][1]
        assert path_used.startswith("/api/")