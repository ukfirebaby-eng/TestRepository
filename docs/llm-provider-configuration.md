# LLM Provider Configuration

Diamond Miner supports two LLM providers: **OpenAI** (default) and **OpenRouter**. The active provider is selected at startup via environment variables — no code changes required.

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `LLM_PROVIDER` | `openai` | Provider to use: `openai` or `openrouter` |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |
| `OPENROUTER_API_KEY` | — | Required when `LLM_PROVIDER=openrouter` |
| `FAST_MODEL` | provider default (see below) | Model for extraction tasks (DeconstructorAgent, ChronosAgent) |
| `SMART_MODEL` | provider default (see below) | Model for reasoning tasks (ContradictionHunterAgent, FragilityAgent) |

### Default models

| Provider | `FAST_MODEL` | `SMART_MODEL` |
|---|---|---|
| `openai` | `gpt-4o-mini` | `gpt-4o` |
| `openrouter` | `openai/gpt-4o-mini` | `openai/gpt-4o` |

---

## Examples

### OpenAI (default)

```bash
set OPENAI_API_KEY=sk-...
python run.py
```

Startup output:
```
[*] LLM Provider: OpenAI     |  Key: sk-...
    -> Fast model:  gpt-4o-mini
    -> Smart model: gpt-4o
```

---

### OpenRouter with default models

```bash
set LLM_PROVIDER=openrouter
set OPENROUTER_API_KEY=sk-or-...
python run.py
```

Startup output:
```
[*] LLM Provider: OpenRouter  |  Key: sk-or-...
    -> Fast model:  openai/gpt-4o-mini
    -> Smart model: openai/gpt-4o
```

---

### OpenRouter with a custom smart model

```bash
set LLM_PROVIDER=openrouter
set OPENROUTER_API_KEY=sk-or-...
set SMART_MODEL=anthropic/claude-3-5-sonnet
python run.py
```

The reasoning agents (ContradictionHunterAgent, FragilityAgent) will use Claude 3.5 Sonnet; extraction agents continue using `openai/gpt-4o-mini`.

---

## How It Works

All LLM calls are routed through two helpers in [core/agents.py](../core/agents.py):

- **`_get_client()`** — returns an OpenAI-compatible client. For OpenRouter, it points the OpenAI SDK at `https://openrouter.ai/api/v1` using `OPENROUTER_API_KEY`. The four agents are unaware of which provider is active.
- **`_get_model(tier)`** — resolves the model name for `"fast"` or `"smart"` tier, consulting provider defaults and then the `FAST_MODEL`/`SMART_MODEL` overrides.

OpenRouter's API is fully OpenAI-SDK-compatible (same `chat.completions.create` interface), so the `response_format={"type": "json_object"}` parameter passed by all agents is forwarded transparently to the underlying model.

> **Note:** If you select a model that does not support JSON mode (e.g. some older open-source models on OpenRouter), the agent will raise a parse error which is caught and logged. The ingestion pipeline will continue but that chunk's analysis will be skipped.

---

## Model Name Format

OpenRouter model names use the format `provider/model-name`, e.g.:

| Model | OpenRouter name |
|---|---|
| GPT-4o | `openai/gpt-4o` |
| GPT-4o mini | `openai/gpt-4o-mini` |
| Claude 3.5 Sonnet | `anthropic/claude-3-5-sonnet` |
| Claude 3 Haiku | `anthropic/claude-3-haiku` |
| Gemini 1.5 Pro | `google/gemini-pro-1.5` |
| Llama 3.1 70B | `meta-llama/llama-3.1-70b-instruct` |

Full model list: https://openrouter.ai/models
