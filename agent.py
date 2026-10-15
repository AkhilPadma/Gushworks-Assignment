"""
agent.py — Lead analysis with LLM primary + rule-based fallback.

Design principle: the user NEVER sees "agent error." If the LLM
fails for any reason (rate limit, validation, timeout, outage),
we fall back to rule-based classification using the same signals
the prompt encodes. The output format is identical either way.
"""

import json
import os
import time
from datetime import datetime, timedelta
from groq import Groq
import streamlit as st


# ---------------------------------------------------------------------------
# Groq client
# ---------------------------------------------------------------------------
def get_groq_client():
    api_key = None
    try:
        api_key = st.secrets["GROQ_API_KEY"]
    except Exception:
        api_key = os.environ.get("GROQ_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY not found. Set it in .streamlit/secrets.toml or as env var."
        )
    return Groq(api_key=api_key)


SYSTEM_PROMPT = """You are an expert B2B sales analyst for PackPro Machines, a packaging equipment company in India.

Your job: for each lead, read the information provided and output a strict JSON object with these 4 fields:
- "tag": one of "Hot", "Warm", or "Cold"
- "reason": one short sentence (max 20 words) explaining the tag
- "next_followup_date": date in YYYY-MM-DD format when the rep should contact this lead next
- "draft_message": a ready-to-send WhatsApp message the rep can send today or on the follow-up date

PRIORITY RULE — UNTOUCHED INBOUND LEADS (DROPPED-BALL):
If a lead has NO chat history AND the source is buyer-initiated (Website Form, WhatsApp Inquiry, Trade Show, Referral), the buyer reached out and the rep NEVER replied. Failure is on our side. Never tag these as Cold.
- Untouched inbound within 14 days -> HOT (urgent recovery)
- Untouched inbound 14-60 days old -> WARM (dropped ball, salvage with apology)
- Untouched inbound >60 days old -> WARM but low priority

For rep-initiated sources (LinkedIn, Cold Call) with no chat and no response:
- <30 days -> WARM
- >30 days -> COLD

Draft for untouched inbound MUST acknowledge the delay briefly ("apologies for the delay getting back"), then propose a call or share value.

TAGGING RULES (when chat history EXISTS):
- HOT: Buyer shows clear buying signals - formal quote request, price negotiation, demo agreed, budget or deadline mentioned, deep technical questions.
- WARM: Interested but not ready - comparing vendors, asked for brochure, short vague responses.
- COLD: Rep sent follow-ups, buyer did not reply, >14 days passed. OR buyer said "not interested" or "maybe next quarter."

FOLLOW-UP DATE RULES (today's date is provided):
- HOT with urgency -> TODAY or TOMORROW
- HOT without urgency -> 2-3 days
- WARM -> 5-7 days
- WARM where buyer said "will decide in X weeks" -> end of that window
- COLD who said "maybe next quarter" -> START OF NEXT QUARTER (e.g. Jan 15 for Q1)
- COLD without stated timeline -> 30-45 days
- UNTOUCHED inbound -> TODAY

REP DELAY DETECTION:
If rep promised ("I'll send today") and failed, draft MUST acknowledge delay ("apologies for the delay"), then deliver. Tag HOT.

NEGOTIATION DETECTION:
If buyer proposes a NEW combination the rep did NOT offer, treat as COUNTER-OFFER. Draft says "let me check and confirm by [time]" — never "thanks for confirming X." Tag HOT.

DRAFT MESSAGE RULES:
- Under 40 words, WhatsApp-friendly
- Reference something specific from the last chat
- End with a single em-dash: "—" (UI appends the rep's name)
- Sound human. Avoid "Dear Sir", "I hope this message finds you well"
- Action-oriented: ask for a decision or offer a specific next step

OUTPUT FORMAT:
Return ONLY a valid JSON object. No markdown, no code fences.
"""


# ---------------------------------------------------------------------------
# Rule-based fallback (no LLM — guaranteed to succeed)
# ---------------------------------------------------------------------------
BUYING_SIGNAL_WORDS = [
    "quote", "price", "cost", "budget", "deadline", "order", "purchase",
    "deliver", "when can you", "references", "demo", "letter", "formal",
    "negotiate", "discount", "payment", "warranty", "specification", "specs"
]

COLD_SIGNAL_PHRASES = [
    "not interested", "maybe later", "not now", "next quarter",
    "will reach out when", "just exploring", "already have"
]


def _days_between(date_str: str, today: str) -> int:
    """Return days between date_str and today. Positive if date_str is older."""
    try:
        d1 = datetime.strptime(date_str, "%Y-%m-%d").date()
        d2 = datetime.strptime(today, "%Y-%m-%d").date()
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 0


def _format_date(today: str, days_ahead: int) -> str:
    """Return today + days_ahead in YYYY-MM-DD."""
    d = datetime.strptime(today, "%Y-%m-%d").date() + timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")


def _rule_based_analysis(lead: dict, chat: list | None, today: str) -> dict:
    """
    Rule-based classification that mirrors the prompt's logic.
    Used as fallback when the LLM is unavailable. Always returns a valid result.
    """
    source = lead.get("source", "")
    name = lead.get("name", "there")
    last_contact = lead.get("last_contact_date", today)
    days_old = _days_between(last_contact, today)

    buyer_initiated_sources = {"WhatsApp Inquiry", "Website Form", "Trade Show", "Referral"}
    rep_initiated_sources = {"LinkedIn", "Cold Call"}

    # ===== CASE 1: No chat history =====
    if not chat:
        if source in buyer_initiated_sources:
            # Dropped-ball logic
            if days_old <= 14:
                return {
                    "tag": "Hot",
                    "reason": f"Buyer reached out via {source.lower()}, no reply sent — urgent first-touch needed.",
                    "next_followup_date": today,
                    "draft_message": (
                        f"Hi {name}, apologies for the delay getting back on your {source.lower()} inquiry. "
                        f"Can we set up a quick call this week to discuss your packaging needs? —"
                    ),
                }
            elif days_old <= 60:
                return {
                    "tag": "Warm",
                    "reason": f"Dropped ball — {source.lower()} from {days_old} days ago never got a reply.",
                    "next_followup_date": today,
                    "draft_message": (
                        f"Hi {name}, sincere apologies — your {source.lower()} from a while back got buried on our end. "
                        f"If packaging is still a need, I'd love to make it up with a quick call. —"
                    ),
                }
            else:
                return {
                    "tag": "Warm",
                    "reason": f"Very old untouched {source.lower()} ({days_old} days) — low priority but worth one attempt.",
                    "next_followup_date": _format_date(today, 2),
                    "draft_message": (
                        f"Hi {name}, apologies this is late — reaching out on your old {source.lower()}. "
                        f"If packaging is still on your roadmap, happy to share updated options. —"
                    ),
                }
        else:
            # Rep-initiated, no response
            if days_old <= 30:
                return {
                    "tag": "Warm",
                    "reason": f"Rep outreach via {source.lower()}, awaiting first response.",
                    "next_followup_date": _format_date(today, 5),
                    "draft_message": (
                        f"Hi {name}, following up on my earlier message. "
                        f"Happy to share more about how we help companies like yours. —"
                    ),
                }
            else:
                return {
                    "tag": "Cold",
                    "reason": f"No response to rep outreach in {days_old} days.",
                    "next_followup_date": _format_date(today, 30),
                    "draft_message": (
                        f"Hi {name}, circling back one last time. "
                        f"If there's interest in future, keep us in mind. —"
                    ),
                }

    # ===== CASE 2: Chat exists — analyze signals =====
    last_msg = chat[-1]
    last_from = last_msg.get("from", "").lower()
    last_text = last_msg.get("text", "").lower()
    last_msg_date = last_msg.get("date", today)[:10]
    days_since_last_msg = _days_between(last_msg_date, today)

    # Count buyer messages with buying signals
    buyer_msgs = [m for m in chat if m.get("from", "").lower() == "buyer"]
    rep_msgs = [m for m in chat if m.get("from", "").lower() == "rep"]
    buying_signal_count = sum(
        1 for m in buyer_msgs
        for word in BUYING_SIGNAL_WORDS
        if word in m.get("text", "").lower()
    )

    # Cold-signal check
    for m in buyer_msgs:
        text = m.get("text", "").lower()
        for phrase in COLD_SIGNAL_PHRASES:
            if phrase in text:
                return {
                    "tag": "Cold",
                    "reason": f"Buyer indicated '{phrase}' — respect timeline, follow up later.",
                    "next_followup_date": _format_date(today, 45),
                    "draft_message": (
                        f"Hi {name}, no rush — reaching out as discussed earlier. "
                        f"Let me know when timing is better. —"
                    ),
                }

    # Rep sent last → waiting for buyer
    if last_from == "rep" and days_since_last_msg > 14:
        return {
            "tag": "Cold",
            "reason": f"Rep followed up {days_since_last_msg} days ago, buyer did not respond.",
            "next_followup_date": _format_date(today, 30),
            "draft_message": (
                f"Hi {name}, following up one more time on our previous conversation. "
                f"Still happy to help if the need is active. —"
            ),
        }

    # Buyer sent last → we might owe a reply
    if last_from == "buyer":
        if buying_signal_count >= 2:
            return {
                "tag": "Hot",
                "reason": f"Buyer sent {buying_signal_count} messages with buying signals — active deal.",
                "next_followup_date": today,
                "draft_message": (
                    f"Hi {name}, thanks for the details. "
                    f"Let me get back to you shortly with specifics as discussed. —"
                ),
            }
        else:
            return {
                "tag": "Warm",
                "reason": "Buyer engaged recently, no strong urgency signals yet.",
                "next_followup_date": _format_date(today, 3),
                "draft_message": (
                    f"Hi {name}, thanks for your note. "
                    f"Happy to clarify further — when would be a good time to connect? —"
                ),
            }

    # Default: moderate engagement
    return {
        "tag": "Warm",
        "reason": "Conversation active, no clear urgency or disengagement.",
        "next_followup_date": _format_date(today, 5),
        "draft_message": (
            f"Hi {name}, just checking in on our last conversation. "
            f"Let me know if any questions came up. —"
        ),
    }


# ---------------------------------------------------------------------------
# LLM calls
# ---------------------------------------------------------------------------
def _call_groq(client, model_name, user_message):
    """Make a single Groq call. Returns raw text or raises."""
    response = client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
        max_tokens=800,
    )
    return response.choices[0].message.content


def _parse_json(raw_output):
    """Clean and parse LLM output."""
    cleaned = raw_output.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1:
            return json.loads(cleaned[start:end+1])
        raise ValueError(f"Could not parse JSON: {raw_output[:200]}")


def _validate(result):
    """Ensure required fields exist and tag is valid."""
    required = {"tag", "reason", "next_followup_date", "draft_message"}
    if not required.issubset(result.keys()):
        raise ValueError(f"Missing fields: {required - result.keys()}")
    result["tag"] = result["tag"].capitalize()
    if result["tag"] not in {"Hot", "Warm", "Cold"}:
        raise ValueError(f"Invalid tag: {result['tag']}")
    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def analyze_lead(lead: dict, chat: list | None, today: str) -> dict:
    """
    Analyze a lead with:
    1. LLM primary (gpt-oss-120b, then 20b)
    2. Rule-based fallback if all LLM attempts fail

    Guarantees a valid result — user never sees "agent error".
    """
    try:
        client = get_groq_client()
    except Exception:
        # No API key — fall straight to rules
        return _rule_based_analysis(lead, chat, today)

    # Build user message
    if chat:
        chat_text = "\n".join(
            f"[{msg['date']}] {msg['from'].upper()}: {msg['text']}"
            for msg in chat
        )
    else:
        chat_text = "(No chat history — only basic lead info is available.)"

    user_message = f"""TODAY'S DATE: {today}

LEAD INFO:
- Name: {lead['name']}
- Company: {lead['company']}
- Phone: {lead['phone']}
- Source: {lead['source']}
- Last contact date: {lead['last_contact_date']}

CHAT HISTORY:
{chat_text}

Analyze this lead and return the JSON object."""

    # Try LLM: 120b → 20b, with retry on 429
    models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]

    for model_name in models:
        for attempt in range(2):
            try:
                raw = _call_groq(client, model_name, user_message)
                result = _parse_json(raw)
                return _validate(result)
            except Exception as e:
                err_str = str(e)
                if "429" in err_str and attempt == 0:
                    time.sleep(6)
                    continue
                break  # try next model

    # All LLM attempts failed — rule-based fallback (always succeeds)
    return _rule_based_analysis(lead, chat, today)


if __name__ == "__main__":
    with open("data/leads.json") as f:
        leads = json.load(f)
    with open("data/chats.json") as f:
        chats = json.load(f)

    chat_by_lead = {c["lead_id"]: c["messages"] for c in chats}
    test_lead = leads[0]
    test_chat = chat_by_lead.get(test_lead["lead_id"])
    today_str = datetime.now().strftime("%Y-%m-%d")

    print(f"\nTesting on: {test_lead['name']}")
    start = time.perf_counter()
    result = analyze_lead(test_lead, test_chat, today_str)
    elapsed = time.perf_counter() - start

    print(json.dumps(result, indent=2))
    print(f"\n⏱  {elapsed:.2f}s")