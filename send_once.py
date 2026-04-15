#!/usr/bin/env python3
"""
One-shot script for GitHub Actions / cron.
Fetches prices + commentary, sends email report AND WhatsApp P&L summary, then exits.
"""

import logging
from stock_report import fetch_prices, fetch_commentary, build_email_html, send_email, send_whatsapp_pnl

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

if __name__ == "__main__":
    log.info("=== Daily Stock Report — one-shot run ===")

    log.info("Step 1/3 — Fetching live prices...")
    prices = fetch_prices()

    log.info("Step 2/3 — Fetching live commentary...")
    commentary = fetch_commentary(prices)

    log.info("Step 3/3 — Building & sending email report...")
    html = build_email_html(prices, commentary)
    send_email(html)

    log.info("Step 4/4 — Sending WhatsApp P&L summary...")
    send_whatsapp_pnl(prices)

    log.info("Done.")
