# tests/integration/test_joat_pipeline.py

import asyncio
import pytest
import random
import time

from market_data.orderbook import OrderBook
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from alpha_scoring.AlphaBlender import AlphaBlender
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine
from dynamic_risk_engine.performance_tracker import PerformanceTracker
from dynamic_risk_engine.throttle_cooldown_manager import ThrottleCooldownManager
from Execution_layer.execution_coordinator import ExecutionCoordinator
from Execution_layer.binance_adapter import BinanceExecutionAdapter
from Execution_layer.adaptive_sl_tp import AdaptiveSLTP
from cancel_window.simple_cancel_window import SimpleCancelWindow

# -----------------------------
# Fixture: Initialize full system
# -----------------------------
@pytest.fixture
def joat_system():
    orderbook = OrderBook()
    alpha_blender = AlphaBlender()
    alpha_pipeline = AlphaSignalPipeline(alpha_blender)
    
    perf_tracker = PerformanceTracker()
    throttle_mgr = ThrottleCooldownManager()
    risk_engine = DynamicRiskEngine(
        performance_tracker=perf_tracker,
        throttle_manager=throttle_mgr
    )
    
    execution_adapter = BinanceExecutionAdapter(api_key="test", secret_key="test")
    execution_coordinator = ExecutionCoordinator(
        execution_adapter=execution_adapter,
        risk_engine=risk_engine,
        alpha_pipeline=alpha_pipeline
    )
    
    sl_tp_manager = AdaptiveSLTP()
    spoof_detector = SimpleCancelWindow()
    
    return {
        "orderbook": orderbook,
        "alpha_pipeline": alpha_pipeline,
        "risk_engine": risk_engine,
        "execution_coordinator": execution_coordinator,
        "sl_tp_manager": sl_tp_manager,
        "spoof_detector": spoof_detector
    }

# -----------------------------
# Helper: Generate synthetic L2 events
# -----------------------------
def generate_l2_events(n_events=50):
    events = []
    base_price = 100.0
    for _ in range(n_events):
        price = base_price + random.uniform(-0.5, 0.5)
        size = random.uniform(0.1, 5.0)
        side = random.choice(["buy", "sell"])
        event_type = random.choices(["new", "cancel", "fill"], weights=[0.6, 0.2, 0.2])[0]
        events.append({
            "timestamp": time.time(),
            "price": price,
            "size": size,
            "side": side,
            "type": event_type
        })
    return events

# -----------------------------
# Main integration test
# -----------------------------
@pytest.mark.asyncio
async def test_full_pipeline(joat_system):
    ob = joat_system["orderbook"]
    alpha = joat_system["alpha_pipeline"]
    risk = joat_system["risk_engine"]
    exec_coord = joat_system["execution_coordinator"]
    sl_tp = joat_system["sl_tp_manager"]
    spoof = joat_system["spoof_detector"]
    
    events = generate_l2_events(100)
    
    for e in events:
        # Update OrderBook
        ob.process_l2_update(e)
        
        # Feed event into spoof detector
        if e["type"] == "cancel":
            spoof.register_cancel(e)
        
        # Feed event into alpha pipeline
        alpha.process_event(e)
        
        # Get blended alpha signal
        signal = alpha.get_signal()
        
        # Check if risk allows order
        position_size = risk.get_position_size(signal)
        
        # Execute order if allowed
        if position_size > 0:
            await exec_coord.execute(signal, position_size)
            
            # Update SL/TP based on simulated fills
            sl_tp.monitor_and_adjust(exec_coord.current_positions)
        
        # Assertions for integration correctness
        # ------------------------------
        # 1. Alpha score must be finite
        assert signal is not None
        assert isinstance(signal, float)
        
        # 2. Risk sizing matches limits
        max_size = risk.max_position_per_trade
        assert 0 <= position_size <= max_size
        
        # 3. SL/TP levels are reasonable relative to price
        for pos in exec_coord.current_positions.values():
            assert pos["sl"] <= pos["entry_price"] <= pos["tp"]
        
        # 4. Spoof detector maintains internal state
        assert spoof.get_cancel_density() >= 0

# -----------------------------
# Optional: Stress test
# -----------------------------
@pytest.mark.asyncio
async def test_pipeline_stress(joat_system):
    events = generate_l2_events(500)
    alpha = joat_system["alpha_pipeline"]
    risk = joat_system["risk_engine"]
    
    for e in events:
        alpha.process_event(e)
        signal = alpha.get_signal()
        position_size = risk.get_position_size(signal)
        # Ensure risk never allows oversize positions
        assert position_size <= risk.max_position_per_trade
