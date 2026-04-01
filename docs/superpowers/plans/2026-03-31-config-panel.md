# Config Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a ⚙ gear button to the web UI that opens a slide-in settings drawer for editing `.env` values (provider, API keys, models, vault path) with hot-reload on save.

**Architecture:** A new `core/config.py` module owns `.env` read/write logic. Two new FastAPI endpoints (`GET/POST /api/v1/config`) expose it. The frontend adds a fixed ⚙ button in the top-right corner and a slide-in drawer that calls those endpoints; saving calls `load_dotenv(override=True)` so changes take effect immediately without a restart.

**Tech Stack:** Python `python-dotenv`, FastAPI/Pydantic v2, vanilla JS (no build step), CSS transitions

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `core/config.py` | Create | `_ENV_KEYS`, `read_env()`, `write_env()`, `mask_key()` |
| `requirements.txt` | Modify | Add `python-dotenv` |
| `api.py` | Modify | Import config helpers; add `ConfigUpdate` model; add `GET /api/v1/config` and `POST /api/v1/config`; add `_env_path()` helper |
| `static/index.html` | Modify | Fixed ⚙ button (top-right), drawer HTML, drawer CSS, drawer JS |
| `tests/test_config_helpers.py` | Create | Unit tests for `read_env`, `write_env`, `mask_key` |
| `tests/test_api_config_get.py` | Create | Tests for `GET /api/v1/config` |
| `tests/test_api_config_post.py` | Create | Tests for `POST /api/v1/config` |

---

## Task 1: Create `core/config.py` and unit tests

**Files:**
- Create: `core/config.py`
- Create: `tests/test_config_helpers.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_config_helpers.py`:

```python
import pytest
from pathlib import Path
from core.config import read_env, write_env, mask_key, _ENV_KEYS


class TestReadEnv:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = read_env(tmp_path / "nonexistent.env")
        assert result == {}

    def test_parses_known_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text('LLM_PROVIDER="openrouter"\nFAST_MODEL="gpt-4o-mini"\n')
        result = read_env(env)
        assert result["LLM_PROVIDER"] == "openrouter"
        assert result["FAST_MODEL"] == "gpt-4o-mini"

    def test_strips_quotes(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("OPENAI_API_KEY='sk-proj-abc'\n")
        result = read_env(env)
        assert result["OPENAI_API_KEY"] == "sk-proj-abc"

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# comment\n\nLLM_PROVIDER=\"openai\"\n")
        result = read_env(env)
        assert "LLM_PROVIDER" in result
        assert len(result) == 1


class TestWriteEnv:
    def test_writes_managed_keys(self, tmp_path):
        env = tmp_path / ".env"
        write_env(env, {"LLM_PROVIDER": "openai", "FAST_MODEL": "gpt-4o-mini"})
        content = env.read_text()
        assert 'LLM_PROVIDER="openai"' in content
        assert 'FAST_MODEL="gpt-4o-mini"' in content

    def test_preserves_comments(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("# my comment\nLLM_PROVIDER=\"openrouter\"\n")
        write_env(env, {"LLM_PROVIDER": "openai"})
        content = env.read_text()
        assert "# my comment" in content

    def test_preserves_unmanaged_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text('CUSTOM_VAR="keep-me"\nLLM_PROVIDER="openai"\n')
        write_env(env, {"LLM_PROVIDER": "openrouter"})
        content = env.read_text()
        assert 'CUSTOM_VAR="keep-me"' in content

    def test_omits_empty_values(self, tmp_path):
        env = tmp_path / ".env"
        write_env(env, {"LLM_PROVIDER": "openai", "OPENAI_API_KEY": ""})
        content = env.read_text()
        assert "OPENAI_API_KEY" not in content

    def test_round_trip(self, tmp_path):
        env = tmp_path / ".env"
        original = {
            "LLM_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "sk-or-v1-abc123",
            "FAST_MODEL": "gpt-4o-mini",
            "SMART_MODEL": "gpt-4o",
        }
        write_env(env, original)
        result = read_env(env)
        for key, val in original.items():
            assert result[key] == val


class TestMaskKey:
    def test_masks_long_values(self):
        assert mask_key("sk-or-v1-285fb99cc144") == "sk-or-v1-285f…"

    def test_does_not_mask_short_values(self):
        assert mask_key("short") == "short"

    def test_does_not_mask_empty_string(self):
        assert mask_key("") == ""

    def test_masks_exactly_at_12_chars(self):
        # 12 chars exactly — not masked (only >12 triggers masking)
        assert mask_key("abcdefghijkl") == "abcdefghijkl"

    def test_masks_13_chars(self):
        assert mask_key("abcdefghijklm") == "abcdefghijkl…"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_config_helpers.py -v
```

Expected: `ERROR` — `ModuleNotFoundError: No module named 'core.config'`

- [ ] **Step 3: Create `core/config.py`**

```python
from pathlib import Path
from typing import Dict, List

_ENV_KEYS: List[str] = [
    "VAULT_PATH",
    "LLM_PROVIDER",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "FAST_MODEL",
    "SMART_MODEL",
]


def read_env(path: Path) -> Dict[str, str]:
    """Parse KEY=VALUE lines from a .env file. Returns dict of present keys only."""
    result: Dict[str, str] = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            key, _, val = stripped.partition("=")
            result[key.strip()] = val.strip().strip('"').strip("'")
    return result


def write_env(path: Path, values: Dict[str, str]) -> None:
    """Write managed KEY=VALUE lines, preserving comments and unrecognised keys."""
    existing_lines: List[str] = []
    if path.exists():
        existing_lines = path.read_text(encoding="utf-8").splitlines()

    preserved: List[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            preserved.append(line)
            continue
        if "=" in stripped:
            key = stripped.partition("=")[0].strip()
            if key not in _ENV_KEYS:
                preserved.append(line)

    out_lines = preserved[:]
    for key in _ENV_KEYS:
        val = values.get(key, "")
        if val:
            out_lines.append(f'{key}="{val}"')
    path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")


def mask_key(value: str) -> str:
    """Return first 12 chars + '…' for values longer than 12 characters."""
    if len(value) > 12:
        return value[:12] + "\u2026"
    return value
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_config_helpers.py -v
```

Expected: all 14 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add core/config.py tests/test_config_helpers.py
git commit -m "feat: add core/config.py with read_env, write_env, mask_key"
```

---

## Task 2: Add `python-dotenv` to requirements

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add dependency**

In `requirements.txt`, add `python-dotenv` under the AI section:

```
# --- AI & LLM Integration ---
openai
httpx
python-dotenv
```

- [ ] **Step 2: Install it**

```
pip install python-dotenv
```

Expected: `Successfully installed python-dotenv-...` (or "already satisfied")

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add python-dotenv dependency"
```

---

## Task 3: Add `GET /api/v1/config` endpoint

**Files:**
- Modify: `api.py`
- Create: `tests/test_api_config_get.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_config_get.py`:

```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from api import app


def _make_mock_vault():
    mock = MagicMock()
    mock.list_documents.return_value = []
    return mock


@pytest.fixture
def client(tmp_path):
    env_file = tmp_path / ".env"
    mock_vault = _make_mock_vault()
    with patch("api.vault", mock_vault), patch("api._env_path", return_value=env_file):
        with TestClient(app) as c:
            yield c, env_file


class TestGetConfig:
    def test_returns_empty_strings_when_no_env_file(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/config")
        assert response.status_code == 200
        body = response.json()
        assert body["LLM_PROVIDER"] == ""
        assert body["FAST_MODEL"] == ""

    def test_returns_all_expected_keys(self, client):
        test_client, _ = client
        response = test_client.get("/api/v1/config")
        assert response.status_code == 200
        body = response.json()
        for key in ("LLM_PROVIDER", "OPENAI_API_KEY", "OPENROUTER_API_KEY",
                    "FAST_MODEL", "SMART_MODEL", "VAULT_PATH"):
            assert key in body

    def test_returns_plain_values_for_non_key_fields(self, client):
        test_client, env_file = client
        env_file.write_text('LLM_PROVIDER="openrouter"\nFAST_MODEL="gpt-4o-mini"\n')
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["LLM_PROVIDER"] == "openrouter"
        assert body["FAST_MODEL"] == "gpt-4o-mini"

    def test_masks_api_keys_longer_than_12_chars(self, client):
        test_client, env_file = client
        env_file.write_text('OPENROUTER_API_KEY="sk-or-v1-285fb99cc144"\n')
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["OPENROUTER_API_KEY"] == "sk-or-v1-285f\u2026"

    def test_does_not_mask_short_or_empty_keys(self, client):
        test_client, env_file = client
        env_file.write_text('OPENAI_API_KEY="short"\n')
        response = test_client.get("/api/v1/config")
        body = response.json()
        assert body["OPENAI_API_KEY"] == "short"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_config_get.py -v
```

Expected: `FAILED` — `404 Not Found` for `/api/v1/config`

- [ ] **Step 3: Add `_env_path()` helper and `GET /api/v1/config` to `api.py`**

At the top of `api.py`, add this import after the existing imports:

```python
from core.config import read_env, write_env, mask_key
```

After the existing `_active_mitigations` declaration (around line 53), add:

```python
def _env_path() -> Path:
    """Returns the path to the .env file co-located with api.py."""
    return Path(__file__).parent / ".env"
```

After the last existing route in `api.py`, add:

```python
@app.get("/api/v1/config")
async def get_config():
    """Returns current .env values; API keys masked to first 12 chars."""
    vals = read_env(_env_path())
    return {
        "LLM_PROVIDER":        vals.get("LLM_PROVIDER", ""),
        "OPENAI_API_KEY":      mask_key(vals.get("OPENAI_API_KEY", "")),
        "OPENROUTER_API_KEY":  mask_key(vals.get("OPENROUTER_API_KEY", "")),
        "FAST_MODEL":          vals.get("FAST_MODEL", ""),
        "SMART_MODEL":         vals.get("SMART_MODEL", ""),
        "VAULT_PATH":          vals.get("VAULT_PATH", ""),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_config_get.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add api.py tests/test_api_config_get.py
git commit -m "feat: add GET /api/v1/config endpoint"
```

---

## Task 4: Add `POST /api/v1/config` endpoint

**Files:**
- Modify: `api.py`
- Create: `tests/test_api_config_post.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_api_config_post.py`:

```python
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, call

from api import app


def _make_mock_vault():
    mock = MagicMock()
    mock.list_documents.return_value = []
    return mock


@pytest.fixture
def client(tmp_path):
    env_file = tmp_path / ".env"
    mock_vault = _make_mock_vault()
    with patch("api.vault", mock_vault), patch("api._env_path", return_value=env_file):
        with TestClient(app) as c:
            yield c, env_file


def _valid_body(**overrides):
    body = {
        "LLM_PROVIDER": "openrouter",
        "OPENAI_API_KEY": "",
        "OPENROUTER_API_KEY": "sk-or-v1-newvalue",
        "FAST_MODEL": "gpt-4o-mini",
        "SMART_MODEL": "gpt-4o",
        "VAULT_PATH": "./vaults",
    }
    body.update(overrides)
    return body


class TestPostConfig:
    def test_returns_applied_status(self, client):
        test_client, _ = client
        with patch("api.load_dotenv"):
            response = test_client.post("/api/v1/config", json=_valid_body())
        assert response.status_code == 200
        assert response.json() == {"status": "applied"}

    def test_writes_env_file(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body())
        content = env_file.read_text()
        assert 'LLM_PROVIDER="openrouter"' in content
        assert 'FAST_MODEL="gpt-4o-mini"' in content

    def test_calls_load_dotenv_with_override(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv") as mock_ld:
            test_client.post("/api/v1/config", json=_valid_body())
        mock_ld.assert_called_once_with(dotenv_path=env_file, override=True)

    def test_rejects_invalid_provider_with_422(self, client):
        test_client, _ = client
        with patch("api.load_dotenv"):
            response = test_client.post(
                "/api/v1/config",
                json=_valid_body(LLM_PROVIDER="anthropic"),
            )
        assert response.status_code == 422

    def test_masked_key_preserves_existing_value(self, client):
        test_client, env_file = client
        env_file.write_text('OPENROUTER_API_KEY="sk-or-v1-original-secret"\n')
        with patch("api.load_dotenv"):
            test_client.post(
                "/api/v1/config",
                json=_valid_body(OPENROUTER_API_KEY="sk-or-v1-285f\u2026"),
            )
        content = env_file.read_text()
        assert 'OPENROUTER_API_KEY="sk-or-v1-original-secret"' in content

    def test_empty_key_value_not_written(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body(OPENAI_API_KEY=""))
        content = env_file.read_text()
        assert "OPENAI_API_KEY" not in content

    def test_round_trip_get_after_post(self, client):
        test_client, env_file = client
        with patch("api.load_dotenv"):
            test_client.post("/api/v1/config", json=_valid_body(FAST_MODEL="gpt-4o"))
        response = test_client.get("/api/v1/config")
        assert response.json()["FAST_MODEL"] == "gpt-4o"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_config_post.py -v
```

Expected: `FAILED` — `404 Not Found` for `POST /api/v1/config`

- [ ] **Step 3: Add `ConfigUpdate` model and `POST /api/v1/config` to `api.py`**

At the top of `api.py`, add after the existing imports:

```python
from typing import Literal
from dotenv import load_dotenv
```

After the `get_config` endpoint added in Task 3, add:

```python
class ConfigUpdate(BaseModel):
    LLM_PROVIDER: Literal["openai", "openrouter"]
    OPENAI_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    FAST_MODEL: str = ""
    SMART_MODEL: str = ""
    VAULT_PATH: str = ""


def _resolve_key(submitted: str, existing: str) -> str:
    """If submitted value is a masked stub (ends with …), return the existing value."""
    if submitted.endswith("\u2026"):
        return existing
    return submitted


@app.post("/api/v1/config")
async def update_config(body: ConfigUpdate):
    """Writes .env and hot-reloads env vars without restarting the server."""
    env_path = _env_path()
    existing = read_env(env_path)
    values = {
        "LLM_PROVIDER":       body.LLM_PROVIDER,
        "OPENAI_API_KEY":     _resolve_key(body.OPENAI_API_KEY,     existing.get("OPENAI_API_KEY", "")),
        "OPENROUTER_API_KEY": _resolve_key(body.OPENROUTER_API_KEY, existing.get("OPENROUTER_API_KEY", "")),
        "FAST_MODEL":         body.FAST_MODEL,
        "SMART_MODEL":        body.SMART_MODEL,
        "VAULT_PATH":         body.VAULT_PATH,
    }
    write_env(env_path, values)
    load_dotenv(dotenv_path=env_path, override=True)
    return {"status": "applied"}
```

Note: `BaseModel` is already imported via `from pydantic import BaseModel` — verify this is present at the top of `api.py`. If not, add it to the existing pydantic import line.

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_config_post.py -v
```

Expected: all 7 tests `PASSED`

- [ ] **Step 5: Run the full test suite to confirm no regressions**

```
pytest tests/ -q
```

Expected: same pass count as before (pre-existing `test_vault_delete.py` failures are unrelated — onnxruntime crash on Python 3.14)

- [ ] **Step 6: Commit**

```bash
git add api.py tests/test_api_config_post.py
git commit -m "feat: add POST /api/v1/config endpoint with hot-reload"
```

---

## Task 5: Add config drawer to `static/index.html`

**Files:**
- Modify: `static/index.html`

Note: The web UI uses a top toolbar (`#toolbar`), not a sidebar. The ⚙ button is added as a **fixed-position standalone button** in the top-right corner so it's always visible regardless of which panel is active.

- [ ] **Step 1: Add CSS for the drawer**

In `static/index.html`, locate the line:

```css
#active-doc-label { color: var(--text-secondary); ...
```

Insert the following CSS block **after** that line (before `</style>`):

```css
        /* ── Config drawer ───────────────────────────────────────────── */
        #config-btn {
            position: fixed; top: 16px; right: 16px; z-index: 20;
            background: rgba(12, 21, 32, 0.9); backdrop-filter: blur(10px);
            border: 1px solid var(--border-dim); border-radius: 4px;
            color: var(--text-primary); padding: 6px 10px; cursor: pointer;
            font-size: 0.9rem; font-family: 'Syne', sans-serif;
            transition: border-color 0.2s, background 0.2s;
        }
        #config-btn:hover { border-color: var(--accent-cyan); color: var(--accent-cyan); background: rgba(0,200,255,0.06); }
        #config-backdrop {
            display: none; position: fixed; inset: 0; z-index: 90;
            background: rgba(5, 5, 16, 0.6);
        }
        #config-backdrop.config-backdrop--open { display: block; }
        #config-drawer {
            position: fixed; top: 0; right: -400px; width: 360px; height: 100vh;
            z-index: 91; background: #0a0a1e; border-left: 1px solid var(--border-dim);
            display: flex; flex-direction: column;
            transition: right 0.25s ease;
            font-family: 'Syne', sans-serif;
        }
        #config-drawer.config-drawer--open { right: 0; }
        .cfg-header {
            padding: 16px 18px 12px; border-bottom: 1px solid var(--border-dim);
            display: flex; align-items: center; justify-content: space-between;
            color: var(--accent-cyan); font-weight: 700; font-size: 0.95rem;
        }
        .cfg-close-btn { background: none; border: none; color: var(--text-secondary); cursor: pointer; font-size: 1rem; padding: 0 4px; }
        .cfg-close-btn:hover { color: var(--text-primary); }
        .cfg-body { flex: 1; overflow-y: auto; padding: 16px 18px; display: flex; flex-direction: column; gap: 8px; }
        .cfg-section-label { color: #9999bb; font-size: 0.7rem; letter-spacing: 1px; margin-top: 8px; font-family: 'JetBrains Mono', monospace; }
        .cfg-field-label { color: var(--text-secondary); font-size: 0.8rem; }
        .cfg-input {
            width: 100%; background: var(--bg-deep); border: 1px solid var(--border-dim);
            border-radius: 4px; padding: 7px 10px; color: var(--text-primary);
            font-size: 0.82rem; font-family: 'JetBrains Mono', monospace; box-sizing: border-box;
        }
        .cfg-input:focus { outline: none; border-color: var(--accent-cyan); }
        .cfg-password-row { display: flex; gap: 4px; align-items: center; }
        .cfg-password-row .cfg-input { flex: 1; }
        .cfg-eye-btn {
            background: var(--bg-deep); border: 1px solid var(--border-dim);
            border-radius: 4px; padding: 7px 8px; cursor: pointer; font-size: 0.85rem; color: var(--text-secondary);
        }
        .cfg-eye-btn:hover { border-color: var(--accent-cyan); }
        .cfg-pill-row { display: flex; gap: 6px; }
        .cfg-pill {
            background: var(--bg-deep); border: 1px solid var(--border-dim);
            color: var(--text-secondary); padding: 5px 14px; border-radius: 4px;
            cursor: pointer; font-size: 0.8rem; font-family: 'Syne', sans-serif;
            font-weight: 600; transition: all 0.15s;
        }
        .cfg-pill.active { background: #0a1f3a; border-color: var(--accent-cyan); color: var(--accent-cyan); }
        .cfg-footer {
            padding: 12px 18px; border-top: 1px solid var(--border-dim);
            display: flex; align-items: center; justify-content: space-between; gap: 8px;
        }
        #cfg-status { font-size: 0.8rem; color: var(--text-secondary); flex: 1; }
```

- [ ] **Step 2: Add the ⚙ button and drawer HTML**

Locate the line:

```html
    <div id="toolbar">
```

Insert the following **immediately before** that line:

```html
    <!-- Config gear button (always visible, top-right) -->
    <button id="config-btn" onclick="openConfigDrawer()" title="Configuration">&#9881;</button>

    <!-- Config drawer -->
    <div id="config-backdrop" onclick="closeConfigDrawer()"></div>
    <div id="config-drawer">
        <div class="cfg-header">
            <span>&#9881; Configuration</span>
            <button class="cfg-close-btn" onclick="closeConfigDrawer()">&#10005;</button>
        </div>
        <div class="cfg-body">
            <div class="cfg-section-label">PROVIDER</div>
            <div class="cfg-pill-row">
                <button id="cfg-provider-openrouter" class="cfg-pill active" onclick="cfgToggleProvider('openrouter')">OpenRouter</button>
                <button id="cfg-provider-openai" class="cfg-pill" onclick="cfgToggleProvider('openai')">OpenAI</button>
            </div>

            <div id="cfg-row-openrouter">
                <div class="cfg-field-label">OpenRouter API Key</div>
                <div class="cfg-password-row">
                    <input type="password" id="cfg-openrouter-key" class="cfg-input" placeholder="sk-or-v1-&hellip;">
                    <button class="cfg-eye-btn" onclick="cfgToggleEye('cfg-openrouter-key', this)">&#128065;</button>
                </div>
            </div>
            <div id="cfg-row-openai" style="display:none">
                <div class="cfg-field-label">OpenAI API Key</div>
                <div class="cfg-password-row">
                    <input type="password" id="cfg-openai-key" class="cfg-input" placeholder="sk-proj-&hellip;">
                    <button class="cfg-eye-btn" onclick="cfgToggleEye('cfg-openai-key', this)">&#128065;</button>
                </div>
            </div>

            <div class="cfg-section-label">MODELS</div>
            <div class="cfg-field-label">Fast Model</div>
            <input type="text" id="cfg-fast-model" class="cfg-input" placeholder="e.g. gpt-4o-mini">
            <div class="cfg-field-label">Smart Model</div>
            <input type="text" id="cfg-smart-model" class="cfg-input" placeholder="e.g. gpt-4o">

            <div class="cfg-section-label">VAULT PATH</div>
            <input type="text" id="cfg-vault-path" class="cfg-input" placeholder="e.g. ./vaults">
        </div>
        <div class="cfg-footer">
            <span id="cfg-status"></span>
            <button class="toolbar-btn" onclick="saveConfig()">&#9889; Save &amp; Apply</button>
        </div>
    </div>
```

- [ ] **Step 3: Verify HTML renders correctly**

Start the server (`python run.py`) and open `http://localhost:8000`. A ⚙ button should appear in the top-right corner. Clicking it should open the drawer. The drawer should slide in smoothly and show the PROVIDER / API KEY / MODELS / VAULT PATH sections. Close via ✕ or clicking the backdrop.

No automated test for layout — visual check is sufficient.

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat: add config drawer HTML and CSS to web UI"
```

---

## Task 6: Add config drawer JavaScript

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add the JS functions**

Locate the closing `</script>` tag at the very end of `static/index.html`. Insert the following block **immediately before** it:

```javascript
        // ── Config drawer ─────────────────────────────────────────────

        function _cfgUpdateProviderVisibility() {
            const isOR = document.getElementById('cfg-provider-openrouter').classList.contains('active');
            document.getElementById('cfg-row-openrouter').style.display = isOR ? 'block' : 'none';
            document.getElementById('cfg-row-openai').style.display    = isOR ? 'none'  : 'block';
        }

        function cfgToggleProvider(provider) {
            document.getElementById('cfg-provider-openrouter').classList.toggle('active', provider === 'openrouter');
            document.getElementById('cfg-provider-openai').classList.toggle('active',     provider === 'openai');
            _cfgUpdateProviderVisibility();
        }

        function cfgToggleEye(inputId, btn) {
            const input = document.getElementById(inputId);
            input.type = input.type === 'password' ? 'text' : 'password';
            btn.innerHTML = input.type === 'password' ? '&#128065;' : '&#128584;';
        }

        function openConfigDrawer() {
            fetch('/api/v1/config')
                .then(r => r.json())
                .then(data => {
                    const provider = data.LLM_PROVIDER || 'openrouter';
                    document.getElementById('cfg-provider-openrouter').classList.toggle('active', provider === 'openrouter');
                    document.getElementById('cfg-provider-openai').classList.toggle('active',     provider === 'openai');
                    document.getElementById('cfg-openrouter-key').value = data.OPENROUTER_API_KEY || '';
                    document.getElementById('cfg-openai-key').value     = data.OPENAI_API_KEY     || '';
                    document.getElementById('cfg-fast-model').value     = data.FAST_MODEL         || '';
                    document.getElementById('cfg-smart-model').value    = data.SMART_MODEL        || '';
                    document.getElementById('cfg-vault-path').value     = data.VAULT_PATH         || '';
                    document.getElementById('cfg-status').textContent   = '';
                    _cfgUpdateProviderVisibility();
                    document.getElementById('config-drawer').classList.add('config-drawer--open');
                    document.getElementById('config-backdrop').classList.add('config-backdrop--open');
                });
        }

        function closeConfigDrawer() {
            document.getElementById('config-drawer').classList.remove('config-drawer--open');
            document.getElementById('config-backdrop').classList.remove('config-backdrop--open');
        }

        function saveConfig() {
            const provider = document.getElementById('cfg-provider-openrouter').classList.contains('active')
                ? 'openrouter' : 'openai';
            const body = {
                LLM_PROVIDER:       provider,
                OPENAI_API_KEY:     document.getElementById('cfg-openai-key').value,
                OPENROUTER_API_KEY: document.getElementById('cfg-openrouter-key').value,
                FAST_MODEL:         document.getElementById('cfg-fast-model').value,
                SMART_MODEL:        document.getElementById('cfg-smart-model').value,
                VAULT_PATH:         document.getElementById('cfg-vault-path').value,
            };
            const status = document.getElementById('cfg-status');
            status.style.color = 'var(--text-secondary)';
            status.textContent = 'Saving\u2026';
            fetch('/api/v1/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(body),
            })
            .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(e)))
            .then(() => {
                status.style.color = '#4caf50';
                status.textContent = '\u26a1 Applied \u2713';
            })
            .catch(err => {
                status.style.color = '#ff3333';
                status.textContent = 'Error: ' + (err.detail || 'Unknown error');
            });
        }
```

- [ ] **Step 2: Smoke test the full flow**

Start the server (`python run.py`) and open `http://localhost:8000`.

1. Click ⚙ — drawer opens, fields pre-populated from current `.env`
2. Toggle provider pill between OpenRouter / OpenAI — correct key field shows/hides
3. Click 👁 on an API key — value revealed, icon changes
4. Edit Fast Model to `gpt-4o-mini-test`, click ⚡ Save & Apply
5. Status shows "⚡ Applied ✓" in green
6. Re-open drawer — Fast Model field shows `gpt-4o-mini-test`
7. Open `.env` in a text editor — confirms `FAST_MODEL="gpt-4o-mini-test"` written
8. Click backdrop — drawer closes

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add config drawer JavaScript (open, toggle, save, hot-reload)"
```

---

## Verification

Run the full test suite:

```
pytest tests/ -q
```

Expected: all new tests pass; pre-existing `test_vault_delete.py` failures are unrelated (onnxruntime crash on Python 3.14 — not caused by this work).

Full end-to-end smoke test:
1. `python run.py` → open `http://localhost:8000`
2. ⚙ button visible top-right at all times
3. Drawer opens with current `.env` values pre-loaded
4. Change provider — only the active provider's key field is shown
5. Save → status shows "⚡ Applied ✓", `.env` updated on disk, env vars live in process
