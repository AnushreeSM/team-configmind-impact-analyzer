"""ConfigMind v1.0 — single Bedrock agentic loop, real downstream API calls.

Usage:
    # Copy and fill env vars first:
    cp .env.example .env

    # Start the server:
    python run.py

    # Test with a payload:
    curl -X POST http://localhost:8000/analyze \\
         -H "Authorization: Bearer <your-token>" \\
         -H "Content-Type: application/json" \\
         -d @tests/payloads/move_group.json
"""
import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    from configmind.config import BEDROCK_MODEL_ID, BEDROCK_REGION
    print("=" * 64)
    print("  ConfigMind v1.0 — AI Impact Analysis")
    print("  http://localhost:8000")
    print(f"  Bedrock model : {BEDROCK_MODEL_ID}")
    print(f"  Bedrock region: {BEDROCK_REGION}")
    print("  Docs          : http://localhost:8000/docs")
    print("=" * 64)
    uvicorn.run("configmind.app:app", host="0.0.0.0", port=8000, reload=True)
