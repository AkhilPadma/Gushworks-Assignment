"""
streamlit_app.py — PackPro Lead Follow-Up Agent
Main UI: lead buckets, detail view, draft editing.
"""

import streamlit as st
from datetime import datetime, date
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
TAG_EMOJI = {"Hot": "🔥", "Warm": "☀️", "Cold": "❄️"}
TAG_COLOR = {"Hot": "#dc2626", "Warm": "#f59e0b", "Cold": "#64748b"}
TAG_BG = {"Hot": "#fef2f2", "Warm": "#fffbeb", "Cold": "#f1f5f9"}
REPS_FILTER = ["All reps", "Priya", "Rohit", "Anjali", "Sameer", "Vikram"]


def today_str():
    return datetime.now().strftime("%Y-%m-%d")


def days_from_today(d_str: str) -> int:
    try:
        d = datetime.strptime(d_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return 999
    return (d - date.today()).days


def resolve_rep_in_draft(draft: str, rep_name: str) -> str:
    """Replace [Rep]/[rep] placeholder and ensure draft ends with em-dash + rep name."""
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
            time.sleep(2.5)  # avoid rate limits
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
today_display = datetime.now().strftime("%A, %d %b %Y")

col_a, col_b, col_c = st.columns([3, 1.3, 1])
with col_a:
    st.title("📦 PackPro Lead Follow-Up")
    st.caption(f"5 sales reps · {len(all_leads)} active leads · {today_display}")
with col_b:
    st.write("")
    selected_rep = st.selectbox("Filter by rep", REPS_FILTER, label_visibility="collapsed")
with col_c:
    st.write("")
    with st.popover("🔄 Re-run analysis", use_container_width=True):
        st.caption("Re-analyzes ALL leads from scratch. Takes ~2 min due to API rate limits.")
        if st.button("Yes, re-run all", type="primary", key="confirm_reanalyze"):
            n = analyze_all_leads(force=True)
            st.success(f"Re-analyzed {n} leads.")
            st.rerun()


# First-time guard
if not results:
    st.warning(
        "⚠️ No cached analysis found. Click '🔄 Re-run analysis' above to analyze all leads (~2 min)."
    )
    st.stop()


# Filter by rep
if selected_rep == "All reps":
    leads = all_leads
else:
    leads = [l for l in all_leads if l.get("assigned_rep") == selected_rep]


# Bucket
overdue, today_bucket, upcoming, later = [], [], [], []
for lead in leads:
    r = results.get(lead["lead_id"])
    if not r:
        continue
    days = days_from_today(r["next_followup_date"])
    row = {**lead, **r, "days_from_today": days}
    if days < 0:
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
    st.header("➕ Add new lead")
    with st.form("add_lead_form", clear_on_submit=True):
        new_name = st.text_input("Name *")
        new_company = st.text_input("Company *")
        new_phone = st.text_input("Phone")
        new_source = st.selectbox(
            "Source",
            ["WhatsApp Inquiry", "Trade Show", "Website Form", "Referral", "LinkedIn", "Cold Call"]
        )
        new_rep = st.selectbox(
            "Assign to rep",
            ["Priya", "Rohit", "Anjali", "Sameer", "Vikram"]
        )
        new_date = st.date_input("Last contact date", value=date.today())
        new_buyer_msg = st.text_area(
            "Buyer's first message (optional)",
            placeholder="Paste the WhatsApp text, form submission, or trade-show note here. Leave blank if you don't have it.",
            height=90,
            help="If you paste the buyer's first message, the agent will use it to tag the lead and draft a better reply."
        )
        submitted = st.form_submit_button("Add lead", use_container_width=True)

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
                st.success(f"Added {new_name} ({new_id}).")
                st.rerun()

    st.divider()
    st.caption("Built for Gushwork FDE assignment · Streamlit + Groq + SQLite")


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
                    st.rerun()


# ---------------------------------------------------------------------------
# Detail view
# ---------------------------------------------------------------------------
if "selected_lead" in st.session_state and st.session_state["selected_lead"]:
    lid = st.session_state["selected_lead"]
    lead = db.get_lead(lid)
    result = db.get_agent_result(lid)
    chat = db.get_chat(lid)

    # Sticky header: back button + lead name on same row
    header_col1, header_col2 = st.columns([1, 5])
    with header_col1:
        if st.button("← Back", key="back_top", use_container_width=True):
            st.session_state["selected_lead"] = None
            st.rerun()
    with header_col2:
        st.markdown(
            f"### {TAG_EMOJI.get(result['tag'], '•')} {lead['name']} — {lead['company']}"
        )

    # Lead meta
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.markdown(f"**Phone**  \n{lead['phone']}")
    m2.markdown(f"**Source**  \n{lead['source']}")
    m3.markdown(f"**Assigned to**  \n{lead.get('assigned_rep', '?')}")
    m4.markdown(f"**Last contact**  \n{lead['last_contact_date']}")
    m5.markdown(f"**Follow-up**  \n{result['next_followup_date']}")

    # Tag banner
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

    # Two columns: chat + draft
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

        st.markdown("##### Add a message")
        with st.form(f"add_msg_{lid}", clear_on_submit=True):
            who = st.selectbox("From", ["buyer", "rep"], key=f"who_{lid}")
            text = st.text_area("Message", key=f"text_{lid}", height=70)
            if st.form_submit_button("Add & re-analyze"):
                if text.strip():
                    db.add_chat_message(lid, who, text.strip())
                    analyze_one(lid)
                    st.rerun()

    with right:
        st.markdown("#### ✉️ Draft follow-up message")

        rep_name = lead.get("assigned_rep", "the team")
        draft_display = resolve_rep_in_draft(result["draft_message"], rep_name)

        analyzed_at = result.get("analyzed_at", "")
        edited = st.text_area(
            "Edit before sending",
            value=draft_display,
            height=160,
            key=f"draft_{lid}_{analyzed_at}",
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
                    st.warning("Same message was just sent to this lead. Edit before resending.")
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
    # Main list view — buckets
    render_bucket("🔴 Overdue", overdue, "Nothing overdue. Good state.")
    render_bucket("🟡 Due today", today_bucket, "No follow-ups scheduled for today.")
    render_bucket("🟢 This week", upcoming, "No follow-ups in the next 7 days.")
    st.markdown('<div class="dormant-section">', unsafe_allow_html=True)
    render_bucket("⚪ Later / dormant", later, "No dormant leads.")
    st.markdown('</div>', unsafe_allow_html=True)