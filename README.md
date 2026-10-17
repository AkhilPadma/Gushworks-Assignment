# PackPro Lead Follow-Up Agent

AI agent + web app that helps a packaging-equipment company's 5 sales reps work through their daily follow-up queue. Reads WhatsApp chat history, tags leads Hot/Warm/Cold, sets follow-up dates, drafts replies.

**Live app:** https://gushworks-assignment-fghmnmixvzn8g5gquqzf5u.streamlit.app

Built as a take-home for the Gushwork Forward Deployed Engineer role.

---

## What it does

- Reads 30 seeded leads from 6 sources (WhatsApp, Website Form, Trade Show, Referral, LinkedIn, Cold Call) and 18 WhatsApp-style chats
- Tags each lead **Hot / Warm / Cold** with a one-line reason
- Sets the next follow-up date (respects "next quarter" parsing, opt-outs, dropped-balls)
- Drafts a ready-to-send WhatsApp message
- Lets reps work a filtered queue: Overdue → Due today → This week → Later
- Lets reps edit the draft, mark as sent, add new leads/messages, and the agent re-analyzes on each change

## Stack

- **UI:** Streamlit
- **LLM:** Groq (openai/gpt-oss-120b primary, 20b fallback)
- **Storage:** SQLite (ephemeral on cloud; pre-cached `app.db` committed for instant demo load)
- **Deploy:** Streamlit Community Cloud

## How to run locally

```bash
# Clone
git clone https://github.com/AkhilPadma/Gushworks-Assignment.git
cd Gushworks-Assignment

# Virtual env
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate   # Mac/Linux

# Install
pip install -r requirements.txt

# API key
# Create .streamlit/secrets.toml with:
# GROQ_API_KEY = "your_key_here"

# Run
streamlit run streamlit_app.py
```

First launch takes ~2 min to analyze all 30 leads. Subsequent loads are instant (cached in `app.db`).

## File structure
├── streamlit_app.py # Main UI (rep queue, lead detail, reply panel)
├── agent.py # LLM agent + rule-based fallback
├── db.py # SQLite layer (leads, chats, agent results, sent log)
├── styles.py # Minimal CSS
├── data/
│ ├── leads.json # 30 seed leads
│ └── chats.json # 18 seed chats
├── app.db # Pre-cached DB (committed for fast demo load)
├── requirements.txt
└── .streamlit/secrets.toml # Groq API key (gitignored)


## How the agent decides Hot / Warm / Cold

Rules in priority order (first match wins):

**Hot** — buyer intent signals (quote/specs/pricing ask, deadline, budget, negotiation) OR dropped-ball on buyer-initiated source (apology-first draft calibrated to the gap).

**Warm** — interested but no urgency ("share catalog", mid-conversation without specifics, rep outreach with no reply <30 days).

**Cold** — silent beyond threshold (14 days for buyer-initiated, 30 days for rep-initiated), "not interested" / "next quarter" (parses to Jan 15 of next year, not a floating 90-day offset), or hard opt-out ("do not contact") which pushes +180 days and suppresses from the active queue.

### Source handling

- **Buyer-initiated** (WhatsApp, Website Form, Trade Show, Referral) → higher starting intent, dropped-ball detection active, apology framing on delay
- **Rep-initiated** (LinkedIn, Cold Call) → patient with silence (30-day threshold), no apology framing

### Guardrails

- Agent never commits to pricing — discount asks defer to the manager
- Agent never claims completed actions ("I'll prepare..." not "I've prepared...")
- Hard opt-outs are honored and suppressed from active queue
- If the LLM fails or rate-limits, a deterministic rule-based classifier takes over silently

## What would come next (not shipped)

1. **Dynamic rep assignment** — classify lead complexity (quantity, delivery, customer type) and match to rep experience tier. Returning customers auto-route to their previous rep. Prototyped as standalone V2 but kept V1 as the submission to respect scope.
2. **Monthly rep performance agent** — close rate, response-time percentiles, coaching flags.
3. **Lead health scoring** — proactive alerts for leads going cold.
4. **Real WhatsApp integration** via WhatsApp Business API.

## Known limitations

- SQLite is ephemeral on Streamlit Cloud — DB resets to the committed baseline on container restart. Fine for a demo; a production version would use Postgres or Supabase.
- Groq free tier has rate limits (30 req/min on 120b). Bulk re-analysis sleeps 2.5 sec between calls to stay under.
- The agent reads each lead in isolation — no cross-lead context (e.g., spotting a company that appears across multiple leads).

## Author

Akhil Padma · [akhilpadma021@gmail.com](mailto:akhilpadma021@gmail.com)
