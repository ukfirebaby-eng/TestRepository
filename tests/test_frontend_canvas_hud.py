from pathlib import Path


FRONTEND = Path(__file__).resolve().parents[1] / "static" / "index.html"


def test_canvas_hud_shell_and_lens_controls_exist():
    html = FRONTEND.read_text(encoding="utf-8")

    expected_tokens = [
        'id="command-hud"',
        'id="risk-lens-controls"',
        'data-lens="overview"',
        'data-lens="structural"',
        'data-lens="fragility"',
        'data-lens="timeline"',
        'data-lens="high-risk"',
        'id="critical-attention-panel"',
        'id="canvas-state-banner"',
        "function applyRiskLens",
        "function renderCriticalAttention",
        "function updateCanvasHud",
    ]

    missing = [token for token in expected_tokens if token not in html]
    assert missing == []


def test_canvas_refinement_controls_and_focus_helpers_exist():
    html = FRONTEND.read_text(encoding="utf-8")

    expected_tokens = [
        'id="node-search-panel"',
        'id="node-search-input"',
        'id="node-search-results"',
        'id="timeline-drawer"',
        'id="timeline-toggle"',
        "let selectedNodeId",
        "let selectedLinkKey",
        "function handleNodeSearch",
        "function renderNodeSearchResults",
        "function selectGraphNode",
        "function clearGraphSelection",
        "function focusLink",
        "function toggleTimelineDrawer",
        ".node-search-result",
        ".timeline-drawer.collapsed",
    ]

    missing = [token for token in expected_tokens if token not in html]
    assert missing == []


def test_canvas_analyst_map_view_contract_exists():
    html = FRONTEND.read_text(encoding="utf-8")

    expected_tokens = [
        "cytoscape",
        'id="view-mode-toggle"',
        'data-view="spatial"',
        'data-view="analyst"',
        'id="analyst-map-container"',
        "let analystMap",
        "function switchCanvasView",
        "function renderAnalystMap",
        "function buildAnalystElements",
        ".analyst-map",
    ]

    missing = [token for token in expected_tokens if token not in html]
    assert missing == []
