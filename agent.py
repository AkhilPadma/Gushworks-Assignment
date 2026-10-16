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
- Untouched inbound within 0-2 days -> HOT (fresh, no apology needed — just prompt first-touch)
- Untouched inbound 3-14 days -> HOT (urgent recovery, brief apology for delay)
- Untouched inbound 14-60 days -> WARM (dropped ball, salvage with apology)
- Untouched inbound >60 days -> WARM but low priority

For rep-initiated sources (LinkedIn, Cold Call) with no chat and no response:
- <30 days -> WARM
- >30 days -> COLD

Draft for untouched inbound:
- 0-2 days old -> NO apology ("thanks for reaching out", "glad you got in touch")
- 3+ days -> brief delay acknowledgment ("apologies for the delay")

TAGGING RULES (when chat history EXISTS):
- HOT: Buyer shows clear buying signals - formal quote request, price negotiation, demo agreed, budget or deadline mentioned, deep technical questions, asking for specs/details/catalog/brochure.
- WARM: Interested but not ready - comparing vendors, asked for general info, short vague responses.
- COLD: Rep sent follow-ups, buyer did not reply, >14 days passed. OR buyer said "not interested" or "maybe next quarter."

HARD OPT-OUT DETECTION (HIGHEST PRIORITY):
If buyer says "do not contact", "don't contact", "unsubscribe", "remove me", "stop contacting", "please stop", "no further contact", or any clear opt-out:
- Tag: COLD
- next_followup_date: EXACTLY 180 days from today (effectively archive)
- Reason: "Buyer explicitly opted out — suppressed from active queue."
- Draft: brief acknowledgment ONLY, e.g. "Understood — we'll remove you from our list. Reach out anytime if that changes. —"
- NEVER schedule a near-term follow-up for an opted-out lead. This overrides all other rules.

PRIORITY OVERRIDE RULES (apply BEFORE date rules, AFTER opt-out check):
1. If the LATEST message is from BUYER and contains a question (ends in ?, or words like "what", "when", "how much", "can you", "could you") -> follow-up TODAY. Rep MUST answer.
2. If the LATEST message is from BUYER and >1 day has passed with no rep response -> follow-up TODAY. Buyer is waiting.
3. If a recent BUYER message contradicts an earlier timeline (e.g., earlier "next quarter" but recent "ready to buy") -> trust the RECENT message.

FOLLOW-UP DATE RULES (today's date is provided at top of user message):
- HOT with urgency -> TODAY or TOMORROW
- HOT without urgency -> 2-3 days
- WARM -> 5-7 days
- WARM where buyer said "will decide in X weeks" -> end of that window

COLD TIMELINE PARSING (STRICT — do not approximate):
- "next quarter": compute the START of the NEXT CALENDAR QUARTER after today, use the 15th of that month:
  * If today is Jan/Feb/Mar -> April 15 of same year
  * If today is Apr/May/Jun -> July 15 of same year
  * If today is Jul/Aug/Sep -> October 15 of same year
  * If today is Oct/Nov/Dec -> January 15 of NEXT YEAR
- "Q1" -> January 15 of relevant year
- "Q2" -> April 15 of relevant year
- "Q3" -> July 15 of relevant year
- "Q4" -> October 15 of relevant year
- "next year" -> January 15 of NEXT YEAR
- "January" or any specific month -> 15th of that month (next occurrence)
- "in [N] months" -> today + (N * 30) days
- "after [event] opens/launches/completes" + a timeline hint -> use the timeline hint
- COLD without stated timeline -> today + 30-45 days
- COLD opt-out -> today + 180 days
- UNTOUCHED inbound -> TODAY

REP DELAY DETECTION:
If rep promised ("I'll send today") and failed, draft MUST acknowledge delay ("apologies for the delay"), then deliver. Tag HOT.

NEGOTIATION DETECTION:
If buyer proposes a NEW combination the rep did NOT offer, treat as COUNTER-OFFER. Draft says "let me check and confirm by [time]" — never "thanks for confirming X." Tag HOT.

DISCOUNT & COMMITMENT RULES (CRITICAL):
- You are the REP's assistant, not the company owner. You CANNOT approve discounts, special pricing, or non-standard terms on your own.
- If buyer asks for ANY discount, special payment terms, custom specs, or extended warranty: draft MUST say "let me check with my manager and confirm by [specific date]" — NEVER agree on the spot.
- If buyer counter-offers a price: treat as COUNTER-OFFER. Draft acknowledges the ask, promises to check internally, gives a timeframe (24-48 hours). Tag HOT.
- NEVER draft messages that commit to:
  * A specific discount percentage not already offered by the rep in chat
  * A specific price lower than what rep already quoted
  * Free add-ons, extended warranty, or bundled services the rep did not already offer
  * Payment terms beyond standard (standard = 50% advance, 50% on delivery)
- If buyer asks "any more discount?" after rep already gave one, draft MUST say: "that's the best I can offer right now, let me double-check with my manager." — NEVER escalate the discount further.

NO HALLUCINATED COMMITMENTS (CRITICAL):
The draft is what REP WILL SAY — it must NEVER claim actions the rep hasn't actually done.
- NEVER write "I've prepared the quote" or "I've attached" or "I've sent" or "I've spoken to"
- INSTEAD write: "I'll prepare the quote today", "Let me put together the quote", "I'll share by [date]"
- NEVER write "We can offer X% discount" or "We'll match that price" unless the rep ALREADY offered this in prior chat
- INSTEAD write: "Let me check with my manager on pricing and confirm by [date]"
- NEVER claim a document, call, or action is already done unless the chat history clearly shows it
- The draft proposes rep ACTIONS, never claims completed ones.

DATE SANITY RULES:
- Any delivery date, meeting date, or call time you propose MUST be today or later. Never suggest past dates.
- Propose realistic FUTURE dates (e.g., "in 5-7 business days").
- Compare every date you write against today's date given at the top.

DRAFT MESSAGE RULES:
- Under 40 words, WhatsApp-friendly
- Reference something specific from the last chat
- End with a single em-dash: "—" (UI appends the rep's name)
- Sound human. Avoid "Dear Sir", "I hope this message finds you well"
- Action-oriented: propose next step as something REP will do

OUTPUT FORMAT:
Return ONLY a valid JSON object. No markdown, no code fences.
"""


# ---------------------------------------------------------------------------
# Rule-based fallback
# ---------------------------------------------------------------------------
BUYING_SIGNAL_WORDS = [
    "quote", "price", "cost", "budget", "deadline", "order", "purchase",
    "deliver", "when can you", "references", "demo", "letter", "formal",
    "negotiate", "discount", "payment", "warranty", "specification", "specs",
    "spec", "detail", "catalog", "brochure", "urgent", "urgently"
]

COLD_SIGNAL_PHRASES = [
    "not interested", "maybe later", "not now", "next quarter",
    "will reach out when", "just exploring", "already have", "next year"
]

HARD_OPT_OUT = [
    "do not contact", "don't contact", "dont contact", "unsubscribe",
    "remove me", "stop contacting", "please stop", "no further contact",
    "don't reach out", "do not reach out", "take me off"
]

DISCOUNT_WORDS = [
    "discount", "cheaper", "lower price", "better rate", "reduce",
    "negotiate", "best price", "any more", "further", "concession",
    "bring it down", "come down", "lesser price"
]


def _days_between(date_str: str, today: str) -> int:
    try:
        d1 = datetime.strptime(date_str, "%Y-%m-%d").date()
        d2 = datetime.strptime(today, "%Y-%m-%d").date()
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 0


def _format_date(today: str, days_ahead: int) -> str:
    d = datetime.strptime(today, "%Y-%m-%d").date() + timedelta(days=days_ahead)
    return d.strftime("%Y-%m-%d")


def _parse_cold_timeline(buyer_text: str, today: str) -> str:
    """
    Parse buyer's stated timeline from text and return a target follow-up date.
    Returns YYYY-MM-DD string.
    """
    text = buyer_text.lower()
    today_date = datetime.strptime(today, "%Y-%m-%d").date()
    y = today_date.year
    m = today_date.month

    # "next quarter" → start of next calendar quarter, 15th
    if "next quarter" in text:
        if m <= 3:
            return datetime(y, 4, 15).strftime("%Y-%m-%d")
        elif m <= 6:
            return datetime(y, 7, 15).strftime("%Y-%m-%d")
        elif m <= 9:
            return datetime(y, 10, 15).strftime("%Y-%m-%d")
        else:  # Oct-Dec → next year Q1
            return datetime(y + 1, 1, 15).strftime("%Y-%m-%d")

    # Explicit quarters
    if "q1" in text:
        target_year = y + 1 if m >= 1 else y
        return datetime(target_year, 1, 15).strftime("%Y-%m-%d")
    if "q2" in text:
        target_year = y + 1 if m >= 4 else y
        return datetime(target_year, 4, 15).strftime("%Y-%m-%d")
    if "q3" in text:
        target_year = y + 1 if m >= 7 else y
        return datetime(target_year, 7, 15).strftime("%Y-%m-%d")
    if "q4" in text:
        target_year = y + 1 if m >= 10 else y
        return datetime(target_year, 10, 15).strftime("%Y-%m-%d")

    # "next year"
    if "next year" in text:
        return datetime(y + 1, 1, 15).strftime("%Y-%m-%d")

    # Specific month mentions
    months = {
        "january": 1, "february": 2, "march": 3, "april": 4,
        "may": 5, "june": 6, "july": 7, "august": 8,
        "september": 9, "october": 10, "november": 11, "december": 12
    }
    for month_name, month_num in months.items():
        if month_name in text:
            target_year = y if month_num > m else y + 1
            return datetime(target_year, month_num, 15).strftime("%Y-%m-%d")

    # "in N months"
    import re
    match = re.search(r"in (\d+)\s*month", text)
    if match:
        n = int(match.group(1))
        return _format_date(today, n * 30)

    # Default cold
    return _format_date(today, 45)


def _rule_based_analysis(lead: dict, chat: list | None, today: str) -> dict:
    source = lead.get("source", "")
    name = lead.get("name", "there")
    last_contact = lead.get("last_contact_date", today)
    days_old = _days_between(last_contact, today)

    buyer_initiated_sources = {"WhatsApp Inquiry", "Website Form", "Trade Show", "Referral"}

    # ===== CASE 1: No chat history =====
    if not chat:
        if source in buyer_initiated_sources:
            if days_old <= 2:
                return {
                    "tag": "Hot",
                    "reason": f"Fresh {source.lower()} inquiry — needs first-touch today.",
                    "next_followup_date": today,
                    "draft_message": (
                        f"Hi {name}, thanks for reaching out via {source.lower()}. "
                        f"Can we set up a quick call today to discuss your packaging needs? —"
                    ),
                }
            if days_old <= 14:
                return {
                    "tag": "Hot",
                    "reason": f"Buyer reached out via {source.lower()} {days_old} days ago, no reply yet — urgent.",
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

    # ===== CASE 2: Chat exists =====
    last_msg = chat[-1]
    last_from = last_msg.get("from", "").lower()
    last_text = last_msg.get("text", "").lower()
    last_msg_date = last_msg.get("date", today)[:10]
    days_since_last_msg = _days_between(last_msg_date, today)

    buyer_msgs = [m for m in chat if m.get("from", "").lower() == "buyer"]
    buying_signal_count = sum(
        1 for m in buyer_msgs
        for word in BUYING_SIGNAL_WORDS
        if word in m.get("text", "").lower()
    )

    # PRIORITY 1: Hard opt-out
    for m in buyer_msgs:
        text = m.get("text", "").lower()
        if any(phrase in text for phrase in HARD_OPT_OUT):
            return {
                "tag": "Cold",
                "reason": "Buyer explicitly opted out — suppressed from active queue.",
                "next_followup_date": _format_date(today, 180),
                "draft_message": (
                    f"Understood, {name} — we'll remove you from our list. "
                    f"Reach out anytime if that changes. —"
                ),
            }

    # PRIORITY 2: Soft cold signals — parse timeline from buyer text
    for m in buyer_msgs:
        text = m.get("text", "").lower()
        for phrase in COLD_SIGNAL_PHRASES:
            if phrase in text:
                target_date = _parse_cold_timeline(text, today)
                return {
                    "tag": "Cold",
                    "reason": f"Buyer indicated '{phrase}' — respecting their stated timeline.",
                    "next_followup_date": target_date,
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
        # Discount request → defer to manager
        if any(w in last_text for w in DISCOUNT_WORDS):
            return {
                "tag": "Hot",
                "reason": "Buyer negotiating on price — needs manager approval, not on-spot agreement.",
                "next_followup_date": today,
                "draft_message": (
                    f"Hi {name}, I hear you on the pricing. "
                    f"Let me check with my manager on what's possible and confirm by tomorrow. —"
                ),
            }

        # Question → respond today
        is_question = "?" in last_text or any(
            w in last_text for w in ["what", "when", "how much", "can you", "could you", "how long"]
        )
        if is_question:
            return {
                "tag": "Hot",
                "reason": "Buyer asked a question — needs response today.",
                "next_followup_date": today,
                "draft_message": (
                    f"Hi {name}, thanks for the question. "
                    f"Let me get you the answer today. —"
                ),
            }

        # Specific asks
        specific_asks = ["spec", "detail", "quote", "price", "catalog", "brochure", "send me"]
        if any(ask in last_text for ask in specific_asks):
            return {
                "tag": "Hot",
                "reason": "Buyer asking for specific info — needs quick response.",
                "next_followup_date": today,
                "draft_message": (
                    f"Hi {name}, thanks for the specifics. "
                    f"Let me put the details together and share by end of day. —"
                ),
            }

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
    required = {"tag", "reason", "next_followup_date", "draft_message"}
    if not required.issubset(result.keys()):
        raise ValueError(f"Missing fields: {required - result.keys()}")
    result["tag"] = result["tag"].capitalize()
    if result["tag"] not in {"Hot", "Warm", "Cold"}:
        raise ValueError(f"Invalid tag: {result['tag']}")
    return result


def analyze_lead(lead: dict, chat: list | None, today: str) -> dict:
    try:
        client = get_groq_client()
    except Exception:
        return _rule_based_analysis(lead, chat, today)

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
                break

    return _rule_based_analysis(lead, chat, today)