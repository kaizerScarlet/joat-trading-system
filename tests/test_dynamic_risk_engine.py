import time
import pytest 
from dynamic_risk_engine.dynamic_risk_engine import DynamicRiskEngine

def test_initial_state():

    engine =  DynamicRiskEngine(initial_balance=100000.0, max_risk_per_trade=0.02, daily_drawdown_limit=0.25)

    diagnostic = engine.get_diagnostic()

    assert diagnostic['can_trade'] is True
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False
    assert diagnostic['position_size_for_1_sl'] > 0
    assert diagnostic['current_confidence'] == 0.5
    assert diagnostic['current_win_rate'] == 0.0
    assert diagnostic['average_rrr'] == 0.0
    assert diagnostic['equity_curve'] == []


def test_register_trade_win_updates_all_modules():
    engine = DynamicRiskEngine(initial_balance=1000, max_risk_per_trade=0.02, daily_drawdown_limit=0.25)

    engine.register_trade(
        pnl = 100.0,
        risk = 50.0,
        reward = 150,
        signal_id = "signal_1",
        was_correct=True,
        metadata={"strategy": "test_strategy"}
    )

    diagnostic = engine.get_diagnostic()

    assert diagnostic['current_win_rate'] == 1.0
    assert diagnostic['current_confidence'] == 1.0
    assert diagnostic['equity_curve'][-1] == 100.0
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False




def test_register_trade_loss_and_cooldown_triggered():
    engine = DynamicRiskEngine(initial_balance=1000, max_risk_per_trade=0.02, daily_drawdown_limit=0.25)

    engine.register_trade(
        pnl = -50.0,
        risk = 50.0,
        reward = 100,
        signal_id = "signal_2",
        was_correct=False,      

    )

    engine.register_trade(
        pnl = -30.0,
        risk = 50.0,
        reward = 100,
        signal_id = "signal_3",
        was_correct=False,      
    )

    engine.register_trade(
        pnl = -70.0,
        risk = 50.0,
        reward = 100,
        signal_id = "signal_4",
        was_correct=False,
    )


    diagnostic = engine.get_diagnostic()

    assert diagnostic['cooldown_active'] is True
    assert engine.can_trade() is False




def test_position_size_scaling():
    engine = DynamicRiskEngine(initial_balance=1000, max_risk_per_trade=0.01, daily_drawdown_limit=0.25)

    #Record 3 good trades to raise confidence + win rate
    engine.register_trade(
        pnl = 100.0,
        risk = 50.0,
        reward = 100,
        signal_id = "signal_5",
        was_correct=True,
        metadata={"strategy": "test_strategy"}
    )

    engine.register_trade(
        pnl = 150.0,
        risk = 50.0,
        reward = 120,
        signal_id = "signal_6",
        was_correct=True,
        metadata={"strategy": "test_strategy"}
    )

    engine.register_trade(
        pnl = 200.0,
        risk = 50.0,
        reward = 130,
        signal_id = "signal_7",
        was_correct=True,
        metadata={"strategy": "test_strategy"}
    )   



    position_size = engine.get_position_size(stop_loss_distance=5)

    #Because confidence and win rate have risen, position size should grow
    assert position_size > 1.0  # Should be able to calculate a position size


def test_engine_reset():
    engine = DynamicRiskEngine(initial_balance=500, max_risk_per_trade=0.05, daily_drawdown_limit=0.25)
    engine.register_trade(
        pnl = -100.0,
        risk = 50.0,
        reward = 100,
        signal_id = "signal_8",
        was_correct=False,
    )


    engine.reset()
    diagnostic = engine.get_diagnostic()

    assert diagnostic['current_win_rate'] == 0.0
    assert diagnostic['equity_curve'] == []
    assert diagnostic['drawdown_triggered'] is False
    assert diagnostic['cooldown_active'] is False
    assert diagnostic['position_size_for_1_sl'] > 0  # Should be able to calculate position size again


    