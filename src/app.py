import sys
import os
sys.path.append(os.path.dirname(__file__))

import streamlit as st
import pandas as pd

# System hooks
from runners.binance_cancel_window_runner import BinanceCancelWindowRunner, collect_debug_views
from narrator.mistral_narrator import build_prompt_from_debug_views, mistral_narrate

# Core modules
from cancel_window.simple_cancel_window import SimpleCancelWindow, CancelWindowTunerForLayering, CancelWindowTuner
from cancel_window.order_layering_detection import OrderLayeringDetection
from cancel_window.order_age_distribution import OrderAgeDistribution
from alpha_scoring.Order_layering_scorer import LayeringScoring
from alpha_scoring.order_age_scorer import OrderAgeDistributionScorer
from alpha_scoring.cancel_activity_scorer import CancelActivityScorer
from alpha_scoring.AlphaBlender import AlphaBlender
from alpha_scoring.alpha_pipeline import AlphaSignalPipeline
from market_data.orderbook import OrderBook
from dynamic_risk_engine.cognitive_market_regime_classifier import CognitiveMarketRegimeClassifier
from dynamic_risk_engine.signal_confidence_calibrator import SignalConfidenceCalibrator

# Spoof and iceberg modules
from cancel_window.order_laddering_detection import OrderLadderingDetection
from cancel_window.synthetic_fill_detector import SyntheticFillDetection
from cancel_window.order_spoofing_detection import OrderSpoofingDetection
from cancel_window.cancel_density_detection import CancelDensityDetection
from cancel_window.order_iceberg_detection import OrderIcebergDetection


from alpha_scoring.cancel_density_scorer import CancelDensityScorer
from alpha_scoring.order_laddering_scorer import LadderingScorer
from alpha_scoring.order_iceberg_scorer import IcebergScorer
from alpha_scoring.order_spoofing_scorer import SpoofingScorer
from alpha_scoring.synthetic_fill_scorer import SyntheticFillScorer




# === Instantiate core components ===
order_book = OrderBook()
signal_confidence_calibrator = SignalConfidenceCalibrator()

# Create placeholder cancel_window for classifier reference
cancel_window = SimpleCancelWindow(
    tuner=None,
    order_layering=None,
    order_ladder_tracker=None,
    synthetic_fill_detector=None,
    order_spoofing=None,
    order_cancel_density=None,
    order_iceberg_detection=None,
    order_age_tracker=None,
    cancel_density_threshold_bid=0.15,
    cancel_density_threshold_ask=0.15,
    cancel_density_window_ms=3000,
    order_book=order_book,
    classifier=None,
    market_type="spot"
)

# Instantiate classifier
classifier = CognitiveMarketRegimeClassifier(
    orderbook=order_book,
    signal_calibrator=signal_confidence_calibrator,
    cancel_window=cancel_window
)

# Instantiate spoof/iceberg modules with classifier
order_laddering_tracker = OrderLadderingDetection(regime_classifier=classifier)
synthetic_fill_detector = SyntheticFillDetection(regime_classifier=classifier)
order_spoofing_detector = OrderSpoofingDetection(regime_classifier=classifier)
cancel_density_detector = CancelDensityDetection(regime_classifier=classifier)
iceberg_detector = OrderIcebergDetection(regime_classifier=classifier)


# === Instantiate spoof/iceberg scorers ===
cancel_density_scorer = CancelDensityScorer(detector=cancel_density_detector)
order_ladder_scorer = LadderingScorer(detector=order_laddering_tracker)
iceberg_scorer = IcebergScorer(detector=iceberg_detector)
order_spoofing_scorer = SpoofingScorer(spoof_detector=order_spoofing_detector)
synthetic_fill_scorer = SyntheticFillScorer(detector=synthetic_fill_detector)

# Patch spoof modules into cancel_window
cancel_window.order_ladder_tracker = order_laddering_tracker
cancel_window.synthetic_fill_detector = synthetic_fill_detector
cancel_window.order_spoofing = order_spoofing_detector
cancel_window.order_cancel_density = cancel_density_detector
cancel_window.order_iceberg_detection = iceberg_detector
cancel_window.classifier = classifier

# Instantiate scoring modules
tunerforlayering = CancelWindowTunerForLayering(classifier=classifier)
order_layering_tracker = OrderLayeringDetection(regime_classifier=classifier, tuner=tunerforlayering)
tuner = CancelWindowTuner(classifier=classifier)
order_layering_score = LayeringScoring(layering_detector=order_layering_tracker)
order_age_tracker = OrderAgeDistribution(regime_classifier=classifier)
order_age_tracker_score = OrderAgeDistributionScorer(tracker=order_age_tracker, distribution_tracker=order_age_tracker)

# Patch scoring modules into cancel_window
cancel_window.tuner = tuner
cancel_window.order_layering = order_layering_tracker
cancel_window.order_age_tracker = order_age_tracker

# Now instantiate CancelActivityScorer (after tuner is patched)
cancel_activity_scorer = CancelActivityScorer(window_ms_tuner=cancel_window)

# Alpha signal pipeline
alpha_blender = AlphaBlender(
    weights={'cancel_activity': 0.5, 'layering': 0.3, 'order_age': 0.2},
    blending_method='weighted average',
    adaptive=True
)

alpha_signal_pipeline = AlphaSignalPipeline(
    cancel_scorer=cancel_activity_scorer,
    age_scorer=order_age_tracker_score,
    layering_scorer=order_layering_score,
    cancel_density_scorer=cancel_density_scorer,
    order_ladder_scorer=order_ladder_scorer,
    iceberg_scorer=iceberg_scorer,
    order_spoofing_scorer=order_spoofing_scorer,
    synthetic_fill_scorer=synthetic_fill_scorer,
    blender=alpha_blender
)


runner = BinanceCancelWindowRunner(
    alpha_blender=alpha_blender,
    alpha_signal_pipeline=alpha_signal_pipeline,
    cancel_activity_scorer=cancel_activity_scorer,
    order_layering_scorer=order_layering_score,
    order_age_scorer=order_age_tracker_score,
    cancel_window=cancel_window,
    orderbook=order_book,
)

# ✅ Patch spoof/iceberg scorers into runner
runner.cancel_density_scorer = cancel_density_scorer
runner.order_ladder_scorer = order_ladder_scorer
runner.iceberg_scorer = iceberg_scorer
runner.order_spoofing_scorer = order_spoofing_scorer
runner.synthetic_fill_scorer = synthetic_fill_scorer

# ✅ Patch spoof/iceberg detectors into runner
runner.cancel_density_detector = cancel_density_detector
runner.order_laddering_tracker = order_laddering_tracker
runner.iceberg_detector = iceberg_detector
runner.order_spoofing_detector = order_spoofing_detector
runner.synthetic_fill_detector = synthetic_fill_detector


# === Streamlit UI ===
st.set_page_config(page_title="Mythic Market Cockpit", layout="wide")
st.title("🧠 Digital Markets Behavioral Engine")

st.sidebar.image("assets/epiclogo.png", use_column_width=True)  # ✅ Logo added here
# Sidebar controls
st.sidebar.header("⚙️ Controls")
view_mode = st.sidebar.radio("🧭 View Mode", ["Dashboards", "Debug Views"])
show_all = st.sidebar.checkbox("Show all debug views", value=False)
views = collect_debug_views(runner)
selected_modules = st.sidebar.multiselect("Select modules to inspect", list(views.keys()), disabled=show_all)

# Narration trigger
if st.button("🔮 Narrate Current Regime"):
    prompt = build_prompt_from_debug_views(views)
    narration = mistral_narrate(prompt)
    st.subheader("🗣️ Symbolic Narration")
    st.markdown(narration)

# 📊 Dashboard or Debug View Toggle
if view_mode == "Dashboards":
    st.subheader("📊 Module Dashboards")
    tabs = st.tabs(list(views.keys()))
    for i, name in enumerate(views.keys()):
        with tabs[i]:
            st.markdown(f"### 📦 {name}")
            st.json(views[name])

            # 🔮 Narration per module
            if st.button(f"🔮 Narrate {name}", key=f"narrate_{name}"):
                prompt = build_prompt_from_debug_views({name: views[name]})
                narration = mistral_narrate(prompt)
                st.markdown(f"**🗣️ {name} Narration**")
                st.markdown(narration)

            # 📈 Chart if score history is available
            if "score_history" in views[name]:
                history = views[name]["score_history"]
                df = pd.DataFrame(history)
                if "timestamp" in df.columns and "score" in df.columns:
                    df["timestamp"] = pd.to_datetime(df["timestamp"])
                    df.set_index("timestamp", inplace=True)
                    st.line_chart(df["score"])


# Optional: Spoof cluster summary
if "spoof_clusters" in views:
    st.subheader("📊 Spoof Cluster Summary")
    df = pd.DataFrame(views["spoof_clusters"]["clusters"])
    st.dataframe(df)

# Optional: Regime overlay
if "regime_overlay" in views:
    st.subheader("🧭 Regime Overlay")
    st.json(views["regime_overlay"])
