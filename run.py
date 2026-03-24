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

    # 2. Boot the Server
    print("\n[*] Boot sequence complete. Starting Uvicorn ASGI server...")
    print("[*] Spatial Canvas UI will be available at: http://localhost:8000\n")

    # Run the FastAPI app defined in api.py
    uvicorn.run("api:app", host="127.0.0.1", port=8000, reload=False)
