import json

def build_prompt_from_debug_views(views: dict) -> str:
    """
    Constructs a symbolic prompt from debug views for narration.
    """
    prompt = "Narrate the current market regime using the following diagnostics:\n\n"

    for module, view in views.items():
        prompt += f"=== {module.upper()} ===\n"
        for key, value in view.items():
            formatted_value = json.dumps(value, indent=2) if isinstance(value, (dict, list)) else str(value)
            prompt += f"{key}: {formatted_value}\n"
        prompt += "\n"

    prompt += "\nFocus on behavioral overlays, spoof signals, regime shifts, and symbolic scores.\n"
    prompt += "Use expressive, mythic language suitable for a market cockpit.\n"
    return prompt


def mistral_narrate(prompt: str) -> str:
    """
    Placeholder for model-based narration. Returns stylized markdown.
    """
    # You can later replace this with a real model call
    return f"""### 🧠 Mythic Regime Narration

> The market breathes in layered deception and exhales short-lived bursts.  
> Cancel density surges on the bid side, while spoof scores whisper of manipulation.  
> Regime velocity is rising, overlaying a volatile phase with adaptive signal blending.  

**Summary**  
- Cancel activity: elevated  
- Order age bias: short-lived  
- Layering score: dense clusters detected  
- Regime: {prompt[:50]}...

*This is a symbolic interpretation. For tactical execution, consult the raw overlays.*
"""
