"""
FinResearch AI - Advanced Multi-Agent Financial Research System
Built with LangGraph, LangChain, and Gradio.

This application acts as a main entry point for the user interface.
"""

import time
import json
import re
import logging
import os
import zipfile
import html
from typing import Dict, Tuple
import gradio as gr
from src.graph import create_graph
import plotly.graph_objects as go

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("FinResearchAI")

# --- Security & Caching ---
CACHE_DURATION = int(os.getenv("CACHE_DURATION", 300))  # 5 minutes default
RATE_LIMIT_BLOCK = int(os.getenv("RATE_LIMIT_BLOCK", 1800))  # 30 minutes
MAX_REQUESTS_PER_WINDOW = int(os.getenv("MAX_REQUESTS_PER_WINDOW", 5))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", 3600))  # 1 hour

# Simple in-memory storage
# Cache key: (ticker, mode) -> (timestamp, data)
response_cache: Dict[Tuple[str, str], Tuple[float, dict]] = {}
# Rate Limit: {client_ip: {"count": int, "window_start": timestamp, "blocked_until": timestamp}}
rate_limit_db: Dict[str, dict] = {}


def validate_env():
    """Validates required environment variables at startup."""
    required = ["PINECONE_API_KEY", "OPENAI_API_KEY", "TAVILY_API_KEY"]
    missing = [
        env for env in required if not os.getenv(env) or len(os.getenv(env, "")) < 10
    ]
    if missing:
        raise RuntimeError("Missing or invalid required environment variables")


def sanitize_ticker(ticker: str) -> str:
    """
    Sanitizes and validates ticker symbol with strict security checks.
    Prevents XSS, path traversal, and injection attacks.
    """
    if not ticker:
        raise ValueError("Ticker cannot be empty")

    # Remove whitespace and convert to uppercase
    ticker = ticker.strip().upper()

    # Strict validation: Only alphanumeric and hyphen (NO dots for security)
    # Maximum 10 characters to prevent abuse
    if not re.match(r"^[A-Z0-9\-]{1,10}$", ticker):
        raise ValueError("Invalid ticker format")

    # Additional security: Reject if looks suspicious
    if ticker.count("-") > 1 or ticker.startswith("-") or ticker.endswith("-"):
        raise ValueError("Invalid ticker format")

    return ticker


def escape_llm_output(text: str) -> str:
    """
    Escapes LLM-generated text to prevent XSS attacks.
    CRITICAL: Always use this before rendering LLM outputs in HTML.
    """
    if not text:
        return ""
    # HTML escape all special characters
    return html.escape(str(text), quote=True)


def cleanup_expired_data():
    """Removes expired entries from response_cache and rate_limit_db to prevent memory growth."""
    now = time.time()

    # Cleanup Cache
    expired_cache = [
        k for k, v in response_cache.items() if now - v[0] > CACHE_DURATION
    ]
    for k in expired_cache:
        del response_cache[k]

    # Cleanup Rate Limit DB (entries older than window + block)
    expired_ips = [
        ip
        for ip, data in rate_limit_db.items()
        if now - data["window_start"] > RATE_LIMIT_WINDOW + RATE_LIMIT_BLOCK
    ]
    for ip in expired_ips:
        del rate_limit_db[ip]

    if expired_cache or expired_ips:
        logger.info(
            f"Cleaned up {len(expired_cache)} cache entries and {len(expired_ips)} rate limit entries."
        )


# --- Custom Theme & Styling ---
CUSTOM_CSS = """
/* ===== FONT IMPORTS ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800;900&family=Roboto+Mono:wght@400;600;700&display=swap');

/* ===== CSS VARIABLES (SDS-Inspired Color Palette) ===== */
:root {
    /* Primary Colors */
    --primary-cyan: #0693e3;
    --primary-cyan-bright: #00C9FF;
    --primary-cyan-light: #00E5FF;
    --primary-charcoal: #32373c;

    /* Accent Colors */
    --accent-purple: #9b51e0;
    --accent-orange: #ff6900;
    --accent-green: #00d084;
    --accent-gold: #FFD700;
    --accent-red: #FF5252;

    /* Neutrals */
    --bg-primary: #0a0e27;
    --bg-secondary: #1a1f3a;
    --bg-tertiary: #2a2f4a;
    --text-primary: #ffffff;
    --text-secondary: #e0e0e0;
    --text-tertiary: #999999;
    --border-primary: rgba(0, 201, 255, 0.2);
    --border-secondary: rgba(255, 255, 255, 0.1);
}

/* ===== GLOBAL OVERRIDES ===== */
body {
    background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0a0e27 100%) !important;
    font-family: 'Inter', ui-sans-serif, system-ui, sans-serif !important;
    color: var(--text-primary) !important;
    overflow: hidden !important;
    height: 100vh !important;
    margin: 0 !important;
    padding: 0 !important;
}

.gradio-container {
    max-width: 1400px !important;
    margin: 0 auto !important;
    height: 100vh !important;
    display: flex !important;
    flex-direction: column !important;
    overflow: hidden !important;
    padding: 0 !important;
}

/* Fixed header sections (disclaimer + hero) */
.gradio-container > div:first-child,
.gradio-container > div:nth-child(2) {
    flex-shrink: 0 !important;
}

/* Main content row - grows to fill space */
.gradio-container > div:nth-child(3) {
    flex: 1 !important;
    min-height: 0 !important;
    overflow: hidden !important;
}

/* Left sidebar column - scrollable if needed */
.gradio-container > div:nth-child(3) > div:first-child {
    overflow-y: auto !important;
    overflow-x: hidden !important;
    max-height: 100% !important;
}

/* Right results column - scrollable */
.gradio-container > div:nth-child(3) > div:last-child {
    overflow-y: auto !important;
    overflow-x: hidden !important;
    max-height: 100% !important;
}

/* Fixed footer */
.gradio-container > div:last-child {
    flex-shrink: 0 !important;
}

/* ===== CUSTOM SCROLLBAR ===== */
::-webkit-scrollbar {
    width: 10px;
    height: 10px;
}

::-webkit-scrollbar-track {
    background: rgba(0, 0, 0, 0.3);
}

::-webkit-scrollbar-thumb {
    background: rgba(0, 201, 255, 0.4);
    border-radius: 5px;
}

::-webkit-scrollbar-thumb:hover {
    background: rgba(0, 201, 255, 0.6);
}

/* ===== INPUT FIELDS ===== */
#ticker-input input {
    background: rgba(0, 0, 0, 0.4) !important;
    border: 2px solid rgba(0, 201, 255, 0.3) !important;
    color: #00C9FF !important;
    font-size: 20px !important;
    font-weight: 700 !important;
    text-align: center !important;
    text-transform: uppercase !important;
    letter-spacing: 2px !important;
    transition: all 0.3s ease !important;
    border-radius: 12px !important;
    padding: 18px !important;
}

#ticker-input input:focus {
    border-color: #00E5FF !important;
    box-shadow: 0 0 20px rgba(0, 201, 255, 0.4) !important;
    outline: none !important;
}

#ticker-input input::placeholder {
    color: rgba(0, 201, 255, 0.4) !important;
}

/* ===== DROPDOWN/RADIO (MODE SELECTOR) ===== */
#mode-selector label {
    background: rgba(0, 0, 0, 0.3) !important;
    border: 2px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 12px !important;
    padding: 12px 16px !important;
    margin: 5px 0 !important;
    transition: all 0.3s ease !important;
    cursor: pointer !important;
}

#mode-selector label:hover {
    border-color: rgba(0, 201, 255, 0.5) !important;
    background: rgba(0, 201, 255, 0.05) !important;
}

#mode-selector input:checked + label {
    border-color: #00C9FF !important;
    background: rgba(0, 201, 255, 0.15) !important;
    box-shadow: 0 0 15px rgba(0, 201, 255, 0.3) !important;
}

/* ===== BUTTONS ===== */
#submit-btn {
    background: linear-gradient(135deg, #00C9FF, #00E5FF) !important;
    font-weight: 800 !important;
    font-size: 16px !important;
    padding: 18px !important;
    border: none !important;
    border-radius: 12px !important;
    box-shadow: 0 4px 20px rgba(0, 201, 255, 0.3) !important;
    transition: all 0.3s ease !important;
    color: #000 !important;
    letter-spacing: 1px !important;
}

#submit-btn:hover {
    transform: translateY(-2px) !important;
    box-shadow: 0 6px 30px rgba(0, 201, 255, 0.5) !important;
}

#submit-btn:active {
    transform: translateY(0) !important;
}

/* ===== TABS ===== */
#report-tabs .tab-nav {
    background: rgba(0, 0, 0, 0.3) !important;
    border-bottom: 2px solid rgba(0, 201, 255, 0.2) !important;
    border-radius: 12px 12px 0 0 !important;
}

#report-tabs button {
    background: transparent !important;
    border: none !important;
    color: rgba(255, 255, 255, 0.6) !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    padding: 16px 24px !important;
    transition: all 0.3s ease !important;
}

#report-tabs button:hover {
    color: #00C9FF !important;
    background: rgba(0, 201, 255, 0.05) !important;
}

#report-tabs button.selected {
    color: #00C9FF !important;
    background: rgba(0, 201, 255, 0.1) !important;
    border-bottom: 3px solid #00C9FF !important;
}

/* ===== PLOTS ===== */
.plot-container {
    background: rgba(0, 0, 0, 0.3) !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 16px !important;
    padding: 15px !important;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2) !important;
}

/* Fix radar plot from growing infinitely */
#radar-plot {
    max-height: 500px !important;
    overflow: hidden !important;
}

#radar-plot .plot-container {
    max-height: 500px !important;
    height: 500px !important;
    overflow: hidden !important;
}

#radar-plot svg {
    max-height: 450px !important;
    height: auto !important;
}

/* ===== MARKDOWN CONTENT ===== */
.prose {
    color: #e0e0e0 !important;
    line-height: 1.7 !important;
}

.prose h1, .prose h2, .prose h3 {
    color: #00C9FF !important;
    font-weight: 700 !important;
    margin-top: 24px !important;
    margin-bottom: 16px !important;
}

.prose ul, .prose ol {
    padding-left: 24px !important;
}

.prose li {
    margin-bottom: 8px !important;
}

.prose strong {
    color: #00E5FF !important;
    font-weight: 700 !important;
}

.prose code {
    background: rgba(0, 201, 255, 0.1) !important;
    color: #00C9FF !important;
    padding: 2px 6px !important;
    border-radius: 4px !important;
    font-family: 'Roboto Mono', monospace !important;
}

/* ===== FILE DOWNLOADS ===== */
.file-container {
    background: rgba(0, 0, 0, 0.3) !important;
    border: 1px solid rgba(0, 201, 255, 0.2) !important;
    border-radius: 12px !important;
    padding: 12px !important;
    transition: all 0.3s ease !important;
}

.file-container:hover {
    border-color: rgba(0, 201, 255, 0.4) !important;
    background: rgba(0, 201, 255, 0.05) !important;
}

/* ===== ANIMATIONS ===== */
@keyframes pulse {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 1; }
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

@keyframes fadeOut {
    from { opacity: 1; transform: translateY(0); }
    to { opacity: 0; transform: translateY(-10px); }
}

@keyframes slideInRight {
    from { opacity: 0; transform: translateX(30px); }
    to { opacity: 1; transform: translateX(0); }
}

@keyframes rotate {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.fade-in {
    animation: fadeIn 0.5s ease-out;
}

.slide-in-right {
    animation: slideInRight 0.5s ease-out;
}

.pulse-text {
    animation: pulse 2s infinite ease-in-out;
    color: #ff9800;
    font-weight: bold;
    font-style: italic;
    font-family: 'Roboto Mono', monospace;
    text-align: center;
    padding: 10px;
}

/* Agent Progress Smooth Transitions */
#agent-progress-container {
    transition: opacity 0.6s ease-out, transform 0.6s ease-out;
}

#agent-progress-container[style*="display: none"] {
    animation: fadeOut 0.6s ease-out;
}

/* Results area - dynamic height */
#verdict-card:empty::after {
    content: "";
    display: block;
    min-height: 0;
}

/* Tabs container */
.tab-nav {
    position: sticky;
    top: 0;
    z-index: 10;
    background: var(--bg-primary);
}

/* ===== DISCLAIMER BANNER ===== */
.disclaimer-banner {
    background: rgba(255, 193, 7, 0.08) !important;
    border-left: 3px solid #ffc107 !important;
    border-bottom: 1px solid rgba(255, 193, 7, 0.2) !important;
    backdrop-filter: blur(10px) !important;
}

/* ===== FOOTER ATTRIBUTION ===== */
.footer-attribution {
    text-align: center;
    padding: 15px 20px;
    background: rgba(0, 0, 0, 0.3);
    border-top: 1px solid rgba(0, 201, 255, 0.15);
    margin: 0;
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
}

.footer-attribution a {
    color: #00C9FF;
    text-decoration: none;
    font-weight: 600;
    transition: color 0.3s ease;
}

.footer-attribution a:hover {
    color: #00E5FF;
}

/* ===== COMPACT SPACING ===== */
.gr-row {
    gap: 15px !important;
}

.gr-column {
    gap: 12px !important;
}

/* ===== MOBILE RESPONSIVENESS ===== */
@media (max-width: 768px) {
    .gradio-container {
        padding: 10px !important;
    }

    #ticker-input input {
        font-size: 16px !important;
        padding: 14px !important;
    }

    #submit-btn {
        font-size: 14px !important;
        padding: 14px !important;
    }

    #report-tabs button {
        font-size: 12px !important;
        padding: 12px 16px !important;
    }

    button, a, input, select {
        min-height: 44px !important;
        min-width: 44px !important;
    }

    body {
        overflow-y: auto !important;
    }
}

@media (max-width: 480px) {
    #ticker-input input {
        font-size: 14px !important;
        letter-spacing: 1px !important;
    }

    #report-tabs button {
        font-size: 11px !important;
        padding: 10px 12px !important;
    }
}

/* Hide default Gradio footer */
footer {
    visibility: hidden !important;
}
"""

# --- Custom Gradio Theme ---
custom_theme = gr.themes.Soft(
    primary_hue="cyan",
    secondary_hue="blue",
    neutral_hue="slate",
    font=gr.themes.GoogleFont("Inter"),
    font_mono=gr.themes.GoogleFont("Roboto Mono"),
).set(
    body_background_fill="linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%)",
    body_background_fill_dark="linear-gradient(135deg, #0a0e27 0%, #1a1f3a 100%)",
    button_primary_background_fill="#00C9FF",
    button_primary_background_fill_hover="#00E5FF",
    button_primary_text_color="#000000",
    input_background_fill="rgba(0, 0, 0, 0.4)",
    input_border_color="rgba(0, 201, 255, 0.3)",
    block_background_fill="rgba(255, 255, 255, 0.02)",
    block_border_color="rgba(255, 255, 255, 0.1)",
)


def get_hero_html():
    """
    Generates the hero section with SDS-inspired branding
    """
    return f"""
    <div style="
        background: linear-gradient(135deg, #0a0e27 0%, #1a1f3a 50%, #0a0e27 100%);
        border-bottom: 1px solid rgba(0, 201, 255, 0.2);
        padding: 25px 20px;
        text-align: center;
        position: relative;
        overflow: hidden;
    ">
        <div style="
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-image:
                repeating-linear-gradient(90deg, transparent, transparent 79px, rgba(0, 201, 255, 0.03) 79px, rgba(0, 201, 255, 0.03) 81px),
                repeating-linear-gradient(0deg, transparent, transparent 79px, rgba(0, 201, 255, 0.03) 79px, rgba(0, 201, 255, 0.03) 81px);
            pointer-events: none;
        "></div>

        <div style="position: relative; z-index: 1;">
            <div style="
                font-size: 36px;
                font-weight: 900;
                background: linear-gradient(135deg, #00C9FF 0%, #00E5FF 50%, #00C9FF 100%);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                background-clip: text;
                margin-bottom: 6px;
                letter-spacing: -1px;
            ">FinResearch AI</div>

            <div style="
                font-size: 14px;
                color: rgba(255, 255, 255, 0.7);
                font-weight: 300;
                letter-spacing: 1.5px;
                text-transform: uppercase;
            ">AI-Powered Stock Analysis Platform</div>

            <div style="
                margin-top: 12px;
                font-size: 12px;
                color: rgba(0, 201, 255, 0.8);
                font-family: 'Roboto Mono', monospace;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            ">
                {get_svg_icon("brain", 16)} Manager →
                {get_svg_icon("search", 16)} Researchers →
                {get_svg_icon("chart", 16)} Analyst →
                {get_svg_icon("document", 16)} Reporter
            </div>
        </div>
    </div>

    <style>
        @media (max-width: 768px) {{
            .hero-title {{ font-size: 32px !important; }}
        }}
    </style>
    """


def get_footer_html():
    """
    Generates footer with subtle SDS and creator attribution
    """
    return """
    <div class="footer-attribution">
        <div style="display: flex; align-items: center; justify-content: center; gap: 15px; flex-wrap: wrap;">
            <span style="color: rgba(255,255,255,0.3);">
                Built with <span style="color: #FF5252;">♥</span> by
                <a href="https://linkedin.com/in/prateekmulye" target="_blank" rel="noopener" style="color: #00C9FF; font-weight: 700; text-decoration: none;">Prateek Mulye</a>
            </span>
            <span style="color: rgba(255,255,255,0.2);">|</span>
            <span style="color: rgba(255,255,255,0.3);">
                A community project with <a href="https://superdatascience.com" target="_blank" rel="noopener">SuperDataScience</a>
            </span>
        </div>
    </div>
    """


def generate_agent_progress_html(
    stage="initializing", current_message="Preparing analysis..."
):
    """
    Generates real-time agent progress visualization
    stage: "manager" | "research" | "analyst" | "reporter" | "complete"
    """
    # Define agent pipeline with SVG icons
    agents = [
        {
            "id": "manager",
            "icon": get_svg_icon("brain", 28, "#FFD700"),
            "label": "Manager",
            "color": "#FFD700",
        },
        {
            "id": "research",
            "icon": get_svg_icon("search", 28, "#00C9FF"),
            "label": "Researchers",
            "color": "#00C9FF",
        },
        {
            "id": "analyst",
            "icon": get_svg_icon("chart", 28, "#9C27B0"),
            "label": "Analyst",
            "color": "#9C27B0",
        },
        {
            "id": "reporter",
            "icon": get_svg_icon("document", 28, "#FF9800"),
            "label": "Reporter",
            "color": "#FF9800",
        },
    ]

    # Determine status for each agent
    stage_order = ["manager", "research", "analyst", "reporter", "complete"]
    current_index = stage_order.index(stage) if stage in stage_order else 0

    agent_cards_html = ""
    for i, agent in enumerate(agents):
        if i < current_index:
            # Completed
            status_class = "completed"
            border_color = agent["color"]
            bg_opacity = "0.2"
            glow = f"0 0 15px {agent['color']}"
            status_icon = "<div style='position: absolute; top: 5px; right: 5px; font-size: 16px;'>✅</div>"
        elif stage_order[i] == stage:
            # Currently active
            status_class = "active"
            border_color = agent["color"]
            bg_opacity = "0.3"
            glow = f"0 0 25px {agent['color']}"
            status_icon = "<div style='position: absolute; top: 5px; right: 5px; font-size: 16px; animation: spin 2s linear infinite;'>⚡</div>"
        else:
            # Pending
            status_class = "pending"
            border_color = "rgba(255, 255, 255, 0.1)"
            bg_opacity = "0.05"
            glow = "none"
            status_icon = ""

        agent_cards_html += f"""
        <div style="
            flex: 1;
            min-width: 80px;
            text-align: center;
            padding: 15px 10px;
            background: rgba(255, 255, 255, {bg_opacity});
            border: 2px solid {border_color};
            border-radius: 12px;
            box-shadow: {glow};
            transition: all 0.3s ease;
            position: relative;
        ">
            <div style="margin-bottom: 5px; display: flex; justify-content: center;">{agent['icon']}</div>
            <div style="
                font-size: 11px;
                color: {agent['color'] if status_class != 'pending' else '#666'};
                font-weight: 600;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            ">{agent['label']}</div>
            {status_icon}
        </div>
        """

        # Add arrow between agents
        if i < len(agents) - 1:
            arrow_color = (
                agent["color"] if i < current_index else "rgba(255,255,255,0.2)"
            )
            agent_cards_html += f"""
            <div style="
                font-size: 20px;
                color: {arrow_color};
                flex-shrink: 0;
                padding: 0 10px;
            ">→</div>
            """

    html = f"""
    <div style="
        background: linear-gradient(135deg, rgba(0, 0, 0, 0.6), rgba(0, 0, 0, 0.4));
        border: 1px solid rgba(0, 201, 255, 0.2);
        border-radius: 16px;
        padding: 25px;
        margin-bottom: 20px;
        backdrop-filter: blur(10px);
    ">
        <div style="
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 20px;
        ">
            <div style="
                font-size: 16px;
                font-weight: 700;
                color: #00C9FF;
                letter-spacing: 1px;
            ">AGENT EXECUTION PIPELINE</div>

            <div id="progress-pulse" style="
                width: 12px;
                height: 12px;
                background: #00E676;
                border-radius: 50%;
                animation: pulse 1.5s infinite;
            "></div>
        </div>

        <!-- Progress Track -->
        <div style="
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 10px;
            flex-wrap: wrap;
        ">
            {agent_cards_html}
        </div>

        <!-- Status Message -->
        <div style="
            margin-top: 20px;
            padding: 12px 16px;
            background: rgba(0, 201, 255, 0.1);
            border-left: 3px solid #00C9FF;
            border-radius: 4px;
            font-size: 13px;
            color: rgba(255, 255, 255, 0.9);
            font-family: 'Roboto Mono', monospace;
        ">
            <span style="color: #00C9FF; font-weight: 700;">STATUS:</span> {current_message}
        </div>
    </div>
    """

    return html


def parse_investor_mode(mode_string):
    """
    Extracts the actual mode from the radio label
    e.g., "🐂 Bullish - Growth Focused" -> "Bullish"
    """
    if "Bullish" in mode_string:
        return "Bullish"
    elif "Bearish" in mode_string:
        return "Bearish"
    else:
        return "Neutral"


def show_analyst_stage():
    """Shows analyst stage with timing for user comprehension"""
    import time

    time.sleep(1.2)  # Brief delay so users see research complete
    return generate_agent_progress_html("analyst", "Analyzing data and scoring...")


def show_reporter_stage():
    """Shows reporter stage with timing for user comprehension"""
    import time

    time.sleep(1.0)  # Brief delay so users see analyst complete
    return generate_agent_progress_html("reporter", "Generating final report...")


def show_complete_stage():
    """Shows completion stage with timing before displaying results"""
    import time

    time.sleep(0.8)  # Brief delay so users see reporter complete
    return generate_agent_progress_html("complete", "Analysis complete!")


def get_svg_icon(icon_name, size=24, color="#00C9FF"):
    """
    Returns professional SVG icons matching the app theme
    Open-source, MIT-licensed designs inspired by Lucide/Heroicons
    """
    icons = {
        "brain": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/>
            <path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/>
        </svg>""",
        "search": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <path d="m21 21-4.35-4.35"/>
            <path d="M11 8a3 3 0 0 0-3 3"/>
        </svg>""",
        "chart": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M3 3v18h18"/>
            <path d="m19 9-5 5-4-4-3 3"/>
        </svg>""",
        "document": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <line x1="10" y1="9" x2="8" y2="9"/>
        </svg>""",
        "rocket": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z"/>
            <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z"/>
            <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0"/>
            <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5"/>
        </svg>""",
        "download": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
        </svg>""",
        "target": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <circle cx="12" cy="12" r="6"/>
            <circle cx="12" cy="12" r="2"/>
        </svg>""",
        "lightbulb": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.7 1.3 1.5 1.5 2.5"/>
            <path d="M9 18h6"/>
            <path d="M10 22h4"/>
        </svg>""",
        "alert": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/>
            <line x1="12" y1="9" x2="12" y2="13"/>
            <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>""",
        "waveform": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M2 13h4l3-9 4 18 3-9h4"/>
        </svg>""",
        "trending-up": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>
            <polyline points="16 7 22 7 22 13"/>
        </svg>""",
        "trending-down": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>
            <polyline points="16 17 22 17 22 11"/>
        </svg>""",
        "balance": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 3v18"/>
            <path d="M8 9l4-4 4 4"/>
            <path d="M16 15l-4 4-4-4"/>
        </svg>""",
        "building": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="4" y="2" width="16" height="20" rx="2" ry="2"/>
            <path d="M9 22v-4h6v4"/>
            <path d="M8 6h.01"/>
            <path d="M16 6h.01"/>
            <path d="M12 6h.01"/>
            <path d="M12 10h.01"/>
            <path d="M12 14h.01"/>
            <path d="M16 10h.01"/>
            <path d="M16 14h.01"/>
            <path d="M8 10h.01"/>
            <path d="M8 14h.01"/>
        </svg>""",
        "newspaper": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/>
            <path d="M18 14h-8"/>
            <path d="M15 18h-5"/>
            <path d="M10 6h8v4h-8V6Z"/>
        </svg>""",
        "hand": f"""<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/>
            <path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/>
            <path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/>
            <path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
        </svg>""",
    }
    return icons.get(icon_name, "")


def get_client_ip(request: gr.Request):
    if request:
        return request.client.host
    return "unknown"


def check_rate_limit(request: gr.Request):
    """
    Blocks client if they exceed MAX_REQUESTS_PER_WINDOW.
    """
    cleanup_expired_data()  # Opportunistic cleanup
    client_ip = get_client_ip(request)
    now = time.time()

    if client_ip not in rate_limit_db:
        rate_limit_db[client_ip] = {"count": 0, "window_start": now, "blocked_until": 0}

    user_data = rate_limit_db[client_ip]

    if user_data["blocked_until"] > now:
        remaining = int((user_data["blocked_until"] - now) / 60)
        logger.warning(f"Blocked request from {client_ip}. Remaining: {remaining}m")
        raise gr.Error(f"Rate limit exceeded. Try again in {remaining} minutes.")

    if now - user_data["window_start"] > RATE_LIMIT_WINDOW:
        user_data["count"] = 0
        user_data["window_start"] = now

    user_data["count"] += 1
    if user_data["count"] > MAX_REQUESTS_PER_WINDOW:
        user_data["blocked_until"] = now + RATE_LIMIT_BLOCK
        logger.warning(
            f"Rate limit tripped for {client_ip}. Blocked for {RATE_LIMIT_BLOCK/60}m"
        )
        raise gr.Error("Rate limit exceeded. You are blocked for 30 minutes.")


def parse_report_sections(report_text):
    """
    Parses the markdown report into dictionary sections for tabs.
    """
    sections = {
        "Executive Summary": "No summary available.",
        "Analyst Verdict": "No verdict available.",
        "Company Snapshot": "No snapshot available.",
        "Financial Indicators": "No data available.",
        "News & Sentiment": "No news available.",
        "Risks & Opportunities": "No analysis available.",
        "Final Perspective": "No conclusion available.",
    }

    patterns = {
        "Executive Summary": r"(?:##\s*\d*\.?\s*Executive Summary|Executive Summary)\n(.*?)(?=\n##|$)",
        "Analyst Verdict": r"(?:##\s*\d*\.?\s*Analyst Verdict|Analyst Verdict)\n(.*?)(?=\n##|$)",
        "Company Snapshot": r"(?:##\s*\d*\.?\s*Company Snapshot|Company Snapshot)\n(.*?)(?=\n##|$)",
        "Financial Indicators": r"(?:##\s*\d*\.?\s*Key Financial Indicators|Financial Indicators)\n(.*?)(?=\n##|$)",
        "News & Sentiment": r"(?:##\s*\d*\.?\s*Recent News & Sentiment|News & Sentiment)\n(.*?)(?=\n##|$)",
        "Risks & Opportunities": r"(?:##\s*\d*\.?\s*Risks & Opportunities|Risks & Opportunities)\n(.*?)(?=\n##|$)",
        "Final Perspective": r"(?:##\s*\d*\.?\s*Final Perspective|Final Perspective)\n(.*?)$",
    }

    for key, pattern in patterns.items():
        match = re.search(pattern, report_text, re.DOTALL)
        if match:
            sections[key] = match.group(1).strip()

    return sections


def generate_animated_verdict_html(score, recommendation, reasoning):
    """
    Generates animated verdict card with JavaScript counter animation
    SECURITY: Escapes all LLM outputs to prevent XSS
    """
    # SECURITY: Escape all LLM-generated content
    recommendation = escape_llm_output(recommendation)
    reasoning = escape_llm_output(reasoning)

    # Color scheme based on score
    if score >= 75:
        score_color = "#00E676"
        badge_bg = "rgba(0, 230, 118, 0.15)"
        border_color = "rgba(0, 230, 118, 0.4)"
        glow_color = "rgba(0, 230, 118, 0.3)"
    elif score >= 40:
        score_color = "#FFD700"
        badge_bg = "rgba(255, 215, 0, 0.15)"
        border_color = "rgba(255, 215, 0, 0.4)"
        glow_color = "rgba(255, 215, 0, 0.3)"
    else:
        score_color = "#FF5252"
        badge_bg = "rgba(255, 82, 82, 0.15)"
        border_color = "rgba(255, 82, 82, 0.4)"
        glow_color = "rgba(255, 82, 82, 0.3)"

    # Generate unique IDs for this instance
    import uuid

    uid = str(uuid.uuid4())[:8]

    html = f"""
    <div style="
        background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, rgba(255,255,255,0.01) 100%);
        border-radius: 20px;
        padding: 35px;
        border: 2px solid {border_color};
        margin-bottom: 30px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.3), 0 0 40px {glow_color};
        position: relative;
        overflow: hidden;
    ">
        <!-- Animated background gradient -->
        <div style="
            position: absolute;
            top: -50%;
            left: -50%;
            width: 200%;
            height: 200%;
            background: radial-gradient(circle, {glow_color} 0%, transparent 70%);
            animation: rotate 20s linear infinite;
            pointer-events: none;
        "></div>

        <div style="position: relative; z-index: 1;">
            <!-- Desktop Layout -->
            <div class="verdict-desktop-{uid}" style="
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: 40px;
            ">
                <!-- Score Section -->
                <div style="flex: 1; text-align: center; border-right: 1px solid rgba(255,255,255,0.08); padding-right: 40px;">
                    <div style="font-size: 14px; color: #aaa; letter-spacing: 2px; margin-bottom: 10px; font-weight: 600;">ANALYST SCORE</div>

                    <div id="score-counter-{uid}" style="
                        font-size: 80px;
                        font-weight: 900;
                        color: {score_color};
                        line-height: 1;
                        text-shadow: 0 0 30px {glow_color};
                        font-family: 'Roboto Mono', monospace;
                    ">0</div>

                    <div style="font-size: 12px; color: #666; margin-top: 8px; letter-spacing: 1px;">OUT OF 100</div>

                    <!-- Progress bar -->
                    <div style="
                        width: 100%;
                        height: 6px;
                        background: rgba(255,255,255,0.1);
                        border-radius: 3px;
                        margin-top: 15px;
                        overflow: hidden;
                    ">
                        <div id="score-progress-{uid}" style="
                            width: 0%;
                            height: 100%;
                            background: linear-gradient(90deg, {score_color}, rgba(255,255,255,0.8));
                            transition: width 2s cubic-bezier(0.4, 0.0, 0.2, 1);
                        "></div>
                    </div>
                </div>

                <!-- Verdict Badge Section -->
                <div style="flex: 1; text-align: center; border-right: 1px solid rgba(255,255,255,0.08); padding-right: 40px;">
                    <div style="font-size: 14px; color: #aaa; letter-spacing: 2px; margin-bottom: 15px; font-weight: 600;">VERDICT</div>

                    <div style="
                        background-color: {badge_bg};
                        color: {score_color};
                        padding: 15px 35px;
                        border-radius: 40px;
                        font-weight: 900;
                        font-size: 24px;
                        border: 2px solid {border_color};
                        display: inline-block;
                        text-transform: uppercase;
                        letter-spacing: 2px;
                        box-shadow: 0 0 20px {glow_color};
                        animation: fadeInScale 0.6s ease-out 0.5s both;
                    ">
                        {recommendation}
                    </div>
                </div>

                <!-- Reasoning Section -->
                <div style="flex: 2.5; padding-left: 20px;">
                    <div style="font-size: 14px; color: #aaa; letter-spacing: 2px; margin-bottom: 12px; font-weight: 600;">KEY REASONING</div>

                    <div style="
                        font-size: 17px;
                        color: #f0f0f0;
                        line-height: 1.7;
                        font-weight: 300;
                        border-left: 4px solid {score_color};
                        padding-left: 20px;
                        font-style: italic;
                    ">
                        "{reasoning}"
                    </div>
                </div>
            </div>

            <!-- Mobile Layout (Hidden on Desktop) -->
            <div class="verdict-mobile-{uid}" style="display: none;">
                <!-- Score -->
                <div style="text-align: center; margin-bottom: 25px;">
                    <div style="font-size: 12px; color: #aaa; letter-spacing: 2px; margin-bottom: 8px;">ANALYST SCORE</div>
                    <div id="score-counter-mobile-{uid}" style="
                        font-size: 60px;
                        font-weight: 900;
                        color: {score_color};
                        text-shadow: 0 0 20px {glow_color};
                    ">0</div>
                    <div style="font-size: 11px; color: #666; margin-top: 5px;">OUT OF 100</div>
                </div>

                <!-- Verdict Badge -->
                <div style="text-align: center; margin-bottom: 25px;">
                    <div style="
                        background-color: {badge_bg};
                        color: {score_color};
                        padding: 12px 28px;
                        border-radius: 30px;
                        font-weight: 900;
                        font-size: 20px;
                        border: 2px solid {border_color};
                        display: inline-block;
                    ">{recommendation}</div>
                </div>

                <!-- Reasoning -->
                <div>
                    <div style="font-size: 12px; color: #aaa; letter-spacing: 2px; margin-bottom: 10px;">KEY REASONING</div>
                    <div style="
                        font-size: 15px;
                        color: #f0f0f0;
                        line-height: 1.6;
                        border-left: 3px solid {score_color};
                        padding-left: 15px;
                        font-style: italic;
                    ">"{reasoning}"</div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Animate score counter
        (function() {{
            function animateCounter(elementId, finalValue) {{
                const element = document.getElementById(elementId);
                if (!element) return;

                const duration = 2000;
                const start = 0;
                const startTime = performance.now();

                function update(currentTime) {{
                    const elapsed = currentTime - startTime;
                    const progress = Math.min(elapsed / duration, 1);
                    const easedProgress = 1 - Math.pow(1 - progress, 3);

                    const currentValue = Math.floor(start + (finalValue - start) * easedProgress);
                    element.textContent = currentValue;

                    if (progress < 1) {{
                        requestAnimationFrame(update);
                    }}
                }}

                requestAnimationFrame(update);
            }}

            // Trigger animations
            setTimeout(() => {{
                animateCounter('score-counter-{uid}', {score});
                animateCounter('score-counter-mobile-{uid}', {score});

                // Animate progress bar
                const progressBar = document.getElementById('score-progress-{uid}');
                if (progressBar) {{
                    progressBar.style.width = '{score}%';
                }}
            }}, 300);
        }})();
    </script>

    <style>
        @keyframes fadeInScale {{
            from {{
                opacity: 0;
                transform: scale(0.8);
            }}
            to {{
                opacity: 1;
                transform: scale(1);
            }}
        }}

        /* Mobile responsiveness */
        @media (max-width: 768px) {{
            .verdict-desktop-{uid} {{ display: none !important; }}
            .verdict-mobile-{uid} {{ display: block !important; }}
        }}
    </style>
    """

    return html


def generate_metrics_cards_html(metrics_list):
    """
    Generates modern metric cards using CSS Grid (replaces Plotly annotations)
    """
    if not metrics_list:
        return "<div>No metrics available</div>"

    top_metrics = metrics_list[:6]  # Show top 6 metrics

    # Metric explanations for common financial terms
    METRIC_EXPLANATIONS = {
        "P/E": "Price relative to earnings",
        "P/E Ratio": "Price relative to earnings",
        "EPS": "Profit per share",
        "Earnings Per Share": "Profit per share",
        "RSI": "Momentum indicator (0-100)",
        "MACD": "Trend strength indicator",
        "Dividend Yield": "Annual dividend return %",
        "Market Cap": "Total company value",
        "Revenue": "Total income generated",
        "Net Income": "Profit after expenses",
        "Debt/Equity": "Debt relative to equity",
        "ROE": "Return on equity %",
        "ROA": "Return on assets %",
        "Current Ratio": "Liquidity measure",
        "Quick Ratio": "Short-term liquidity",
        "Gross Margin": "Profit margin %",
        "Operating Margin": "Operating efficiency %",
        "Beta": "Volatility vs market",
        "52W High": "Highest price this year",
        "52W Low": "Lowest price this year",
        "Volume": "Shares traded",
        "Avg Volume": "Average shares traded",
    }

    html = """
    <div style="
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 15px;
        padding: 10px;
    ">
    """

    # Color rotation for variety
    colors = ["#00C9FF", "#00E676", "#FFD700", "#9C27B0", "#FF5252", "#FF9800"]

    for i, metric in enumerate(top_metrics):
        value = metric.get("Value", "-")
        label = metric.get("Metric", "Metric")
        color = colors[i % len(colors)]

        # Get explanation for this metric
        explanation = METRIC_EXPLANATIONS.get(label, "Financial metric")

        html += f"""
        <div style="
            background: linear-gradient(135deg, rgba(255,255,255,0.05), rgba(255,255,255,0.02));
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 16px;
            padding: 20px;
            text-align: center;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        " onmouseover="this.style.transform='translateY(-5px)'; this.style.borderColor='{color}';"
           onmouseout="this.style.transform='translateY(0)'; this.style.borderColor='rgba(255,255,255,0.1)';">

            <div style="position: relative; z-index: 1;">
                <div style="
                    font-size: 36px;
                    font-weight: 800;
                    color: {color};
                    margin-bottom: 8px;
                    font-family: 'Roboto Mono', monospace;
                    letter-spacing: -1px;
                ">{value}</div>

                <div style="
                    font-size: 12px;
                    color: rgba(255,255,255,0.7);
                    text-transform: uppercase;
                    letter-spacing: 1px;
                    font-weight: 600;
                    margin-bottom: 6px;
                ">{label}</div>

                <div style="
                    font-size: 10px;
                    color: rgba(255,255,255,0.4);
                    font-style: italic;
                    margin-top: 4px;
                ">{explanation}</div>
            </div>
        </div>
        """

    html += """
    </div>

    <style>
        @media (max-width: 480px) {
            /* Force single column on mobile */
            .metrics-grid {
                grid-template-columns: 1fr !important;
            }
        }
    </style>
    """

    return html


def create_enhanced_radar_chart(data_points, ticker, mode):
    """
    Enhanced radar chart with legend, tooltips, and benchmark overlay
    """
    categories = list(data_points.keys())
    values = list(data_points.values())

    # Close the loop
    categories = [*categories, categories[0]]
    values = [*values, values[0]]

    # Benchmark values (simulated industry average)
    benchmark_values = [6.5] * len(values)

    # Color scheme
    if mode != "Bearish":
        main_color = "#00C9FF"
        fill_color = "rgba(0, 201, 255, 0.3)"
        benchmark_color = "rgba(255, 215, 0, 0.2)"
    else:
        main_color = "#FF5252"
        fill_color = "rgba(255, 82, 82, 0.3)"
        benchmark_color = "rgba(255, 215, 0, 0.2)"

    fig = go.Figure()

    # Add benchmark overlay
    fig.add_trace(
        go.Scatterpolar(
            r=benchmark_values,
            theta=categories,
            fill="toself",
            name="Industry Avg",
            line_color="rgba(255, 215, 0, 0.5)",
            fillcolor=benchmark_color,
            hovertemplate="<b>Industry Avg</b><br>%{theta}: %{r:.1f}<extra></extra>",
        )
    )

    # Add actual data
    fig.add_trace(
        go.Scatterpolar(
            r=values,
            theta=categories,
            fill="toself",
            name=ticker,
            line_color=main_color,
            line_width=3,
            fillcolor=fill_color,
            hovertemplate=f"<b>{ticker}</b><br>%{{theta}}: %{{r:.1f}}<extra></extra>",
        )
    )

    fig.update_layout(
        template="plotly_dark",
        polar=dict(
            radialaxis=dict(
                visible=True,
                range=[0, 10],
                showline=False,
                gridcolor="#333333",
                tickfont=dict(size=11, color="#999"),
            ),
            angularaxis=dict(
                gridcolor="#333333",
                tickfont=dict(size=12, color="#fff", family="Roboto"),
            ),
            bgcolor="rgba(0,0,0,0.3)",
        ),
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.15,
            xanchor="center",
            x=0.5,
            bgcolor="rgba(0,0,0,0.5)",
            bordercolor="rgba(255,255,255,0.2)",
            borderwidth=1,
            font=dict(size=12, color="white"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        title=dict(
            text=f"<b>{ticker} Financial Health Profile</b>",
            font=dict(size=16, color=main_color),
            x=0.5,
            xanchor="center",
        ),
        margin=dict(t=60, b=60, l=50, r=50),
        height=400,
        width=500,
        autosize=False,
        font=dict(color="white", family="Roboto"),
        hoverlabel=dict(bgcolor="rgba(0,0,0,0.8)", font_size=13, font_family="Roboto"),
        uirevision="constant",
    )

    # Disable auto-updates and animations
    fig.update_traces(selector=dict(type="scatterpolar"))

    return fig


def run_research(ticker, mode, request: gr.Request):
    """
    Main handler for Gradio. Runs the graph and returns outputs.
    """
    check_rate_limit(request)  # Security Check

    # Parse mode from radio label
    mode = parse_investor_mode(mode)

    # SECURITY: Strict input validation
    try:
        ticker = sanitize_ticker(ticker)
    except ValueError as e:
        logger.warning(f"Invalid ticker input rejected: {str(e)}")
        raise gr.Error(
            "Invalid ticker format. Try: AAPL, TSLA, MSFT, or search for your company's ticker symbol."
        )

    # We remove the immediate yf.Ticker validation here to allow the Manager
    # to resolve international suffixes (e.g. converting RELIANCE -> RELIANCE.NS)
    # the graph will handle failures gracefully.

    cache_key = (ticker, mode)
    now = time.time()

    # Check Cache
    if cache_key in response_cache:
        timestamp, cached_output = response_cache[cache_key]
        if now - timestamp < CACHE_DURATION:
            logger.info("Returning cached response for ticker")
            final_output = cached_output
        else:
            logger.info("Cache expired, fetching new data")
            app = create_graph()
            initial_state = {"ticker": ticker, "investor_mode": mode, "messages": []}
            final_output = app.invoke(initial_state)
            response_cache[cache_key] = (now, final_output)
    else:
        logger.info("Fetching fresh analysis data")
        app = create_graph()
        initial_state = {"ticker": ticker, "investor_mode": mode, "messages": []}
        final_output = app.invoke(initial_state)
        response_cache[cache_key] = (now, final_output)

    report = final_output.get("final_report", "Error generating report.")
    sections = parse_report_sections(report)

    md_filename = f"{ticker}_report.md"
    json_filename = f"{ticker}_report.json"

    financial_data = final_output.get("financial_data", {})
    analyst_verdict = final_output.get("analyst_verdict", {})

    plot_update = gr.update(visible=False)
    metrics_update = gr.update(visible=False)
    verdict_html = "<div style='color: #888;'>Research not started.</div>"

    # 1. Process Chart (Enhanced Radar)
    if isinstance(financial_data, dict):
        chart_data = financial_data.get("chart", {})
        if chart_data.get("type") == "radar":
            try:
                data_points = chart_data.get("data", {})
                fig = create_enhanced_radar_chart(data_points, ticker, mode)
                plot_update = gr.update(value=fig, visible=True)
            except Exception as e:
                # SECURITY: Log error without exposing details to user
                logger.error(f"Radar plot generation failed for ticker: {ticker}")
                logger.debug(f"Error details: {str(e)}")  # Debug only

        # 2. Process Metrics (Modern Cards)
        metrics_list = financial_data.get("metrics", [])
        if metrics_list:
            metrics_html = generate_metrics_cards_html(metrics_list)
            metrics_update = gr.update(value=metrics_html, visible=True)

    # 3. Process Verdict (Animated HTML Card)
    if isinstance(analyst_verdict, dict):
        score = analyst_verdict.get("score", 0)
        rec = analyst_verdict.get("recommendation", "N/A")
        reason = analyst_verdict.get("reasoning", "No reasoning provided.")

        # DEBUG: Log the analyst verdict to diagnose score issue
        logger.info(f"Analyst Verdict received: {analyst_verdict}")
        logger.info(f"Extracted score: {score}, recommendation: {rec}")

        # Fallback: Try alternate key names if score is 0
        if score == 0:
            score = analyst_verdict.get("Score", 0)  # Try capitalized
            if score == 0:
                score = analyst_verdict.get("final_score", 0)  # Try alternate name
                if score == 0:
                    logger.warning("No valid score found in analyst_verdict, using default 0")

        verdict_html = generate_animated_verdict_html(score, rec, reason)

    # 4. Generate Results Intro
    # SECURITY: Validate and escape resolved_ticker from LLM
    resolved_ticker = final_output.get("resolved_ticker", ticker)
    try:
        # Re-validate resolved ticker (may have exchange suffix like .NS)
        if not re.match(r"^[A-Z0-9\-]{1,15}(\.[A-Z]{1,3})?$", resolved_ticker):
            resolved_ticker = ticker  # Fallback to original if invalid
        resolved_ticker = escape_llm_output(resolved_ticker)
    except Exception:
        resolved_ticker = escape_llm_output(ticker)

    results_intro_html = f"""
    <div style="
        background: linear-gradient(135deg, rgba(0, 201, 255, 0.08), rgba(0, 229, 255, 0.05));
        border: 1px solid rgba(0, 201, 255, 0.3);
        border-radius: 12px;
        padding: 16px 20px;
        margin-bottom: 20px;
        text-align: center;
    ">
        <div style="font-size: 18px; font-weight: 700; color: #00C9FF; margin-bottom: 6px;">
            📊 Analysis Complete for {resolved_ticker}
        </div>
        <div style="font-size: 13px; color: rgba(255, 255, 255, 0.7);">
            Here's what we found based on current market data and AI analysis
        </div>
    </div>
    """

    # Write individual files
    with open(md_filename, "w") as f:
        f.write(report)

    with open(json_filename, "w") as f:
        json.dump(
            {"financial_data": financial_data, "verdict": analyst_verdict}, f, indent=2
        )

    # Create zip file containing both reports
    zip_filename = f"{ticker}_analysis_package.zip"
    with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
        zipf.write(md_filename, arcname=f"{ticker}_report.md")
        zipf.write(json_filename, arcname=f"{ticker}_data.json")

    # Clean up individual files (optional - keep them for now in case needed)
    # os.remove(md_filename)
    # os.remove(json_filename)

    return (
        report,
        sections["Executive Summary"],
        sections["Company Snapshot"],
        sections["News & Sentiment"],
        sections["Risks & Opportunities"],
        zip_filename,
        plot_update,
        metrics_update,
        verdict_html,
        results_intro_html,
    )


# --- UI Layout ---
with gr.Blocks(title="FinResearch AI") as demo:
    # Disclaimer Banner
    gr.HTML(
        f"""
    <div class="disclaimer-banner" style="
        display: flex;
        align-items: center;
        padding: 10px 20px;
        gap: 12px;
        background: rgba(255, 193, 7, 0.08);
        border-left: 3px solid #ffc107;
        border-bottom: 1px solid rgba(255, 193, 7, 0.2);
        backdrop-filter: blur(10px);
    ">
        <div style="
            flex-shrink: 0;
        ">{get_svg_icon("alert", 20, "#ffc107")}</div>
        <div style="
            font-size: 12px;
            color: rgba(255, 255, 255, 0.85);
            line-height: 1.4;
            font-weight: 500;
        ">
            <span style="color: #ffc107; font-weight: 700;">DISCLAIMER:</span>
            This tool uses LLMs for financial analysis. It is NON-ADVISORY and for INFORMATIONAL PURPOSES ONLY. Investing involves risk. Do your own due diligence.
        </div>
    </div>
    """
    )

    # Hero Section
    gr.HTML(get_hero_html())

    with gr.Row():
        with gr.Column(scale=1, min_width=320):
            # First-Time User Banner
            gr.HTML(
                f"""
            <div style="
                background: rgba(0, 201, 255, 0.08);
                border: 1px solid rgba(0, 201, 255, 0.3);
                border-radius: 10px;
                padding: 12px 16px;
                margin-bottom: 15px;
                text-align: center;
                font-size: 13px;
                color: rgba(255, 255, 255, 0.85);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            ">
                {get_svg_icon("hand", 16)} <strong>First time?</strong> Click any example stock below to see how it works!
            </div>
            """
            )

            # Command Center Header
            gr.HTML(
                f"""
            <div style="
                text-align: center;
                padding: 15px;
                background: linear-gradient(135deg, rgba(0, 201, 255, 0.05), rgba(0, 229, 255, 0.05));
                border-radius: 12px 12px 0 0;
                border-bottom: 2px solid rgba(0, 201, 255, 0.3);
                margin-bottom: -10px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
            ">
                <span style="font-size: 16px; font-weight: 700; color: #00C9FF; display: flex; align-items: center; gap: 8px;">
                    {get_svg_icon("chart", 20)} Analyze a Stock
                </span>
            </div>
            """
            )

            with gr.Group():
                ticker_input = gr.Textbox(
                    label="Company Ticker Symbol",
                    placeholder="AAPL (Apple), TSLA (Tesla), MSFT (Microsoft)...",
                    elem_id="ticker-input",
                )

                # Example Stock Buttons
                gr.HTML(
                    f"""
                <div style="margin: 10px 0 15px 0;">
                    <div style="font-size: 12px; color: rgba(255,255,255,0.6); margin-bottom: 8px; text-align: center; display: flex; align-items: center; justify-content: center; gap: 6px;">
                        {get_svg_icon("lightbulb", 14)} Try these popular stocks:
                    </div>
                    <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                        <button onclick="document.querySelector('#ticker-input textarea').value='AAPL'; document.querySelector('#ticker-input textarea').dispatchEvent(new Event('input', {{bubbles: true}}));"
                            style="
                                padding: 8px 16px;
                                background: rgba(0, 201, 255, 0.1);
                                border: 1px solid rgba(0, 201, 255, 0.3);
                                border-radius: 8px;
                                color: #00C9FF;
                                font-weight: 600;
                                font-size: 12px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                            "
                            onmouseover="this.style.background='rgba(0, 201, 255, 0.2)'; this.style.borderColor='rgba(0, 201, 255, 0.5)';"
                            onmouseout="this.style.background='rgba(0, 201, 255, 0.1)'; this.style.borderColor='rgba(0, 201, 255, 0.3)';">
                            AAPL
                        </button>
                        <button onclick="document.querySelector('#ticker-input textarea').value='TSLA'; document.querySelector('#ticker-input textarea').dispatchEvent(new Event('input', {{bubbles: true}}));"
                            style="
                                padding: 8px 16px;
                                background: rgba(0, 201, 255, 0.1);
                                border: 1px solid rgba(0, 201, 255, 0.3);
                                border-radius: 8px;
                                color: #00C9FF;
                                font-weight: 600;
                                font-size: 12px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                            "
                            onmouseover="this.style.background='rgba(0, 201, 255, 0.2)'; this.style.borderColor='rgba(0, 201, 255, 0.5)';"
                            onmouseout="this.style.background='rgba(0, 201, 255, 0.1)'; this.style.borderColor='rgba(0, 201, 255, 0.3)';">
                            TSLA
                        </button>
                        <button onclick="document.querySelector('#ticker-input textarea').value='NVDA'; document.querySelector('#ticker-input textarea').dispatchEvent(new Event('input', {{bubbles: true}}));"
                            style="
                                padding: 8px 16px;
                                background: rgba(0, 201, 255, 0.1);
                                border: 1px solid rgba(0, 201, 255, 0.3);
                                border-radius: 8px;
                                color: #00C9FF;
                                font-weight: 600;
                                font-size: 12px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                            "
                            onmouseover="this.style.background='rgba(0, 201, 255, 0.2)'; this.style.borderColor='rgba(0, 201, 255, 0.5)';"
                            onmouseout="this.style.background='rgba(0, 201, 255, 0.1)'; this.style.borderColor='rgba(0, 201, 255, 0.3)';">
                            NVDA
                        </button>
                        <button onclick="document.querySelector('#ticker-input textarea').value='MSFT'; document.querySelector('#ticker-input textarea').dispatchEvent(new Event('input', {{bubbles: true}}));"
                            style="
                                padding: 8px 16px;
                                background: rgba(0, 201, 255, 0.1);
                                border: 1px solid rgba(0, 201, 255, 0.3);
                                border-radius: 8px;
                                color: #00C9FF;
                                font-weight: 600;
                                font-size: 12px;
                                cursor: pointer;
                                transition: all 0.2s ease;
                            "
                            onmouseover="this.style.background='rgba(0, 201, 255, 0.2)'; this.style.borderColor='rgba(0, 201, 255, 0.5)';"
                            onmouseout="this.style.background='rgba(0, 201, 255, 0.1)'; this.style.borderColor='rgba(0, 201, 255, 0.3)';">
                            MSFT
                        </button>
                    </div>
                </div>
                """
                )

                mode_input = gr.Radio(
                    choices=[
                        "🐂 Bullish - Growth Focused",
                        "⚖️ Neutral - Balanced View",
                        "🐻 Bearish - Risk Conscious",
                    ],
                    value="⚖️ Neutral - Balanced View",
                    label="Investor Persona",
                    elem_id="mode-selector",
                )
                submit_btn = gr.Button(
                    "Analyze Stock", variant="primary", elem_id="submit-btn"
                )

                # Funny Loading Status
                loading_display = gr.HTML(visible=True)

            gr.HTML(
                f"""
                <div style="font-size: 16px; font-weight: 700; color: #00C9FF; margin: 15px 0 10px 0; display: flex; align-items: center; gap: 8px;">
                    {get_svg_icon("download", 18)} Download Analysis Package
                </div>
                """
            )
            download_package = gr.File(
                label="Complete Analysis (ZIP)",
                file_types=[".zip"],
                elem_id="download-package",
            )

        with gr.Column(scale=4):
            # Agent Progress Visualization (Hidden by default)
            agent_progress = gr.HTML(
                value="", visible=False, elem_id="agent-progress-container"
            )

            # Results Intro (Shows after analysis)
            results_intro = gr.HTML(value="", visible=False, elem_id="results-intro")

            # Verdict Card
            verdict_display = gr.HTML(
                value="<div style='padding: 20px; text-align: center; color: #888;'>Ready to analyze...</div>",
                label="Analyst Verdict",
                elem_id="verdict-card",
            )

            # Data & Visuals
            with gr.Row(equal_height=True):
                with gr.Column(scale=1):
                    metrics_cards = gr.HTML(
                        label="📈 Key Metrics", visible=False, elem_id="metrics-cards"
                    )
                with gr.Column(scale=1):
                    viz_plot = gr.Plot(
                        label="🎯 Health Radar", visible=False, elem_id="radar-plot"
                    )
                    gr.Markdown(
                        "ℹ️ *Visualizing Key Metrics vs Industry or Trends. Source: YFinance/TradingView.*"
                    )

            # Detailed Reports
            with gr.Tabs():
                with gr.TabItem("📝 Executive Summary"):
                    summary_output = gr.Markdown()
                with gr.TabItem("🏢 Company Snapshot"):
                    snapshot_output = gr.Markdown()
                with gr.TabItem("🗞️ News & Sentiment"):
                    news_output = gr.Markdown()
                with gr.TabItem("⚖️ Risks & Opportunities"):
                    risks_output = gr.Markdown()
                with gr.TabItem("📄 Full Report"):
                    report_output = gr.Markdown()

    # Footer Attribution
    gr.HTML(get_footer_html())

    # Event Chaining with Agent Progress Visualization
    submit_btn.click(
        fn=lambda: (
            "",  # Clear loading display
            generate_agent_progress_html("manager", "Planning your analysis..."),
        ),
        outputs=[loading_display, agent_progress],
    ).then(fn=lambda: gr.update(visible=True), outputs=[agent_progress]).then(
        fn=lambda: (
            generate_agent_progress_html(
                "research", "Gathering market data and news..."
            ),
        ),
        outputs=[agent_progress],
    ).then(
        fn=show_analyst_stage,
        outputs=[agent_progress],
    ).then(
        fn=show_reporter_stage,
        outputs=[agent_progress],
    ).then(
        fn=run_research,
        inputs=[ticker_input, mode_input],
        outputs=[
            report_output,
            summary_output,
            snapshot_output,
            news_output,
            risks_output,
            download_package,
            viz_plot,
            metrics_cards,
            verdict_display,
            results_intro,
        ],
    ).then(
        fn=show_complete_stage,
        outputs=[agent_progress],
    ).then(
        fn=lambda: (
            "",  # Clear loading message
            gr.update(visible=False),  # Hide agent progress with fade
            gr.update(visible=True),  # Show results intro
        ),
        outputs=[loading_display, agent_progress, results_intro],
    )

if __name__ == "__main__":
    validate_env()
    server_name = os.getenv("GRADIO_SERVER_NAME", "0.0.0.0")
    server_port = int(os.getenv("GRADIO_SERVER_PORT", 7860))
    logger.info(f"Starting FinResearch AI on {server_name}:{server_port}")
    # Launch with custom theme and CSS (Gradio 6.0 requirement)
    demo.queue().launch(
        server_name=server_name,
        server_port=server_port,
        theme=custom_theme,
        css=CUSTOM_CSS,
    )
