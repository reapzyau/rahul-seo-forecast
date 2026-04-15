CTR_BY_POSITION = {
    1: 22.0, 2: 13.0, 3: 9.0, 4: 6.5, 5: 4.5,
    6: 3.2, 7: 2.5, 8: 2.0, 9: 1.6, 10: 1.3,
}
CTR_11_14 = 0.8
CTR_15_20 = 0.3

DIFFICULTY_TIERS = [
    (20, "Easy"), (40, "Moderate"), (60, "Hard"),
    (80, "Very Hard"), (100, "Extreme")
]

TIME_TO_RANK = {
    "Easy": (2, 3), "Moderate": (4, 6), "Hard": (7, 9),
    "Very Hard": (10, 12), "Extreme": (12, 14)
}

TIER_COLORS = {
    "Easy": "#22C55E", "Moderate": "#EAB308", "Hard": "#F97316",
    "Very Hard": "#EF4444", "Extreme": "#991B1B"
}

# ── Site Profile Presets ───────────────────────────────────────────────────
SITE_PRESETS = {
    "Custom": {"da": 30, "cadence": 4, "months": 18},
    "New Blog (DA 10-20)": {"da": 15, "cadence": 8, "months": 24},
    "Growing Site (DA 25-40)": {"da": 35, "cadence": 4, "months": 18},
    "Established Site (DA 45-65)": {"da": 55, "cadence": 6, "months": 12},
    "Enterprise (DA 70+)": {"da": 75, "cadence": 12, "months": 12},
}

# ── CTR Model Versions ────────────────────────────────────────────────────
CTR_MODELS = {
    "Standard": {
        "ctr_by_position": CTR_BY_POSITION,
        "ctr_11_14": CTR_11_14,
        "ctr_15_20": CTR_15_20,
        "label": "Standard (pre-AI)",
    },
    "AI-Adjusted": {
        "ctr_by_position": {
            1: 16.0, 2: 10.0, 3: 7.0, 4: 5.0, 5: 3.5,
            6: 2.5, 7: 2.0, 8: 1.6, 9: 1.2, 10: 1.0,
        },
        "ctr_11_14": 0.5,
        "ctr_15_20": 0.2,
        "label": "AI-Adjusted (reduced CTR from AI Overviews)",
    },
}

# ── Forecast Scenario Multipliers ─────────────────────────────────────────
FORECAST_SCENARIOS = {
    "Conservative": {"traffic_multiplier": 0.7, "label": "Conservative"},
    "Moderate (Recommended)": {"traffic_multiplier": 1.0, "label": "Moderate"},
    "Aggressive": {"traffic_multiplier": 1.3, "label": "Aggressive"},
}

# ── Search Intent Classification Patterns ─────────────────────────────────
INTENT_PATTERNS = {
    "informational": {
        "starts_with": [
            "how ", "what ", "why ", "when ", "where ", "which ",
            "is ", "are ", "can ", "do ", "does ", "will ", "should ",
        ],
        "contains": [
            "guide", "tutorial", "tips", "examples", "list of",
            "best practices", "meaning", "definition", "explained",
            "difference between",
        ],
    },
    "transactional": {
        "starts_with": [],
        "contains": [
            "buy", "purchase", "order", "price", "pricing", "cost",
            "cheap", "deal", "discount", "coupon", "free trial",
            "download", "subscribe", "hire", "quote",
        ],
    },
    "commercial": {
        "starts_with": [],
        "contains": [
            "best", "top", "review", "comparison", "alternative",
            "tool", "software", "service", "platform", "agency",
            "vs ", " vs ",
        ],
    },
    "navigational": {
        "starts_with": [],
        "contains": [
            "login", "sign in", "sign up", "official", "website",
        ],
    },
}
