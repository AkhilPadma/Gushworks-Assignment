"""
streamlit_app.py — PackPro Lead Follow-Up Agent
Main UI: rep-centric view, buckets, detail view with unified reply panel.
"""

import streamlit as st
from datetime import datetime, date, timezone, timedelta
import re

import db
from agent import analyze_lead
from styles import inject_custom_css


st.set_page_config(
    page_title="PackPro Lead Follow-Up",
    page_icon="📦",
    layout="wide",
)
inject_custom_css()


db.init_db()
db.seed_if_empty()


# Constants
IST = timezone(timedelta(hours=5, minutes=30))

TAG_EMOJI = {"Hot": "🔥", "Warm": "☀️", "Cold": "❄️"}
TAG_COLOR = {"Hot": "#dc2626", "Warm": "#f59e0b", "Cold": "#64748b"}
TAG_BG = {"Hot": "#fef2f2", "Warm": "#fffbeb", "Cold": "#f1f5f9"}
REPS = ["Priya", "Rohit", "Anjali", "Sameer", "Vikram"]
REPS_FILTER = ["All reps"] + REPS

if "selected_rep" not in st.session_state:
    st.session_state["selected_rep"] = "Priya"


def today_str():
    return datetime.now(IST).strftime("%Y-%m-%d")


def days_from_today(d_str: str) -> int:
    try:
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 999
    return (d - datetime.now(IST).date()).days


def resolve_rep_in_draft(draft: str, rep_name: str) -> str:
    if not draft:
        return draft
    out = re.sub(r"\[rep\]", rep_name, draft, flags=re.IGNORECASE)
    out = out.rstrip()
    if out.endswith(f"— {rep_name}") or out.endswith(f"—{rep_name}"):
        return out
    if out.endswith("—"):
        return f"{out} {rep_name}"
    return out


def analyze_all_leads(force: bool = False):
    import time
    all_leads = db.get_all_leads()
    cached = db.get_all_agent_results()
    to_analyze = [l for l in all_leads if force or l["lead_id"] not in cached]
    if not to_analyze:
        return 0
    progress = st.progress(0, text=f"Analyzing {len(to_analyze)} leads...")
    for i, lead in enumerate(to_analyze, start=1):
        chat = db.get_chat(lead["lead_id"])
        result = analyze_lead(lead, chat if chat else None, today_str())
        db.save_agent_result(lead["lead_id"], result)
        progress.progress(i / len(to_analyze), text=f"Analyzing {i}/{len(to_analyze)}: {lead['name']}")
        if i < len(to_analyze):
            time.sleep(2.5)
    progress.empty()
    return len(to_analyze)


def analyze_one(lead_id: str):
    lead = db.get_lead(lead_id)
    chat = db.get_chat(lead_id)
    with st.spinner(f"Re-analyzing {lead['name']}..."):
        result = analyze_lead(lead, chat if chat else None, today_str())
        db.save_agent_result(lead_id, result)
    return result


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
all_leads = db.get_all_leads()
results = db.get_all_agent_results()
today_display = datetime.now(IST).strftime("%A, %d %b %Y")

col_a, col_b, col_c = st.columns([3, 1.5, 1.5])
with col_a:
    st.title("📦 PackPro Lead Follow-Up")
    st.caption(f"5 sales reps · {len(all_leads)} total leads · {today_display}")
with col_b:
    st.write("")
    selected_rep = st.selectbox(
        "Filter by rep",
        REPS_FILTER,
        index=REPS_FILTER.index(st.session_state["selected_rep"]),
        label_visibility="collapsed",
        key="rep_selector"
    )
    st.session_state["selected_rep"] = selected_rep
with col_c:
    st.write("")
    with st.popover("➕ Add lead", use_container_width=True):
        st.markdown("##### Add a new lead")
        with st.form("add_lead_form_main", clear_on_submit=True):
            new_name = st.text_input("Name *")
            new_company = st.text_input("Company *")
            new_phone = st.text_input("Phone")
            new_source = st.selectbox(
                "Source",
                ["WhatsApp Inquiry", "Trade Show", "Website Form", "Referral", "LinkedIn", "Cold Call"]
            )
            new_rep = st.selectbox("Assign to rep", REPS)
            new_date = st.date_input("Last contact date", value=datetime.now(IST).date())
            new_buyer_msg = st.text_area(
                "Buyer's first message (optional)",
                placeholder="Paste the WhatsApp text, form submission, or trade-show note here.",
                height=90,
            )
            submitted = st.form_submit_button("Add lead", use_container_width=True, type="primary")

            if submitted:
                if not new_name or not new_company:
                    st.error("Name and Company are required.")
                else:
                    new_id = db.add_lead(
                        new_name, new_company, new_phone, new_source,
                        new_date.strftime("%Y-%m-%d"), new_rep
                    )
                    if new_buyer_msg and new_buyer_msg.strip():
                        db.add_chat_message(new_id, "buyer", new_buyer_msg.strip())
                    analyze_one(new_id)
                    st.success(f"Added {new_name}.")
                    st.rerun()


# First-time guard — auto-run if cache empty
if not results:
    st.info("🔄 First-time setup: analyzing all leads. Takes ~2 minutes and only happens once.")
    n = analyze_all_leads(force=False)
    st.success(f"Analyzed {n} leads. Refreshing...")
    st.rerun()


# Filter by rep
if selected_rep == "All reps":
    leads = all_leads
    rep_view_label = f"All reps · {len(leads)} leads"
else:
    leads = [l for l in all_leads if l.get("assigned_rep") == selected_rep]
    rep_view_label = f"{selected_rep}'s queue · {len(leads)} leads"


# Bucket
overdue, today_bucket, upcoming, later, suppressed = [], [], [], [], []
for lead in leads:
    r = results.get(lead["lead_id"])
    if not r:
        continue
    days = days_from_today(r["next_followup_date"])
    row = {**lead, **r, "days_from_today": days}
    if days >= 150:
        suppressed.append(row)
    elif days < 0:
        overdue.append(row)
    elif days == 0:
        today_bucket.append(row)
    elif days <= 7:
        upcoming.append(row)
    else:
        later.append(row)

overdue.sort(key=lambda x: x["days_from_today"])
today_bucket.sort(key=lambda x: (x["tag"] != "Hot", x["tag"] != "Warm"))
upcoming.sort(key=lambda x: x["days_from_today"])
later.sort(key=lambda x: x["days_from_today"])


# Sidebar
with st.sidebar:
    st.header("ℹ️ About")
    st.markdown(
        """
        **PackPro Lead Follow-Up**
        An AI agent that tags leads (Hot/Warm/Cold), suggests follow-up dates,
        and drafts WhatsApp messages for your sales reps.

        **How to use:**
        1. Pick your name in the rep filter
        2. Work through Overdue → Due today
        3. Open a lead, review the AI's draft, mark as sent

        **Add new leads** via the "➕ Add lead" button at the top.
        """
    )
    st.divider()
    st.caption("Gushwork FDE assignment · Streamlit + Groq + SQLite")


# Lead card renderer
def render_bucket(title: str, rows: list, empty_msg: str):
    st.markdown(f"### {title} ({len(rows)})")
    if not rows:
        st.caption(empty_msg)
        return
    for row in rows:
        tag = row["tag"]
        emoji = TAG_EMOJI.get(tag, "•")
        days = row["days_from_today"]
        assigned = row.get("assigned_rep", "?")
        if days < 0:
            urgency = f"🔴 {-days}d overdue"
        elif days == 0:
            urgency = "🟡 due today"
        else:
            urgency = f"in {days}d"
        with st.container(border=True):
            c1, c2, c3 = st.columns([4, 2, 1])
            with c1:
                st.markdown(f"**{emoji} {row['name']}** · {row['company']}")
                st.caption(f"👤 {assigned} · {row['reason']}")
            with c2:
                st.markdown(
                    f"<span style='color:{TAG_COLOR[tag]};font-weight:600'>{tag}</span> · {urgency}",
                    unsafe_allow_html=True,
                )
                st.caption(f"Follow up: {row['next_followup_date']}")
            with c3:
                if st.button("Open", key=f"open_{row['lead_id']}", use_container_width=True):
                    st.session_state["selected_lead"] = row["lead_id"]
                    for k in list(st.session_state.keys()):
                        if k.startswith("reply_mode_") or k.startswith("reply_text_"):
                            del st.session_state[k]
                    st.rerun()


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------
if "selected_lead" in st.session_state and st.session_state["selected_lead"]:
    lid = st.session_state["selected_lead"]
    lead = db.get_lead(lid)
    result = db.get_agent_result(lid)
    chat = db.get_chat(lid)

    header_col1, header_col2 = st.columns([0.8, 6])
        # Back button + lead name on one line
    bcol, ncol = st.columns([0.1, 0.9])
    with bcol:
        if st.button("←", key="back_top", help="Back to list"):
            st.session_state["selected_lead"] = None
            st.rerun()
    with ncol:
        st.markdown(
            f"<h3 style='margin:0;padding-top:4px'>"
            f"{TAG_EMOJI.get(result['tag'], '•')} {lead['name']} — {lead['company']}"
            f"</h3>",
            unsafe_allow_html=True,
        )

    phone_raw = lead['phone']
    phone_clean = re.sub(r'[^\d+]', '', phone_raw) if phone_raw else ""
    phone_html = (
        f"<a href='tel:{phone_clean}' style='color:#2563eb;text-decoration:none;font-weight:600'>{phone_raw}</a>"
        if phone_clean else phone_raw
    )

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(f"**Phone**  \n{phone_html}", unsafe_allow_html=True)
    m2.markdown(f"**Source**  \n{lead['source']}")
    m3.markdown(f"**Assigned to**  \n{lead.get('assigned_rep', '?')}")
    m4.markdown(f"**Last contact**  \n{lead['last_contact_date']}")
    m5.markdown(f"**Follow-up**  \n{result['next_followup_date']}")

    st.markdown(
        f"<div style='background:{TAG_BG[result['tag']]};"
        f"border-left:4px solid {TAG_COLOR[result['tag']]};"
        f"padding:12px 16px;border-radius:8px;margin-top:12px;color:#0f172a'>"
        f"<span style='color:{TAG_COLOR[result['tag']]};font-weight:700;font-size:1.1rem'>"
        f"{TAG_EMOJI[result['tag']]} {result['tag'].upper()}</span>"
        f" — {result['reason']}</div>",
        unsafe_allow_html=True,
    )

    st.write("")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("#### 💬 Chat history")
        if chat:
            for msg in chat:
                who = msg["from"]
                if who == "rep":
                    bg = "#dbeafe"
                    label_color = "#1e40af"
                    margin_style = "margin:6px 0 6px 60px"
                else:
                    bg = "#f1f5f9"
                    label_color = "#475569"
                    margin_style = "margin:6px 60px 6px 0"
                st.markdown(
                    f"<div style='background:{bg};padding:10px 14px;border-radius:10px;{margin_style};color:#0f172a'>"
                    f"<div style='font-size:0.75rem;color:{label_color};font-weight:600;margin-bottom:4px'>"
                    f"{who.upper()} · {msg['date']}</div>"
                    f"<div>{msg['text']}</div></div>",
                    unsafe_allow_html=True,
                )
        else:
            st.info("No chat history yet. The agent tagged this based on source and last contact age.")

    with right:
        st.markdown("#### ✉️ Reply")

        mode_key = f"reply_mode_{lid}"
        if mode_key not in st.session_state:
            st.session_state[mode_key] = "I'm the rep"

        mode = st.radio(
            "Who's replying?",
            ["I'm the rep", "I'm the buyer"],
            horizontal=True,
            key=mode_key,
            label_visibility="collapsed"
        )

        rep_name = lead.get("assigned_rep", "the team")

        if mode == "I'm the rep":
            draft_display = resolve_rep_in_draft(result["draft_message"], rep_name)
            analyzed_at = result.get("analyzed_at", "")

            edited = st.text_area(
                "AI-generated draft (edit if needed)",
                value=draft_display,
                height=160,
                key=f"draft_rep_{lid}_{analyzed_at}",
            )

            b1, b2 = st.columns(2)
            with b1:
                if st.button("💾 Save edit", use_container_width=True, key=f"save_{lid}"):
                    db.update_draft(lid, edited)
                    st.success("Draft saved.")
                    st.rerun()
            with b2:
                already_sent = db.is_sent_today(lid)
                send_label = "📤 Send again" if already_sent else "📤 Mark as sent"
                if st.button(send_label, use_container_width=True, key=f"send_{lid}", type="primary"):
                    recent_reps = [m for m in chat if m['from'] == 'rep'][-3:]
                    if recent_reps and any(m['text'].strip() == edited.strip() for m in recent_reps):
                        st.warning("Same message was just sent. Edit before resending.")
                    else:
                        db.mark_sent(lid, edited)
                        st.success(f"Marked as sent to {lead['name']}.")
                        st.rerun()
                if already_sent:
                    st.caption("✓ Already sent to this lead today")

            if st.button("🔄 Re-analyze this lead", use_container_width=True, key=f"reanalyze_{lid}"):
                analyze_one(lid)
                st.rerun()

        else:
            buyer_text = st.text_area(
                "Type the buyer's message",
                value="",
                height=160,
                placeholder="E.g. 'Can you share the quote by Friday?' or 'Not interested right now.'",
                key=f"buyer_text_{lid}",
            )

            if st.button("Send buyer message & re-analyze",
                         use_container_width=True,
                         type="primary",
                         key=f"buyer_send_{lid}"):
                if buyer_text.strip():
                    db.add_chat_message(lid, "buyer", buyer_text.strip())
                    analyze_one(lid)
                    st.rerun()
                else:
                    st.warning("Message cannot be empty.")

else:
    st.markdown(f"#### 👤 {rep_view_label}")

    render_bucket("🔴 Overdue", overdue, "Nothing overdue. Good state.")
    render_bucket("🟡 Due today", today_bucket, "No follow-ups scheduled for today.")
    render_bucket("🟢 This week", upcoming, "No follow-ups in the next 7 days.")
    st.markdown('<div class="dormant-section">', unsafe_allow_html=True)
    render_bucket("⚪ Later / dormant", later, "No dormant leads.")
    st.markdown('</div>', unsafe_allow_html=True)

    if suppressed:
        with st.expander(f"🔕 Suppressed / opted-out ({len(suppressed)})"):
            st.caption("Leads that explicitly asked not to be contacted. Not in active queue.")
            for row in suppressed:
                st.markdown(f"- **{row['name']}** · {row['company']} — {row['reason']}")