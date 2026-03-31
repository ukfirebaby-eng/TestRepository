# Design: Configuration Panel for Diamond Miner Web UI

**Date:** 2026-03-31  
**Status:** Approved  

---

## Context

Diamond Miner's web UI (`static/index.html`) has no way to update the `.env` file from the browser. Users must edit `.env` manually in a text editor and restart the server to change the LLM provider, API keys, or model names. The PyQt6 desktop client (`DM_Interface`) already has a full `ConfigPanel` implementation — this design brings equivalent functionality to the web UI.

---

## Decisions

| Question | Decision |
|---|---|
| Entry point | ⚙ gear icon pinned to sidebar footer |
| Surface | Slide-in drawer from right edge, overlays current panel |
| Provider UX | Pill toggle (OpenRouter / OpenAI) — shows only the active key field |
| Save behaviour | Hot-reload: write `.env` then `load_dotenv(override=True)` — no restart |

---

## Architecture

### New API Endpoints (`api.py`)

#### `GET /api/v1/config`
Reads `.env` from `Path(__file__).parent / ".env"`. Returns all managed keys. API key values are masked to first 12 characters + `…` for any value longer than 12 chars.

Response shape:
```json
{
  "LLM_PROVIDER": "openrouter",
  "OPENAI_API_KEY": "sk-proj-nFbm…",
  "OPENROUTER_API_KEY": "sk-or-v1-285f…",
  "FAST_MODEL": "gpt-4o-mini",
  "SMART_MODEL": "nvidia/nemotron-3-super-120b-a12b:free",
  "VAULT_PATH": "C:\\Users\\windo\\Downloads\\Diamond Miner\\vaults"
}
```

If `.env` does not exist, returns all keys as empty strings — no error.

#### `POST /api/v1/config`
Accepts a JSON body with the same keys. Validates `LLM_PROVIDER` is `"openai"` or `"openrouter"` (422 otherwise). Writes `.env` using the same `_write_env()` logic already in `DM_Interface/ui/panels/config.py` — preserves unmanaged lines and comments. Calls `load_dotenv(override=True)` after writing. Returns `{"status": "applied"}`.

**Masked value passthrough:** if a key's submitted value ends with `…`, the existing value in `.env` is preserved unchanged. This prevents the masked GET response from overwriting the real key on Save.

### Helper (`core/config.py`)

Extract `_ENV_KEYS`, `_read_env()`, and `_write_env()` from `DM_Interface/ui/panels/config.py` into a new `core/config.py` module. Both `api.py` and `DM_Interface` can import from it (or `DM_Interface` can be left as-is for now — it's a separate project).

---

## Frontend (`static/index.html`)

### Sidebar change
One addition: a `<button id="config-btn">` with ⚙ icon, pinned to the bottom of the existing sidebar nav. Styled consistently with existing nav buttons.

### Drawer markup
```html
<div id="config-backdrop"></div>
<div id="config-drawer">
  <div class="config-header">
    <span>⚙ Configuration</span>
    <button id="config-close">✕</button>
  </div>

  <!-- Provider section -->
  <div class="config-section-label">PROVIDER</div>
  <div class="config-pill-row">
    <button class="config-pill active" data-provider="openrouter">OpenRouter</button>
    <button class="config-pill" data-provider="openai">OpenAI</button>
  </div>

  <!-- API key fields (mutually exclusive visibility) -->
  <div class="config-key-row" id="row-openrouter">
    <label>OpenRouter API Key</label>
    <div class="config-password-row">
      <input type="password" id="cfg-openrouter-key">
      <button class="cfg-eye">👁</button>
    </div>
  </div>
  <div class="config-key-row" id="row-openai" style="display:none">
    <label>OpenAI API Key</label>
    <div class="config-password-row">
      <input type="password" id="cfg-openai-key">
      <button class="cfg-eye">👁</button>
    </div>
  </div>

  <!-- Models section -->
  <div class="config-section-label">MODELS</div>
  <label>Fast Model</label>
  <input type="text" id="cfg-fast-model" placeholder="e.g. gpt-4o-mini">
  <label>Smart Model</label>
  <input type="text" id="cfg-smart-model" placeholder="e.g. gpt-4o">

  <!-- Vault section -->
  <div class="config-section-label">VAULT PATH</div>
  <input type="text" id="cfg-vault-path" placeholder="e.g. ./vaults">

  <div class="config-footer">
    <span id="cfg-status"></span>
    <button id="cfg-save">⚡ Save &amp; Apply</button>
  </div>
</div>
```

### JS behaviour (vanilla, no build step)

- **Open**: `GET /api/v1/config` → populate all fields; toggle `config-drawer--open` class on drawer and backdrop
- **Provider pill toggle**: clicking a pill adds `active` class, removes from other; shows/hides `#row-openrouter` / `#row-openai`
- **Eye toggle**: toggles `input.type` between `"password"` and `"text"` for each key field independently
- **Save**: collects field values; sends them as-is including masked values (ending `…`); `POST /api/v1/config`; the backend detects the `…` suffix and skips writing that key; on success sets `#cfg-status` to green "Applied ✓"; on error sets red "Error: …"
- **Close**: clicking backdrop or ✕ button removes `config-drawer--open`

### CSS
Drawer is `position: fixed; top: 0; right: -380px; width: 360px; height: 100vh` with `transition: right 0.25s ease`. The `config-drawer--open` class sets `right: 0`. Backdrop is `position: fixed; inset: 0; background: rgba(5,5,16,0.6)`, hidden by default, shown when drawer opens.

Styles match the existing Diamond Miner dark theme: `#0a0a1e` drawer background, `#1a1a3a` borders, `#4f9fff` accent, `#4caf50` success, `#ff3333` error.

---

## Testing

### `tests/test_api_config_get.py`
- Returns correct values when `.env` exists (fixture written to `tmp_path`)
- API keys masked: value `"sk-or-v1-285fb99cc144"` → `"sk-or-v1-285f…"`
- Short/empty values returned as-is (no masking)
- Returns all-empty-string dict when `.env` does not exist

### `tests/test_api_config_post.py`
- Valid body → `.env` written correctly, `load_dotenv` called once
- Invalid `LLM_PROVIDER` → 422
- Masked value passthrough: submitting `"sk-or-v1-285f…"` preserves the existing key in `.env`
- Round-trip: POST then GET returns updated non-masked values

Both files mock `load_dotenv` to avoid polluting the test process environment.

---

## Files to Create / Modify

| File | Change |
|---|---|
| `core/config.py` | New — `_ENV_KEYS`, `_read_env()`, `_write_env()` ported from `DM_Interface` |
| `api.py` | Add `GET /api/v1/config` and `POST /api/v1/config` endpoints |
| `static/index.html` | Add gear button to sidebar, config drawer markup, drawer CSS, drawer JS |
| `tests/test_api_config_get.py` | New |
| `tests/test_api_config_post.py` | New |

---

## Out of Scope

- "Test connection" button (validate key against provider API) — deferred
- Model name autocomplete / dropdown of known models — deferred
- Vault path file-browser (browser cannot access filesystem natively) — text input only
