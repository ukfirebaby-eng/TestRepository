import uvicorn
import os

if __name__ == "__main__":
    print("""
    =========================================
    DIAMOND MINER AI ENGINE INITIALIZING
    =========================================
    """)

    # 1. Validate the local environment
    print("[*] Checking physical directory structures...")
    required_dirs = ["./vaults", "./static", "./temp_uploads"]
    for directory in required_dirs:
        os.makedirs(directory, exist_ok=True)
        print(f"    -> Validated: {directory}/")

    # 2. Validate LLM provider configuration
    provider = os.environ.get("LLM_PROVIDER", "openai").lower()
    if provider == "openrouter":
        key = os.environ.get("OPENROUTER_API_KEY", "")
        key_display = f"{key[:8]}..." if len(key) > 8 else "(not set)"
        fast = os.environ.get("FAST_MODEL", "openai/gpt-4o-mini")
        smart = os.environ.get("SMART_MODEL", "openai/gpt-4o")
        print(f"[*] LLM Provider: OpenRouter  |  Key: {key_display}")
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        key_display = f"{key[:8]}..." if len(key) > 8 else "(not set)"
        fast = os.environ.get("FAST_MODEL", "gpt-4o-mini")
        smart = os.environ.get("SMART_MODEL", "gpt-4o")
        print(f"[*] LLM Provider: OpenAI     |  Key: {key_display}")
    print(f"    -> Fast model:  {fast}")
    print(f"    -> Smart model: {smart}")

    # 3. Boot the Server
    print("\n[*] Boot sequence complete. Starting Uvicorn ASGI server...")
    print("[*] Spatial Canvas UI will be available at: http://localhost:8000\n")

    # Run the FastAPI app defined in api.py
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
