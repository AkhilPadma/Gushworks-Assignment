"""
test_groq.py — Standalone test to verify Groq API connectivity.
Run this to check if your API key works and which models are responding.
"""

import os
import sys
import time

print("=" * 60)
print("GROQ CONNECTION TEST")
print("=" * 60)

# ---------------------------------------------------------------------------
# Step 1: Check if API key is accessible
# ---------------------------------------------------------------------------
print("\n[Step 1] Looking for GROQ_API_KEY...")

api_key = None

# Try environment variable first
api_key = os.environ.get("GROQ_API_KEY")
if api_key:
    print(f"✅ Found in environment variable")
else:
    print("   Not in environment variable, trying secrets.toml...")

# Try secrets.toml
if not api_key:
    try:
        import toml
        secrets = toml.load(".streamlit/secrets.toml")
        api_key = secrets.get("GROQ_API_KEY")
        if api_key:
            print(f"✅ Found in .streamlit/secrets.toml")
    except FileNotFoundError:
        print("   .streamlit/secrets.toml not found")
    except ImportError:
        print("   toml package not installed, installing...")
        os.system("pip install toml --quiet")
        import toml
        secrets = toml.load(".streamlit/secrets.toml")
        api_key = secrets.get("GROQ_API_KEY")

if not api_key:
    print("\n❌ FAIL: Could not find GROQ_API_KEY anywhere.")
    print("   Set it as environment variable OR add to .streamlit/secrets.toml")
    sys.exit(1)

# Mask the key for display
masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
print(f"   Key: {masked}")
print(f"   Length: {len(api_key)} chars")

# ---------------------------------------------------------------------------
# Step 2: Import Groq SDK
# ---------------------------------------------------------------------------
print("\n[Step 2] Importing Groq SDK...")
try:
    from groq import Groq
    print("✅ Groq SDK imported")
except ImportError as e:
    print(f"❌ FAIL: {e}")
    print("   Run: pip install groq")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 3: Create client
# ---------------------------------------------------------------------------
print("\n[Step 3] Creating Groq client...")
try:
    client = Groq(api_key=api_key)
    print("✅ Client created")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 4: List available models
# ---------------------------------------------------------------------------
print("\n[Step 4] Listing available models on your account...")
try:
    models = client.models.list()
    print(f"✅ Got {len(models.data)} models:")
    for m in models.data:
        print(f"   - {m.id}")
except Exception as e:
    print(f"❌ FAIL: {e}")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Step 5: Test simple call on each model we care about
# ---------------------------------------------------------------------------
test_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

for model_name in test_models:
    print(f"\n[Step 5] Testing {model_name}...")
    try:
        start = time.perf_counter()
        response = client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "user", "content": "Reply with just the word: hello"}
            ],
            max_tokens=10,
        )
        elapsed = time.perf_counter() - start
        reply = response.choices[0].message.content.strip()
        print(f"✅ {model_name} responded in {elapsed:.2f}s")
        print(f"   Reply: '{reply}'")
    except Exception as e:
        err_str = str(e)
        if "429" in err_str:
            print(f"⚠️  {model_name}: RATE LIMITED (429)")
            print(f"   Wait a minute and retry, or upgrade tier")
        elif "401" in err_str:
            print(f"❌ {model_name}: UNAUTHORIZED (401) — bad API key")
        elif "404" in err_str:
            print(f"❌ {model_name}: MODEL NOT FOUND (404) — model may be deprecated")
        else:
            print(f"❌ {model_name}: {err_str[:200]}")

# ---------------------------------------------------------------------------
# Step 6: Test JSON mode (what the agent actually uses)
# ---------------------------------------------------------------------------
print(f"\n[Step 6] Testing JSON mode on openai/gpt-oss-20b...")
try:
    start = time.perf_counter()
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        messages=[
            {
                "role": "user",
                "content": 'Return a JSON object with a single key "status" and value "ok". No other text.'
            }
        ],
        response_format={"type": "json_object"},
        max_tokens=50,
    )
    elapsed = time.perf_counter() - start
    reply = response.choices[0].message.content
    print(f"✅ JSON mode works in {elapsed:.2f}s")
    print(f"   Response: {reply}")

    import json
    parsed = json.loads(reply)
    print(f"   Parsed OK: {parsed}")
except Exception as e:
    print(f"❌ JSON mode failed: {str(e)[:200]}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
