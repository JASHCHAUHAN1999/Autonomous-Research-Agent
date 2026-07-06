# tests/test_static.py
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"


def test_index_html_exists():
    index = STATIC / "index.html"
    assert index.exists(), "app/static/index.html must exist"


def test_index_html_has_required_ids():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for element_id in ["provider", "model", "query", "timeline", "report"]:
        assert f'id="{element_id}"' in html, f'index.html missing id="{element_id}"'


def test_app_js_exists():
    js = STATIC / "app.js"
    assert js.exists(), "app/static/app.js must exist"


def test_app_js_has_required_calls():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    for needle in ["getReader", "/api/research", "/api/models"]:
        assert needle in js, f"app.js must reference {needle}"


def test_index_html_has_api_key_controls():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="api-key"' in html, 'index.html missing the api-key input'
    assert 'id="load-models"' in html, 'index.html missing the Load models button'


def test_app_js_supports_api_key_and_both_providers():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "api_key" in js, "app.js must send api_key"
    assert "openrouter" in js and "openai" in js, "app.js must offer both providers"


def test_index_html_has_source_key_inputs():
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="tavily-key"' in html, "index.html missing the Tavily key input"
    assert 'id="newsapi-key"' in html, "index.html missing the NewsAPI key input"


def test_app_js_sends_source_keys():
    js = (STATIC / "app.js").read_text(encoding="utf-8")
    assert "source_keys" in js, "app.js must send source_keys"
