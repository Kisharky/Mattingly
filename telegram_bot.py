"""
Profit Lens — Telegram Bot
Mattingly AI & Operations Hackathon 2026 | Kishan Gowda

Deploy on Render.com (free tier):
  Start command: python telegram_bot.py
  Environment variables:
    GROQ_API_KEY       — your Groq key
    TELEGRAM_BOT_TOKEN — from @BotFather

The bot answers natural-language questions about the Profit Lens analysis
using the same Groq LLaMA model as the Streamlit app.
"""

import os
import logging
from groq import Groq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    MessageHandler,
    CommandHandler,
    filters,
    ContextTypes,
)

logging.basicConfig(level=logging.INFO)

groq_client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """
You are Profit Lens, an AI briefing assistant for Mattingly's warehouse profitability analysis.

Your role: answer questions concisely, as if briefing a CEO or Commercial Lead in 30 seconds.
Be direct. Use dollar figures. No fluff.

KEY FINDINGS (Mattingly dataset — 30 warehouse customers):

HEADLINE NUMBERS:
- True cost to pick: 26.5 cents per unit (activity-based costing on actual labour data)
- Customers are charged 12–17 cents per pick — all below cost
- Total annual pick-line underpricing: $1.5 million
- Recoverable in 9 months with structured action: $1.15 million
- 3 priority customers identified

BRAVO FMCG (highest priority):
- Current rate: 12 cents/pick | True cost: 26.5 cents/pick
- Annual exposure: $298,000
- Recommended rate: 19 cents/pick
- Recovery at 19 cents: $144,000/year
- Bravo margin at 19 cents: 33% — healthy, no reason to leave
- Action: Commercial Lead repricing conversation

DELTA MANUFACTURING (operational priority):
- Generating ~1,300 exception labour hours/year (returns, rework, urgent orders)
- Zero billing recovery on these hours
- Combined exposure: $220,000+
- Action: 2-week floor study → reprice or re-bill

CHARLIE MEDICAL (billing correction):
- 165,000 picks performed | 133,000 billed
- 32,000 picks/year going unrecovered
- Also being charged below cost
- Action: Billing correction — no negotiation required, starts immediately

THE TOOL:
- ProfitLens dashboard: role-based (CEO / Commercial Lead / Site Manager)
- CEO: monthly 30-second view — recovery tracker, decisions pending
- Commercial Lead: weekly — evidence-ready tickets, AI-prepared briefs
- Site Manager: daily 15 minutes — top 3 exception tickets
- Runs on 5 standard WMS export files — no integration required
- Live at: https://kishan-mattingly.streamlit.app/

Respond in plain English. Be brief. If asked for a specific number, give it exactly.
If asked something outside this dataset, say so honestly.
"""


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Profit Lens here.\n\n"
        "Ask me anything about the Mattingly warehouse analysis.\n\n"
        "Try:\n"
        "• What's the Bravo exposure?\n"
        "• How much can we recover in 9 months?\n"
        "• What should the CEO do first?\n"
        "• What does the Site Manager do each morning?"
    )


async def reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = update.message.text
    logging.info(f"Question from {update.effective_user.name}: {question}")

    try:
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": question},
            ],
            max_tokens=300,
            temperature=0.3,
        )
        answer = response.choices[0].message.content
    except Exception as e:
        logging.error(f"Groq error: {e}")
        answer = (
            "Sorry, I couldn't reach the AI engine right now. "
            "Key finding: Bravo at 12¢/pick vs 26.5¢ true cost = $298K exposure. "
            "Move to 19¢ = $144K recovered."
        )

    await update.message.reply_text(answer)


if __name__ == "__main__":
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, reply))

    logging.info("Profit Lens bot is running...")
    app.run_polling()
