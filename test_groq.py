"""
test_llm.py — Standalone Streamlit page to test Groq connectivity.

Access this by renaming it to streamlit_app.py temporarily, OR
by running: streamlit run test_llm.py (locally)

For live deploy: go to Streamlit Cloud -> Manage app -> change main file to test_llm.py
"""

import streamlit as st
import os
import time

st.set_page_config(page_title="Groq Connection Test", page_icon="🧪")

st.title("🧪 Groq Connection Test")
st.caption("Standalone diagnostic page to verify Groq API connectivity")

# ---------------------------------------------------------------------------
# Step 1: Secret check
# ---------------------------------------------------------------------------
st.header("Step 1: API Key Detection")

api_key = None
source = None

try:
    api_key = st.secrets["GROQ_API_KEY"]
    source = "st.secrets (Streamlit Cloud secrets panel OR .streamlit/secrets.toml)"
except Exception as e:
    st.warning(f"Not found in st.secrets: {e}")

if not api_key:
    api_key = os.environ.get("GROQ_API_KEY")
    if api_key:
        source = "environment variable"

if api_key:
    masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
    st.success(f"✅ Found API key from **{source}**")
    st.code(f"Key: {masked}\nLength: {len(api_key)} chars")
else:
    st.error("❌ No GROQ_API_KEY found anywhere. Add it to Streamlit Cloud secrets.")
    st.stop()

# ---------------------------------------------------------------------------
# Step 2: Groq SDK import
# ---------------------------------------------------------------------------
st.header("Step 2: Groq SDK")

try:
    from groq import Groq
    st.success("✅ Groq SDK imported")
except ImportError as e:
    st.error(f"❌ Import failed: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Step 3: Client creation
# ---------------------------------------------------------------------------
st.header("Step 3: Create Client")

try:
    client = Groq(api_key=api_key)
    st.success("✅ Client created")
except Exception as e:
    st.error(f"❌ Client creation failed: {e}")
    st.stop()

# ---------------------------------------------------------------------------
# Step 4: List models button
# ---------------------------------------------------------------------------
st.header("Step 4: List Available Models")

if st.button("🔍 List models on this account"):
    try:
        models = client.models.list()
        st.success(f"✅ Account has {len(models.data)} models:")
        for m in models.data:
            st.write(f"- `{m.id}`")
    except Exception as e:
        st.error(f"❌ Failed to list: {str(e)[:300]}")

# ---------------------------------------------------------------------------
# Step 5: Simple ping test
# ---------------------------------------------------------------------------
st.header("Step 5: Ping Test")
st.caption("Sends a 'say hello' prompt and measures response time")

col1, col2 = st.columns(2)

with col1:
    if st.button("Test gpt-oss-120b", use_container_width=True):
        with st.spinner("Calling 120b..."):
            try:
                start = time.perf_counter()
                response = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[{"role": "user", "content": "Reply with just: hello"}],
                    max_tokens=10,
                )
                elapsed = time.perf_counter() - start
                reply = response.choices[0].message.content.strip()
                st.success(f"✅ 120b: {elapsed:.2f}s")
                st.code(f"Response: {reply}")
            except Exception as e:
                err = str(e)
                if "429" in err:
                    st.warning("⚠️ 120b: RATE LIMITED (429) — wait 1 min")
                elif "401" in err:
                    st.error("❌ 120b: UNAUTHORIZED (401) — bad API key")
                elif "404" in err:
                    st.error("❌ 120b: MODEL NOT FOUND (404)")
                else:
                    st.error(f"❌ 120b: {err[:200]}")

with col2:
    if st.button("Test gpt-oss-20b", use_container_width=True):
        with st.spinner("Calling 20b..."):
            try:
                start = time.perf_counter()
                response = client.chat.completions.create(
                    model="openai/gpt-oss-20b",
                    messages=[{"role": "user", "content": "Reply with just: hello"}],
                    max_tokens=10,
                )
                elapsed = time.perf_counter() - start
                reply = response.choices[0].message.content.strip()
                st.success(f"✅ 20b: {elapsed:.2f}s")
                st.code(f"Response: {reply}")
            except Exception as e:
                err = str(e)
                if "429" in err:
                    st.warning("⚠️ 20b: RATE LIMITED (429) — wait 1 min")
                elif "401" in err:
                    st.error("❌ 20b: UNAUTHORIZED (401) — bad API key")
                elif "404" in err:
                    st.error("❌ 20b: MODEL NOT FOUND (404)")
                else:
                    st.error(f"❌ 20b: {err[:200]}")

# ---------------------------------------------------------------------------
# Step 6: JSON mode test (what the real agent uses)
# ---------------------------------------------------------------------------
st.header("Step 6: JSON Mode Test")
st.caption("This is what the real agent uses — if this fails, the agent will fall back to rules")

if st.button("🧪 Test JSON mode on gpt-oss-20b"):
    with st.spinner("Testing JSON mode..."):
        try:
            start = time.perf_counter()
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {
                        "role": "user",
                        "content": 'Return a JSON with a single key "status" and value "ok". No other text.'
                    }
                ],
                response_format={"type": "json_object"},
                max_tokens=50,
            )
            elapsed = time.perf_counter() - start
            reply = response.choices[0].message.content
            st.success(f"✅ JSON mode works: {elapsed:.2f}s")
            st.code(reply)

            import json
            parsed = json.loads(reply)
            st.write("Parsed:", parsed)
        except Exception as e:
            st.error(f"❌ JSON mode failed: {str(e)[:300]}")

# ---------------------------------------------------------------------------
# Step 7: Full agent simulation
# ---------------------------------------------------------------------------
st.header("Step 7: Real Agent Simulation")
st.caption("Simulates the EXACT call the lead-analyzer agent makes")

if st.button("🤖 Test with realistic agent prompt"):
    system_prompt = """You are a B2B sales analyst. Analyze the lead and return JSON with:
- tag (Hot/Warm/Cold)
- reason (one sentence)
- next_followup_date (YYYY-MM-DD)
- draft_message (under 40 words)
Return ONLY the JSON object."""

    user_prompt = """TODAY: 2026-10-16

LEAD: Test Customer at Test Co
Source: WhatsApp Inquiry
Last contact: 2026-10-16

CHAT:
[2026-10-16 10:00] BUYER: Hi, need pouch filling machine urgently. Budget 15L."""

    with st.spinner("Running full agent simulation..."):
        try:
            start = time.perf_counter()
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                response_format={"type": "json_object"},
                max_tokens=500,
            )
            elapsed = time.perf_counter() - start
            reply = response.choices[0].message.content
            st.success(f"✅ Agent-style call works: {elapsed:.2f}s")

            import json
            parsed = json.loads(reply)
            st.json(parsed)
        except Exception as e:
            st.error(f"❌ Agent call failed: {str(e)[:300]}")

st.divider()
st.caption("If all 7 steps pass, Groq is working. The problem is elsewhere (caching, UI).")
st.caption("If any step fails, that error tells you exactly what to fix.")
