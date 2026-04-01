#!/usr/bin/env python3
"""
Daily Stock Report Emailer  —  AI Chip Dashboard Edition (v2)
Sends NVDA · AMD · AVGO · MU · SWKS · RGTI · ON · CRDO report
Scheduled at 06:00 SGT (Asia/Singapore) every day

Price data  : NASDAQ Official API  (no API key needed)
Commentary  : Live-scraped from StockAnalysis.com + Barchart.com
Design      : Dark-mode chip-dashboard-2 theme
"""

import os
import re
import time
import smtplib
import logging
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

# ─── Credentials ──────────────────────────────────────────────────────────────
load_dotenv()
GMAIL_SENDER       = os.getenv("GMAIL_SENDER", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
RECIPIENT_EMAIL    = os.getenv("RECIPIENT_EMAIL", "victortansgd@gmail.com")

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─── Portfolio Positions ──────────────────────────────────────────────────────
POSITIONS = {
    "AMD":  [{"shares": 500,  "entry": 202.00}],
    "AVGO": [{"shares": 350,  "entry": 335.00},
             {"shares": 500,  "entry": 362.00},
             {"shares": 200,  "entry": 360.00}],
    "SWKS": [{"shares": 500,  "entry": 65.00}],
    "RGTI": [{"shares": 2000, "entry": 26.00}],
    "ON":   [{"shares": 1000, "entry": 90.00},
             {"shares": 3000, "entry": 92.50},
             {"shares": 5000, "entry": 65.00}],
    "CRDO": [{"shares": 500,  "entry": 130.00}],
    # NVDA and MU have NO POSITION
}

# ─── Stock configuration ──────────────────────────────────────────────────────
STOCKS = [
    {
        "ticker": "NVDA", "name": "NVIDIA Corporation", "css_class": "nvda", "color": "#76b900",
        "support": [("S1 — Range floor", "$160", "watch", "TESTING"), ("S2 — Major support", "$150", "watch", "WATCH")],
        "resistance": [("R1 — MA resistance", "$174\u2013$183", "", "")],
        "fwd_pe": "35.9x", "rev_growth": "+65% YoY", "mkt_cap": "$4.1T",
        "catalyst": "Earnings May 27, 2026. Rubin chip launch late 2026. $500B backlog.",
    },
    {
        "ticker": "AMD", "name": "Advanced Micro Devices", "css_class": "amd", "color": "#ed1c24",
        "support": [("S1 — 200-day MA", "$192\u2013$193", "holding", "KEY"), ("S2 — Pivot", "$176", "watch", "WATCH")],
        "resistance": [("R1 — Prior support", "$215\u2013$225", "", "")],
        "fwd_pe": "40x", "rev_growth": "+32% YoY", "mkt_cap": "$329B",
        "catalyst": "Earnings May 5, 2026. Meta GPU deal. CPU datacenter ramp H2 2026.",
    },
    {
        "ticker": "AVGO", "name": "Broadcom Inc.", "css_class": "avgo", "color": "#ff6b6b",
        "support": [("S1 — $300 level", "$300", "watch", "RETESTING"), ("S2 — Next target", "$250", "watch", "WATCH")],
        "resistance": [("R1 — Rejection zone", "$316\u2013$350", "watch", "NEXT TEST")],
        "fwd_pe": "58.6x", "rev_growth": "+106% YoY", "mkt_cap": "$1.38T",
        "catalyst": "Earnings Jun 4, 2026. AI rev guided +140% YoY. Rosenblatt PT $500.",
    },
    {
        "ticker": "MU", "name": "Micron Technology", "css_class": "mu", "color": "#0071c5",
        "support": [("S1 — Range floor", "$80", "watch", "WATCH"), ("S2 — Major support", "$70", "watch", "LEVEL")],
        "resistance": [("R1 — Near-term", "$110\u2013$115", "", "")],
        "fwd_pe": "~10x", "rev_growth": "+38% YoY", "mkt_cap": "~$120B",
        "catalyst": "Earnings ~Jun 2026. HBM4 ramp for AI servers. NAND pricing improving.",
    },
    {
        "ticker": "SWKS", "name": "Skyworks Solutions", "css_class": "swks", "color": "#8b5cf6",
        "support": [("S1 — Recent low", "$50", "watch", "WATCH"), ("S2 — 52W low", "$45", "watch", "KEY")],
        "resistance": [("R1 — Resistance", "$65\u2013$70", "watch", "ENTRY ZONE")],
        "fwd_pe": "10x", "rev_growth": "-5% YoY", "mkt_cap": "~$8B",
        "catalyst": "Q2 2026 earnings. 5G handset recovery. Apple supply chain leverage.",
    },
    {
        "ticker": "RGTI", "name": "Rigetti Computing", "css_class": "rgti", "color": "#06b6d4",
        "support": [("S1 — Key support", "$10", "watch", "WATCH"), ("S2 — Downside", "$7", "watch", "RISK")],
        "resistance": [("R1 — Prior high", "$20\u2013$25", "watch", "RESISTANCE")],
        "fwd_pe": "N/A", "rev_growth": "+30% YoY", "mkt_cap": "~$1.5B",
        "catalyst": "Quantum computing sector momentum. Microsoft/Google partnerships driving sentiment.",
    },
    {
        "ticker": "ON", "name": "onsemi (ON Semiconductor)", "css_class": "on", "color": "#f59e0b",
        "support": [("S1 — Range floor", "$58", "watch", "WATCH"), ("S2 — 52W low", "$55", "watch", "KEY")],
        "resistance": [("R1 — Resistance", "$70\u2013$75", "watch", "NEAR-TERM"), ("R2 — Entry zone", "$90\u2013$93", "watch", "YOUR ENTRY")],
        "fwd_pe": "15x", "rev_growth": "-10% YoY", "mkt_cap": "~$27B",
        "catalyst": "EV/SiC recovery in H2 2026. Industrial cycle bottoming. AI datacenter power mgmt.",
    },
    {
        "ticker": "CRDO", "name": "Credo Technology", "css_class": "crdo", "color": "#10b981",
        "support": [("S1 — Support", "$85", "watch", "WATCH"), ("S2 — Key level", "$75", "watch", "PIVOT")],
        "resistance": [("R1 — Resistance", "$100\u2013$110", "watch", "NEAR-TERM"), ("R2 — Entry zone", "$130", "watch", "YOUR ENTRY")],
        "fwd_pe": "60x", "rev_growth": "+75% YoY", "mkt_cap": "~$14B",
        "catalyst": "AEC (Active Electrical Cable) adoption in AI datacenters. MSFT + hyperscaler volume ramp.",
    },
]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":          "text/html,application/xhtml+xml,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ══════════════════════════════════════════════════════════════════════════════
#  P&L CALCULATIONS
# ══════════════════════════════════════════════════════════════════════════════

def calc_pnl(ticker, current_price):
    """Returns dict with total_shares, cost_basis, market_value, pnl_dollar, pnl_pct, avg_entry, lots"""
    if ticker not in POSITIONS or current_price is None:
        return None
    lots = POSITIONS[ticker]
    total_shares = sum(l["shares"] for l in lots)
    cost_basis = sum(l["shares"] * l["entry"] for l in lots)
    market_value = total_shares * current_price
    pnl_dollar = market_value - cost_basis
    pnl_pct = pnl_dollar / cost_basis * 100 if cost_basis > 0 else 0
    avg_entry = cost_basis / total_shares if total_shares > 0 else 0
    lot_details = []
    for i, lot in enumerate(lots):
        lot_pnl = lot["shares"] * (current_price - lot["entry"])
        lot_pnl_pct = (current_price - lot["entry"]) / lot["entry"] * 100
        lot_details.append({
            "num": i + 1,
            "shares": lot["shares"],
            "entry": lot["entry"],
            "pnl_dollar": lot_pnl,
            "pnl_pct": lot_pnl_pct,
        })
    return {
        "total_shares": total_shares,
        "cost_basis": cost_basis,
        "market_value": market_value,
        "pnl_dollar": pnl_dollar,
        "pnl_pct": pnl_pct,
        "avg_entry": avg_entry,
        "lots": lot_details,
    }


def calc_portfolio_summary(prices):
    """Returns portfolio-level totals across all positions"""
    total_cost = 0
    total_mkt = 0
    per_stock = {}
    for ticker in POSITIONS:
        price = (prices.get(ticker) or {}).get("price")
        if price:
            pnl = calc_pnl(ticker, price)
            if pnl:
                total_cost += pnl["cost_basis"]
                total_mkt += pnl["market_value"]
                per_stock[ticker] = pnl
    total_pnl = total_mkt - total_cost
    total_pct = total_pnl / total_cost * 100 if total_cost > 0 else 0
    return {
        "total_cost": total_cost,
        "total_mkt": total_mkt,
        "total_pnl": total_pnl,
        "total_pct": total_pct,
        "per_stock": per_stock,
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 1 — PRICE DATA  (NASDAQ API)
# ══════════════════════════════════════════════════════════════════════════════

def _parse_num(raw: str) -> float:
    return float(re.sub(r"[^0-9.\-]", "", raw))


def _fetch_nasdaq(ticker: str) -> dict | None:
    url = f"https://api.nasdaq.com/api/quote/{ticker}/info?assetclass=stocks"
    try:
        r = requests.get(url, headers={**_HEADERS, "Accept": "application/json"}, timeout=15)
        r.raise_for_status()
        data    = r.json()["data"]
        primary = data["primaryData"]
        summary = data.get("summaryData", {})

        last_price = _parse_num(primary["lastSalePrice"])
        change_raw = primary.get("netChange", "0")
        change     = _parse_num(change_raw) if change_raw not in ("N/A", "", "--") else 0.0
        change_pct = _parse_num(primary.get("percentageChange", "0"))

        # 52-week range
        wk52 = summary.get("FiftyTwoWeekHighLow", {}).get("value", "")
        wk52_low, wk52_high = None, None
        if " - " in str(wk52):
            parts = str(wk52).split(" - ")
            try:
                wk52_low  = _parse_num(parts[0])
                wk52_high = _parse_num(parts[1])
            except Exception:
                pass

        return {
            "price":      last_price,
            "change":     change,
            "change_pct": change_pct,
            "prev_close": last_price - change,
            "is_realtime": primary.get("isRealTime", False),
            "timestamp":   primary.get("lastTradeTimestamp", ""),
            "wk52_low":   wk52_low,
            "wk52_high":  wk52_high,
        }
    except Exception as e:
        log.debug(f"NASDAQ API failed for {ticker}: {e}")
        return None


def fetch_prices() -> dict:
    result = {}
    for stock in STOCKS:
        ticker = stock["ticker"]
        info   = _fetch_nasdaq(ticker)
        if info:
            result[ticker] = info
            arrow = "\u25b2" if info["change"] >= 0 else "\u25bc"
            rt    = "live" if info.get("is_realtime") else "delayed"
            log.info(f"{ticker}: ${info['price']:.2f}  {arrow} {abs(info['change']):.2f} ({info['change_pct']:+.2f}%)  [{rt}]")
        else:
            log.warning(f"{ticker}: price unavailable")
            result[ticker] = {"price": None, "change": 0, "change_pct": 0,
                              "prev_close": None, "wk52_low": None, "wk52_high": None}
        time.sleep(0.6)
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 2 — COMMENTARY  (StockAnalysis + Barchart)
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_stockanalysis(ticker: str) -> dict:
    default = {"rating": None, "target": None, "analysts": None,
               "low": None, "high": None}
    try:
        r    = requests.get(
            f"https://stockanalysis.com/stocks/{ticker.lower()}/forecast/",
            headers=_HEADERS, timeout=15
        )
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)

        rating = re.search(r'consensus rating of ["\']([^"\']+)["\']', text, re.I)
        target = re.search(r'average price target of \$([0-9,.]+)', text, re.I)
        low    = re.search(r'lowest target is \$([0-9,.]+)', text, re.I)
        high   = re.search(r'highest is \$([0-9,.]+)', text, re.I)
        n_anal = re.search(r'(\d+) analysts?\b', text, re.I)

        return {
            "rating":   rating.group(1).strip() if rating else None,
            "target":   target.group(1).rstrip(",") if target else None,
            "low":      low.group(1) if low else None,
            "high":     high.group(1).rstrip(".") if high else None,
            "analysts": n_anal.group(1) if n_anal else None,
        }
    except Exception as e:
        log.debug(f"StockAnalysis failed for {ticker}: {e}")
        return default


def _scrape_barchart(ticker: str) -> str | None:
    try:
        r = requests.get(
            f"https://www.barchart.com/stocks/quotes/{ticker}/opinion",
            headers={**_HEADERS, "Referer": "https://www.barchart.com/"},
            timeout=15
        )
        r.raise_for_status()
        text = BeautifulSoup(r.text, "html.parser").get_text(" ", strip=True)
        m = re.search(
            r"Overall Average:\s*(\d+)%\s*(Buy|Sell|Hold)\s*Overall Average Signal",
            text, re.I
        )
        return f"{m.group(1)}% {m.group(2)}" if m else None
    except Exception as e:
        log.debug(f"Barchart failed for {ticker}: {e}")
        return None


def _build_commentary(ticker: str, sa: dict, bc: str | None, price: float | None) -> dict:
    """Returns dict with analyst_line, target_line, tech_line for use in template."""
    analyst_line = ""
    target_line  = ""
    tech_line    = ""
    upside_pct   = None

    if sa.get("rating") and sa.get("target"):
        n_str = f" \u00b7 {sa['analysts']} analysts" if sa.get("analysts") else ""
        analyst_line = f'{sa["rating"]}{n_str}'

        tgt = sa["target"]
        if price:
            try:
                tgt_f     = float(tgt.replace(",", ""))
                upside_pct = (tgt_f - price) / price * 100
                direction  = "upside" if upside_pct >= 0 else "downside"
                ud_str     = f"  {abs(upside_pct):.0f}% {direction}"
            except Exception:
                ud_str = ""
        else:
            ud_str = ""
        target_line = f'Avg target ${tgt}{ud_str}'
        if sa.get("low") and sa.get("high"):
            target_line += f'  |  Range ${sa["low"]}\u2013${sa["high"]}'

    if bc:
        sig = bc.split()[-1]
        if sig == "Buy":
            tech_line = f"Barchart: {bc} \u2014 bullish technicals."
        elif sig == "Sell":
            tech_line = f"Barchart: {bc} \u2014 bearish technicals."
        else:
            tech_line = f"Barchart: {bc} \u2014 mixed signals."

    return {
        "analyst_line": analyst_line,
        "target_line":  target_line,
        "tech_line":    tech_line,
        "upside_pct":   upside_pct,
        "rating":       sa.get("rating", ""),
        "target":       sa.get("target", ""),
    }


def fetch_commentary(prices: dict) -> dict:
    commentary = {}
    for stock in STOCKS:
        ticker = stock["ticker"]
        log.info(f"Fetching commentary for {ticker}...")
        sa   = _scrape_stockanalysis(ticker);  time.sleep(1.2)
        bc   = _scrape_barchart(ticker);       time.sleep(1.2)
        price = (prices.get(ticker) or {}).get("price")
        commentary[ticker] = _build_commentary(ticker, sa, bc, price)
        log.info(f"  {ticker}: {commentary[ticker]['analyst_line'][:80]}")
    return commentary


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 3 — EMAIL HTML  (chip-dashboard-2 dark theme)
# ══════════════════════════════════════════════════════════════════════════════

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#0a0c10;--surface:#111418;--border:#1e2530;--border-bright:#2a3444;
  --text:#e2e8f0;--muted:#64748b;--dim:#3a4555;
  --green:#22c55e;--green-dim:rgba(20,83,45,0.18);
  --red:#f43f5e;--red-dim:rgba(76,5,25,0.22);
  --yellow:#eab308;--yellow-dim:rgba(66,50,0,0.22);
  --blue:#38bdf8;--blue-dim:#0c2a3f;
  --nvda:#76b900;--amd:#ed1c24;--avgo:#ff6b6b;--mu:#0071c5;
  --swks:#8b5cf6;--rgti:#06b6d4;--on:#f59e0b;--crdo:#10b981;
}
*{box-sizing:border-box;margin:0;padding:0;}
body{background:var(--bg);color:var(--text);font-family:'DM Sans',Arial,sans-serif;padding:20px 16px;}
.mono{font-family:'Space Mono',monospace;}

/* ── Header ── */
.hdr{display:flex;justify-content:space-between;align-items:flex-start;
     margin-bottom:24px;padding-bottom:18px;border-bottom:2px solid var(--border);}
.hdr h1{font-family:'Space Mono',monospace;font-size:13px;font-weight:700;
        letter-spacing:.2em;color:var(--blue);text-transform:uppercase;}
.hdr p{font-size:10px;color:var(--muted);margin-top:4px;font-family:'Space Mono',monospace;}
.mkt-bar{display:flex;gap:18px;font-family:'Space Mono',monospace;font-size:10px;}
.mkt-item{text-align:right;}
.mkt-item .lbl{color:var(--muted);font-size:9px;}
.mkt-item .val{color:var(--text);font-weight:700;}
.mkt-item .neg{color:var(--red);}
.mkt-item .pos{color:var(--green);}

/* ── Alert Banner ── */
.alert-banner{background:rgba(234,179,8,0.08);border:1px solid rgba(234,179,8,0.25);
              border-left:3px solid var(--yellow);border-radius:6px;
              padding:10px 14px;margin-bottom:18px;font-size:11px;color:var(--text);}
.alert-banner .alert-title{font-family:'Space Mono',monospace;font-size:9px;
                            color:var(--yellow);letter-spacing:.12em;text-transform:uppercase;margin-bottom:5px;}

/* ── Portfolio Summary ── */
.portfolio-summary{display:grid;grid-template-columns:repeat(6,1fr);gap:10px;
                   margin-bottom:20px;background:var(--surface);
                   border:1px solid var(--border);border-radius:10px;padding:14px 16px;}
.ps-item .ps-lbl{font-family:'Space Mono',monospace;font-size:8px;color:var(--muted);
                 letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;}
.ps-item .ps-val{font-family:'Space Mono',monospace;font-size:14px;font-weight:700;color:var(--text);}
.ps-item .ps-sub{font-size:9px;color:var(--muted);margin-top:2px;}
.pnl-box{border-radius:6px;padding:6px 10px;margin-bottom:8px;}
.pnl-box.gain{background:var(--green-dim);border:1px solid rgba(34,197,94,0.2);}
.pnl-box.loss{background:var(--red-dim);border:1px solid rgba(244,63,94,0.2);}
.pnl-box.neutral{background:rgba(56,189,248,0.06);border:1px solid rgba(56,189,248,0.15);}
.pnl-box .pnl-ticker{font-family:'Space Mono',monospace;font-size:10px;font-weight:700;margin-bottom:4px;}
.pnl-box .pnl-main{font-family:'Space Mono',monospace;font-size:13px;font-weight:700;}
.pnl-box .pnl-detail{font-size:9px;color:var(--muted);margin-top:2px;line-height:1.5;}
.pnl-lot{font-size:9px;color:var(--muted);padding:2px 0;border-top:1px solid rgba(255,255,255,0.04);}

/* ── Day Change Pill ── */
.day-change{display:inline-block;padding:2px 8px;border-radius:12px;
            font-family:'Space Mono',monospace;font-size:10px;font-weight:700;}
.day-change.up{background:var(--green-dim);color:var(--green);border:1px solid rgba(34,197,94,0.25);}
.day-change.down{background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,0.25);}

/* ── Stock Grid ── */
.stocks-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:18px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
      padding:16px;position:relative;overflow:hidden;}
.card.no-position{opacity:0.6;}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.nvda::before{background:var(--nvda);}
.amd::before{background:var(--amd);}
.avgo::before{background:var(--avgo);}
.mu::before{background:var(--mu);}
.swks::before{background:var(--swks);}
.rgti::before{background:var(--rgti);}
.on::before{background:var(--on);}
.crdo::before{background:var(--crdo);}

.card-hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;}
.ticker{font-family:'Space Mono',monospace;font-size:18px;font-weight:700;}
.nvda .ticker{color:var(--nvda);}
.amd  .ticker{color:var(--amd);}
.avgo .ticker{color:var(--avgo);}
.mu   .ticker{color:var(--mu);}
.swks .ticker{color:var(--swks);}
.rgti .ticker{color:var(--rgti);}
.on   .ticker{color:var(--on);}
.crdo .ticker{color:var(--crdo);}
.cname{font-size:10px;color:var(--muted);margin-top:2px;}

/* ── Signal badges ── */
.signal-badge{padding:2px 9px;border-radius:20px;font-size:9px;font-family:'Space Mono',monospace;
              font-weight:700;letter-spacing:.08em;}
.signal-badge.no-pos{background:rgba(100,116,139,0.12);color:var(--muted);border:1px solid rgba(100,116,139,0.2);}
.signal-badge.watch{background:var(--yellow-dim);color:var(--yellow);border:1px solid rgba(234,179,8,0.25);}
.signal-badge.caution{background:var(--red-dim);color:var(--red);border:1px solid rgba(244,63,94,0.25);}
.signal-badge.recovery{background:rgba(56,189,248,0.08);color:var(--blue);border:1px solid rgba(56,189,248,0.2);}
.signal-badge.hold{background:var(--green-dim);color:var(--green);border:1px solid rgba(34,197,94,0.25);}

.price-row{display:flex;align-items:baseline;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.price-now{font-family:'Space Mono',monospace;font-size:22px;font-weight:700;color:var(--text);}

/* ── Range bar ── */
.range-sec{margin-bottom:12px;}
.range-lbl{font-size:9px;color:var(--muted);margin-bottom:5px;font-family:'Space Mono',monospace;letter-spacing:.1em;}
.range-bar{height:5px;background:var(--border);border-radius:3px;position:relative;margin-bottom:6px;}
.range-fill{position:absolute;left:0;top:0;bottom:0;border-radius:3px;
            background:linear-gradient(90deg,var(--red),var(--yellow),var(--green));}
.range-marker{position:absolute;top:-4px;width:11px;height:11px;border-radius:50%;
              background:var(--surface);border:2px solid var(--border-bright);transform:translateX(-50%);
              box-shadow:0 1px 4px rgba(0,0,0,.4);}
.entry-marker{position:absolute;top:-5px;width:12px;height:12px;
              background:var(--yellow);border:1px solid rgba(234,179,8,0.6);
              transform:translateX(-50%) rotate(45deg);
              box-shadow:0 0 6px rgba(234,179,8,0.4);}
.range-legend{display:flex;justify-content:space-between;align-items:center;
              font-size:8px;color:var(--muted);font-family:'Space Mono',monospace;margin-top:2px;}
.range-legend .entry-label{color:var(--yellow);font-size:8px;}
.range-ends{display:flex;justify-content:space-between;font-size:9px;color:var(--muted);
            font-family:'Space Mono',monospace;}

/* ── Levels ── */
.levels{margin-bottom:12px;}
.lvl-title{font-size:9px;color:var(--muted);letter-spacing:.1em;margin-bottom:6px;
           font-family:'Space Mono',monospace;text-transform:uppercase;}
.lvl-row{display:flex;justify-content:space-between;align-items:center;
         padding:4px 0;border-bottom:1px solid var(--border);font-size:11px;}
.lvl-row:last-child{border-bottom:none;}
.lvl-name{color:var(--muted);font-size:10px;}
.lvl-price{font-family:'Space Mono',monospace;font-weight:700;}
.lvl-price.support{color:var(--green);}
.lvl-price.resistance{color:var(--red);}
.lvl-price.current{color:var(--blue);}
.lvl-price.entry{color:var(--yellow);}
.lvl-tag{font-size:8px;padding:1px 5px;border-radius:8px;font-family:'Space Mono',monospace;}
.lvl-tag.broken{background:var(--red-dim);color:var(--red);}
.lvl-tag.holding{background:var(--green-dim);color:var(--green);}
.lvl-tag.watch{background:var(--yellow-dim);color:var(--yellow);}

/* ── Fundamentals ── */
.fund-grid{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:12px;}
.fund-item{background:var(--bg);border:1px solid var(--border);border-radius:5px;padding:7px 9px;}
.fund-lbl{font-size:8px;color:var(--muted);letter-spacing:.07em;text-transform:uppercase;margin-bottom:2px;}
.fund-val{font-family:'Space Mono',monospace;font-size:11px;font-weight:700;color:var(--text);}

/* ── Commentary ── */
.commentary{background:var(--blue-dim);border:1px solid rgba(56,189,248,0.15);border-radius:6px;
            padding:8px 11px;font-size:10px;margin-bottom:8px;}
.comm-label{font-size:8px;color:var(--blue);letter-spacing:.1em;text-transform:uppercase;
            margin-bottom:4px;font-family:'Space Mono',monospace;}
.comm-line{color:var(--text);line-height:1.5;margin-bottom:3px;}
.comm-line:last-child{margin-bottom:0;}
.comm-line.tech{color:var(--muted);}

/* ── Catalyst ── */
.catalyst{background:var(--green-dim);border:1px solid rgba(34,197,94,0.15);border-radius:6px;padding:7px 11px;font-size:10px;}
.cat-lbl{font-size:8px;color:var(--green);letter-spacing:.1em;text-transform:uppercase;
         margin-bottom:3px;font-family:'Space Mono',monospace;}
.cat-text{color:var(--muted);line-height:1.45;}

/* ── History Panel ── */
.history-panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;
               padding:16px;margin-bottom:18px;}
.history-panel .panel-title{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:.15em;
                             color:var(--blue);text-transform:uppercase;margin-bottom:12px;
                             padding-bottom:9px;border-bottom:1px solid var(--border);}
.hist-table{width:100%;border-collapse:collapse;font-size:11px;}
.hist-table th{font-family:'Space Mono',monospace;font-size:8px;color:var(--muted);
               letter-spacing:.08em;text-transform:uppercase;padding:5px 8px;
               border-bottom:1px solid var(--border);text-align:left;}
.hist-table td{padding:6px 8px;border-bottom:1px solid rgba(30,37,48,0.6);color:var(--text);}
.hist-table tr:last-child td{border-bottom:none;}
.hist-table .mono{font-family:'Space Mono',monospace;}
.hist-table .gain{color:var(--green);}
.hist-table .loss{color:var(--red);}
.hist-table .placeholder{color:var(--dim);font-style:italic;font-size:10px;}

/* ── Bottom panels ── */
.bottom-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px;}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;}
.panel-title{font-family:'Space Mono',monospace;font-size:9px;letter-spacing:.15em;
             color:var(--blue);text-transform:uppercase;margin-bottom:12px;
             padding-bottom:9px;border-bottom:1px solid var(--border);}

.factor-row{display:flex;align-items:flex-start;gap:9px;padding:7px 0;
            border-bottom:1px solid var(--border);font-size:11px;}
.factor-row:last-child{border-bottom:none;}
.ficon{width:20px;height:20px;border-radius:4px;display:flex;align-items:center;
       justify-content:center;font-size:10px;flex-shrink:0;margin-top:1px;}
.ficon.green{background:var(--green-dim);color:var(--green);}
.ficon.red{background:var(--red-dim);color:var(--red);}
.ficon.yellow{background:var(--yellow-dim);color:var(--yellow);}
.fcontent .fname{font-weight:500;color:var(--text);margin-bottom:2px;font-size:11px;}
.fcontent .fdesc{color:var(--muted);font-size:10px;line-height:1.4;}

.macro-item{display:flex;justify-content:space-between;align-items:center;
            padding:7px 0;border-bottom:1px solid var(--border);font-size:11px;}
.macro-item:last-child{border-bottom:none;}
.macro-lbl{color:var(--muted);}
.macro-val{font-family:'Space Mono',monospace;font-weight:700;}
.macro-val.danger{color:var(--red);}
.macro-val.caution{color:var(--yellow);}
.macro-val.ok{color:var(--green);}

.timeline{position:relative;padding-left:14px;}
.timeline::before{content:'';position:absolute;left:4px;top:8px;bottom:8px;
                  width:1px;background:var(--border);}
.tl-item{position:relative;padding:0 0 14px 12px;}
.tl-item:last-child{padding-bottom:0;}
.tl-item::before{content:'';position:absolute;left:-10px;top:6px;width:7px;height:7px;
                 border-radius:50%;border:1px solid var(--border-bright);background:var(--surface);}
.tl-item.upcoming::before{background:var(--blue);border-color:var(--blue);}
.t-date{font-family:'Space Mono',monospace;font-size:9px;color:var(--blue);margin-bottom:2px;}
.t-event{font-size:11px;font-weight:500;color:var(--text);}
.t-detail{font-size:10px;color:var(--muted);margin-top:2px;}

footer{text-align:center;font-size:9px;color:var(--dim);font-family:'Space Mono',monospace;
       padding-top:14px;border-top:1px solid var(--border);}
</style>
"""


def _range_marker_pct(price: float, low: float, high: float) -> int:
    if high == low:
        return 50
    return int(min(max((price - low) / (high - low) * 100, 2), 98))


def _signal_badge_for_position(pnl_data) -> str:
    """For stocks with positions, badge based on P&L"""
    if pnl_data is None:
        return '<span class="signal-badge no-pos">NO POSITION</span>'
    pct = pnl_data["pnl_pct"]
    if pct >= 5:
        return '<span class="signal-badge hold">HOLD</span>'
    elif pct >= -5:
        return '<span class="signal-badge watch">WATCH</span>'
    elif pct >= -15:
        return '<span class="signal-badge caution">CAUTION</span>'
    else:
        return '<span class="signal-badge caution">CAUTION</span>'


def _build_card(stock: dict, info: dict, comm: dict, prices: dict) -> str:
    ticker    = stock["ticker"]
    css       = stock["css_class"]
    price     = info.get("price")
    change    = info.get("change", 0)
    chg_pct   = info.get("change_pct", 0)
    wk52_low  = info.get("wk52_low")
    wk52_high = info.get("wk52_high")

    has_position = ticker in POSITIONS
    pnl_data = calc_pnl(ticker, price) if has_position else None

    # Price display
    price_str = f"${price:.2f}" if price else "N/A"
    chg_cls   = "up" if change >= 0 else "down"
    chg_arrow = "\u25b2" if change >= 0 else "\u25bc"
    chg_str   = f"{chg_arrow} {abs(change):.2f} ({abs(chg_pct):.2f}%)"

    # From 52W high
    from_high_str = ""
    if price and wk52_high:
        fh = (price - wk52_high) / wk52_high * 100
        from_high_str = f"  {fh:.1f}% from 52W high"

    # Range bar with optional entry marker
    range_html = ""
    if price and wk52_low and wk52_high:
        pct = _range_marker_pct(price, wk52_low, wk52_high)
        entry_marker_html = ""
        entry_label_html = ""
        if pnl_data:
            avg_entry = pnl_data["avg_entry"]
            entry_pct = _range_marker_pct(avg_entry, wk52_low, wk52_high)
            entry_marker_html = f'<div class="entry-marker" style="left:{entry_pct}%" title="Avg Entry ${avg_entry:.2f}"></div>'
            entry_label_html = f'<span class="entry-label">&#9670; Avg Entry ${avg_entry:.2f}</span>'
        range_html = f"""
        <div class="range-sec">
          <div class="range-lbl">52-WEEK RANGE</div>
          <div class="range-bar">
            <div class="range-fill" style="width:100%"></div>
            <div class="range-marker" style="left:{pct}%"></div>
            {entry_marker_html}
          </div>
          <div class="range-ends">
            <span>${wk52_low:.2f}</span>
            <span>{price_str}</span>
            <span>${wk52_high:.2f}</span>
          </div>
          <div class="range-legend">
            <span>52W Low</span>
            {entry_label_html}
            <span>52W High</span>
          </div>
        </div>"""

    # Support / resistance levels
    lvl_rows = f"""
      <div class="lvl-row">
        <span class="lvl-name">Current</span>
        <span class="lvl-price current">{price_str}</span>
        <span></span>
      </div>"""
    for lname, lprice, ltag_cls, ltag_text in stock["support"]:
        tag = f'<span class="lvl-tag {ltag_cls}">{ltag_text}</span>' if ltag_text else ""
        lvl_rows += f"""
      <div class="lvl-row">
        <span class="lvl-name">{lname}</span>
        <span class="lvl-price support">{lprice}</span>
        {tag}
      </div>"""
    for rname, rprice, rtag_cls, rtag_text in stock["resistance"]:
        tag = f'<span class="lvl-tag {rtag_cls}">{rtag_text}</span>' if rtag_text else ""
        lvl_rows += f"""
      <div class="lvl-row">
        <span class="lvl-name">{rname}</span>
        <span class="lvl-price resistance">{rprice}</span>
        {tag}
      </div>"""

    # Avg entry row for positions
    if pnl_data:
        avg_entry = pnl_data["avg_entry"]
        stop_est  = avg_entry * 0.92
        lvl_rows += f"""
      <div class="lvl-row">
        <span class="lvl-name" style="color:var(--yellow)">Avg Entry</span>
        <span class="lvl-price entry">${avg_entry:.2f}</span>
        <span class="lvl-tag watch">YOURS</span>
      </div>
      <div class="lvl-row">
        <span class="lvl-name">Stop Est. (-8%)</span>
        <span class="lvl-price" style="color:var(--red)">${stop_est:.2f}</span>
        <span></span>
      </div>"""

    # Analyst target row
    if comm.get("target"):
        upside_pct = comm.get("upside_pct")
        tag_text = f"+{abs(upside_pct):.0f}%" if upside_pct and upside_pct > 0 else ""
        tag      = f'<span class="lvl-tag holding">{tag_text}</span>' if tag_text else ""
        lvl_rows += f"""
      <div class="lvl-row">
        <span class="lvl-name">Analyst Target</span>
        <span class="lvl-price" style="color:var(--yellow)">${comm['target']}</span>
        {tag}
      </div>"""

    # P&L Box for positions
    pnl_html = ""
    if pnl_data:
        pnl_cls = "gain" if pnl_data["pnl_dollar"] >= 0 else "loss"
        pnl_sign = "+" if pnl_data["pnl_dollar"] >= 0 else ""
        pnl_html = f"""
    <div class="pnl-box {pnl_cls}">
      <div class="pnl-ticker">{ticker} P&amp;L</div>
      <div class="pnl-main mono">{pnl_sign}${pnl_data['pnl_dollar']:,.0f} ({pnl_sign}{pnl_data['pnl_pct']:.1f}%)</div>
      <div class="pnl-detail">
        {pnl_data['total_shares']:,} shares &nbsp;|&nbsp; Cost ${pnl_data['cost_basis']:,.0f} &nbsp;|&nbsp; Mkt ${pnl_data['market_value']:,.0f}
      </div>"""
        for lot in pnl_data["lots"]:
            lot_sign = "+" if lot["pnl_dollar"] >= 0 else ""
            lot_cls = "gain" if lot["pnl_dollar"] >= 0 else "loss"
            pnl_html += f"""
      <div class="pnl-lot">Lot {lot['num']}: {lot['shares']:,}sh @ ${lot['entry']:.2f} &rarr; <span class="{lot_cls}">{lot_sign}${lot['pnl_dollar']:,.0f} ({lot_sign}{lot['pnl_pct']:.1f}%)</span></div>"""
        pnl_html += """
    </div>"""

    # Fund grid
    rev_color = "var(--green)" if "+" in stock["rev_growth"] else "var(--red)"
    rating_color = "var(--green)" if comm.get("rating") and "buy" in (comm.get("rating") or "").lower() else "var(--yellow)"
    fund_html = f"""
    <div class="fund-grid">
      <div class="fund-item">
        <div class="fund-lbl">Fwd P/E</div>
        <div class="fund-val mono">{stock['fwd_pe']}</div>
      </div>
      <div class="fund-item">
        <div class="fund-lbl">Rev Growth</div>
        <div class="fund-val mono" style="color:{rev_color}">{stock['rev_growth']}</div>
      </div>
      <div class="fund-item">
        <div class="fund-lbl">Analyst Rating</div>
        <div class="fund-val mono" style="color:{rating_color}">{comm.get('rating') or 'N/A'}</div>
      </div>
      <div class="fund-item">
        <div class="fund-lbl">Mkt Cap</div>
        <div class="fund-val mono">{stock['mkt_cap']}</div>
      </div>
    </div>"""

    # Commentary block
    comm_html = ""
    lines = []
    if comm.get("analyst_line"):
        lines.append(f'<div class="comm-line">{comm["analyst_line"]}</div>')
    if comm.get("target_line"):
        lines.append(f'<div class="comm-line">{comm["target_line"]}</div>')
    if comm.get("tech_line"):
        lines.append(f'<div class="comm-line tech">{comm["tech_line"]}</div>')
    if lines:
        comm_html = f"""
    <div class="commentary">
      <div class="comm-label">Analyst Commentary</div>
      {"".join(lines)}
    </div>"""

    # Signal badge
    if has_position:
        badge = _signal_badge_for_position(pnl_data)
    else:
        badge = '<span class="signal-badge no-pos">NO POSITION</span>'

    no_pos_class = " no-position" if not has_position else ""

    return f"""
  <div class="card {css}{no_pos_class}">
    <div class="card-hdr">
      <div>
        <div class="ticker">{ticker}</div>
        <div class="cname">{stock['name']}</div>
      </div>
      {badge}
    </div>
    <div class="price-row">
      <div class="price-now mono">{price_str}</div>
      <span class="day-change {chg_cls} mono">{chg_str}</span>
    </div>
    {range_html}
    {pnl_html}
    <div class="levels">
      <div class="lvl-title">Price Levels</div>
      {lvl_rows}
    </div>
    {fund_html}
    {comm_html}
    <div class="catalyst">
      <div class="cat-lbl">Next Catalyst</div>
      <div class="cat-text">{stock['catalyst']}</div>
    </div>
  </div>"""


def _build_portfolio_summary(prices: dict) -> str:
    port = calc_portfolio_summary(prices)
    if port["total_cost"] == 0:
        return ""

    pnl_cls = "gain" if port["total_pnl"] >= 0 else "loss"
    pnl_sign = "+" if port["total_pnl"] >= 0 else ""
    pnl_color = "var(--green)" if port["total_pnl"] >= 0 else "var(--red)"

    # Find best and worst
    best_ticker = worst_ticker = None
    best_pct = worst_pct = None
    for t, p in port["per_stock"].items():
        if best_pct is None or p["pnl_pct"] > best_pct:
            best_pct = p["pnl_pct"]
            best_ticker = t
        if worst_pct is None or p["pnl_pct"] < worst_pct:
            worst_pct = p["pnl_pct"]
            worst_ticker = t

    best_html = ""
    if best_ticker:
        bd = port["per_stock"][best_ticker]
        b_sign = "+" if bd["pnl_dollar"] >= 0 else ""
        best_html = f"""
    <div class="ps-item">
      <div class="ps-lbl">Best Performer</div>
      <div class="ps-val" style="color:var(--green)">{best_ticker}</div>
      <div class="ps-sub" style="color:var(--green)">{b_sign}${bd['pnl_dollar']:,.0f} ({b_sign}{bd['pnl_pct']:.1f}%)</div>
    </div>"""

    worst_html = ""
    if worst_ticker:
        wd = port["per_stock"][worst_ticker]
        w_sign = "+" if wd["pnl_dollar"] >= 0 else ""
        w_color = "var(--red)" if wd["pnl_dollar"] < 0 else "var(--green)"
        worst_html = f"""
    <div class="ps-item">
      <div class="ps-lbl">Worst Performer</div>
      <div class="ps-val" style="color:{w_color}">{worst_ticker}</div>
      <div class="ps-sub" style="color:{w_color}">{w_sign}${wd['pnl_dollar']:,.0f} ({w_sign}{wd['pnl_pct']:.1f}%)</div>
    </div>"""

    return f"""
<div class="portfolio-summary">
  <div class="ps-item">
    <div class="ps-lbl">Total Cost Basis</div>
    <div class="ps-val">${port['total_cost']:,.0f}</div>
    <div class="ps-sub">Across {len(port['per_stock'])} positions</div>
  </div>
  <div class="ps-item">
    <div class="ps-lbl">Market Value</div>
    <div class="ps-val">${port['total_mkt']:,.0f}</div>
    <div class="ps-sub">Live pricing</div>
  </div>
  <div class="ps-item">
    <div class="ps-lbl">Unrealized P&amp;L</div>
    <div class="ps-val" style="color:{pnl_color}">{pnl_sign}${port['total_pnl']:,.0f}</div>
    <div class="ps-sub" style="color:{pnl_color}">{pnl_sign}{port['total_pct']:.2f}%</div>
  </div>
  <div class="ps-item">
    <div class="ps-lbl">Return</div>
    <div class="ps-val" style="color:{pnl_color}">{pnl_sign}{port['total_pct']:.1f}%</div>
    <div class="ps-sub">vs cost basis</div>
  </div>
  {best_html}
  {worst_html}
</div>"""


def _build_history_table(prices: dict, date_str: str) -> str:
    port = calc_portfolio_summary(prices)
    rows = ""
    for ticker, pnl in port["per_stock"].items():
        pnl_cls = "gain" if pnl["pnl_dollar"] >= 0 else "loss"
        sign = "+" if pnl["pnl_dollar"] >= 0 else ""
        price = (prices.get(ticker) or {}).get("price", 0) or 0
        rows += f"""
        <tr>
          <td class="mono">{date_str}</td>
          <td class="mono">{ticker}</td>
          <td class="mono">${price:.2f}</td>
          <td class="mono">${pnl['avg_entry']:.2f}</td>
          <td class="mono">{pnl['total_shares']:,}</td>
          <td class="mono">${pnl['cost_basis']:,.0f}</td>
          <td class="mono">${pnl['market_value']:,.0f}</td>
          <td class="mono {pnl_cls}">{sign}${pnl['pnl_dollar']:,.0f}</td>
          <td class="mono {pnl_cls}">{sign}{pnl['pnl_pct']:.1f}%</td>
        </tr>"""

    if not rows:
        rows = '<tr><td colspan="9" class="placeholder">No position data available today.</td></tr>'

    return f"""
<div class="history-panel">
  <div class="panel-title">Portfolio P&amp;L History</div>
  <table class="hist-table">
    <thead>
      <tr>
        <th>Date</th><th>Ticker</th><th>Price</th><th>Avg Entry</th>
        <th>Shares</th><th>Cost</th><th>Mkt Val</th><th>P&amp;L $</th><th>P&amp;L %</th>
      </tr>
    </thead>
    <tbody>
      {rows}
      <tr>
        <td colspan="9" class="placeholder">&#9656; Historical rows will accumulate with each daily report run.</td>
      </tr>
    </tbody>
  </table>
</div>"""


def _build_position_footer(prices: dict) -> str:
    lines = []
    for ticker in POSITIONS:
        price = (prices.get(ticker) or {}).get("price")
        pnl = calc_pnl(ticker, price)
        if pnl:
            sign = "+" if pnl["pnl_dollar"] >= 0 else ""
            lines.append(f"{ticker}: {pnl['total_shares']:,}sh @ ${pnl['avg_entry']:.2f} avg &nbsp;&middot;&nbsp; {sign}${pnl['pnl_dollar']:,.0f} ({sign}{pnl['pnl_pct']:.1f}%)")
        else:
            lots = POSITIONS[ticker]
            total_shares = sum(l["shares"] for l in lots)
            avg = sum(l["shares"] * l["entry"] for l in lots) / total_shares
            lines.append(f"{ticker}: {total_shares:,}sh @ ${avg:.2f} avg &nbsp;&middot;&nbsp; price unavailable")
    return " &nbsp;|&nbsp; ".join(lines)


def build_email_html(prices: dict, commentary: dict) -> str:
    sgt_now  = datetime.now(ZoneInfo("Asia/Singapore"))
    date_str = sgt_now.strftime("%b %d, %Y")
    time_str = sgt_now.strftime("%H:%M SGT")

    cards = "".join(
        _build_card(s, prices.get(s["ticker"], {}), commentary.get(s["ticker"], {}), prices)
        for s in STOCKS
    )

    portfolio_bar = _build_portfolio_summary(prices)
    history_table = _build_history_table(prices, date_str)
    position_footer = _build_position_footer(prices)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Chip Decision Dashboard</title>
{_CSS}
</head>
<body>

<header class="hdr">
  <div>
    <h1>AI Chip &middot; Decision Dashboard</h1>
    <p>NVDA &middot; AMD &middot; AVGO &middot; MU &middot; SWKS &middot; RGTI &middot; ON &middot; CRDO &nbsp;|&nbsp; Updated: {date_str} &nbsp;|&nbsp; {time_str}</p>
  </div>
  <div class="mkt-bar">
    <div class="mkt-item">
      <div class="lbl">NASDAQ</div>
      <div class="val mono">&mdash;</div>
      <div class="neg mono">live</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">VIX</div>
      <div class="val mono">&mdash;</div>
      <div class="neg mono">&mdash;</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">10Y UST</div>
      <div class="val mono">&mdash;</div>
      <div class="neg mono">&mdash;</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">GOLD</div>
      <div class="val mono">&mdash;</div>
      <div class="pos mono">&mdash;</div>
    </div>
  </div>
</header>

<!-- Alert Banner -->
<div class="alert-banner">
  <div class="alert-title">&#9650; Market Update</div>
  Semi sector under pressure from China export controls. AI capex still strong at $571B forecast for 2026.
  Watch NVDA May 27 earnings and AMD May 5 earnings as near-term catalysts. ON and SWKS seeking cycle bottom.
  RGTI speculative; CRDO benefiting from AEC hyperscaler adoption.
</div>

<!-- Portfolio Summary -->
{portfolio_bar}

<!-- Stock Cards -->
<div class="stocks-grid">
{cards}
</div>

<!-- P&L History -->
{history_table}

<!-- Bottom panels -->
<div class="bottom-grid">

  <!-- Hold / Add / Cut Framework -->
  <div class="panel">
    <div class="panel-title">&#9889; Hold / Add / Cut Framework</div>
    <div class="factor-row">
      <div class="ficon green">&#10003;</div>
      <div class="fcontent">
        <div class="fname">HOLD — Price above avg entry &amp; key support</div>
        <div class="fdesc">If price holds above your avg entry and S1, maintain position. Let thesis play out through earnings catalyst.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon yellow">&#9889;</div>
      <div class="fcontent">
        <div class="fname">ADD — Price tests strong support with volume</div>
        <div class="fdesc">Add at confirmed S1/S2 with volume spike. Candle close above level required. Scale in — do not catch falling knife.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon red">&#10005;</div>
      <div class="fcontent">
        <div class="fname">CUT — Support broken or stop triggered</div>
        <div class="fdesc">Exit if price closes below stop estimate (-8% from avg entry). Preserve capital. Re-enter on confirmed reversal.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon red">&#10005;</div>
      <div class="fcontent">
        <div class="fname">VIX &gt; 28 = Risk-Off</div>
        <div class="fdesc">Elevated VIX signals fear. Reduce position sizing or hold cash. Re-deploy when VIX cools below 20.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon yellow">&#9889;</div>
      <div class="fcontent">
        <div class="fname">Geopolitical / Export Risk</div>
        <div class="fdesc">China export controls headwind for NVDA &amp; MU. ON and AVGO have EV/SiC and AI tailwinds partially offsetting.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon green">&#10003;</div>
      <div class="fcontent">
        <div class="fname">Earnings Beat + Guidance Raise</div>
        <div class="fdesc">Strong buy signal. Watch May 5 (AMD), May 27 (NVDA), Jun 4 (AVGO) for guidance raises and GPU ramp updates.</div>
      </div>
    </div>
  </div>

  <!-- Macro + Catalyst Timeline -->
  <div style="display:flex;flex-direction:column;gap:12px;">

    <div class="panel">
      <div class="panel-title">&#127758; Macro Environment</div>
      <div class="macro-item"><span class="macro-lbl">VIX (Fear Index)</span><span class="macro-val danger">ELEVATED &mdash; monitor</span></div>
      <div class="macro-item"><span class="macro-lbl">Nasdaq Trend</span><span class="macro-val caution">Volatile &mdash; correction risk</span></div>
      <div class="macro-item"><span class="macro-lbl">10Y Treasury</span><span class="macro-val caution">~4.4% &mdash; Holding</span></div>
      <div class="macro-item"><span class="macro-lbl">Gold</span><span class="macro-val danger">Risk-off signal elevated</span></div>
      <div class="macro-item"><span class="macro-lbl">China Export Controls</span><span class="macro-val caution">Ongoing &mdash; NVDA &amp; MU exposed</span></div>
      <div class="macro-item"><span class="macro-lbl">AI Capex Trend</span><span class="macro-val ok">$571B forecast 2026 &#10003;</span></div>
      <div class="macro-item"><span class="macro-lbl">EV / SiC Recovery</span><span class="macro-val caution">H2 2026 expected &mdash; ON watch</span></div>
      <div class="macro-item"><span class="macro-lbl">HBM Demand</span><span class="macro-val ok">Surging &mdash; MU beneficiary &#10003;</span></div>
    </div>

    <div class="panel">
      <div class="panel-title">&#128197; Catalyst Calendar</div>
      <div class="timeline">
        <div class="tl-item upcoming">
          <div class="t-date">MAY 5, 2026</div>
          <div class="t-event">AMD Q1 2026 Earnings</div>
          <div class="t-detail">EPS est. $1.27 | Rev est. $9.84B. Watch GPU ramp guidance.</div>
        </div>
        <div class="tl-item upcoming">
          <div class="t-date">MAY 27, 2026</div>
          <div class="t-event">NVDA Q1 2026 Earnings</div>
          <div class="t-detail">Rev guided $65B (+65% YoY). Rubin roadmap update.</div>
        </div>
        <div class="tl-item upcoming">
          <div class="t-date">JUN 4, 2026</div>
          <div class="t-event">AVGO Q2 2026 Earnings</div>
          <div class="t-detail">AI rev guided +140% YoY. Q2 total rev est. $22.02B.</div>
        </div>
        <div class="tl-item upcoming">
          <div class="t-date">~JUN 2026</div>
          <div class="t-event">MU Q3 2026 Earnings</div>
          <div class="t-detail">HBM4 ramp update. NAND/DRAM pricing inflection watch.</div>
        </div>
        <div class="tl-item upcoming">
          <div class="t-date">~Q2 2026</div>
          <div class="t-event">SWKS Q2 2026 Earnings</div>
          <div class="t-detail">5G handset recovery pace. Apple supply chain update.</div>
        </div>
        <div class="tl-item">
          <div class="t-date">H2 2026</div>
          <div class="t-event">ON EV/SiC Recovery</div>
          <div class="t-detail">Industrial cycle bottom. AI datacenter power mgmt ramp.</div>
        </div>
        <div class="tl-item">
          <div class="t-date">LATE 2026</div>
          <div class="t-event">NVDA Rubin GPU Launch</div>
          <div class="t-detail">Next-gen architecture. Key for sustaining NVDA premium.</div>
        </div>
        <div class="tl-item">
          <div class="t-date">FY2027</div>
          <div class="t-event">AVGO Custom AI Chip Target</div>
          <div class="t-detail">Mgmt targeting $100B custom AI chip revenue.</div>
        </div>
      </div>
    </div>

  </div>
</div>

<footer>
  <div style="margin-bottom:6px;color:var(--muted);font-size:9px;">POSITIONS: {position_footer}</div>
  DATA AS OF {date_str.upper()} &nbsp;&middot;&nbsp; {time_str}
  &nbsp;&middot;&nbsp; PRICES: NASDAQ API &nbsp;&middot;&nbsp; COMMENTARY: STOCKANALYSIS &middot; BARCHART
  &nbsp;&middot;&nbsp; FOR INFORMATIONAL PURPOSES ONLY &nbsp;&middot;&nbsp; NOT FINANCIAL ADVICE
</footer>

</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — EMAIL SENDER
# ══════════════════════════════════════════════════════════════════════════════

def send_email(html_body: str):
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.error("Gmail credentials not configured. Fill in .env")
        return

    sgt_date = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%d %b %Y")
    subject  = f"AI Chip Dashboard \u2014 NVDA | AMD | AVGO | MU | SWKS | RGTI | ON | CRDO  [{sgt_date}]"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_SENDER
    msg["To"]      = RECIPIENT_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.ehlo()
            server.starttls()
            server.login(GMAIL_SENDER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_SENDER, RECIPIENT_EMAIL, msg.as_string())
        log.info(f"Email sent to {RECIPIENT_EMAIL}")
    except smtplib.SMTPAuthenticationError:
        log.error("Gmail auth failed. Use App Password (not your Gmail password).")
    except Exception as e:
        log.error(f"Email failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — MAIN JOB + SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

def run_report():
    log.info("=" * 60)
    log.info("Running AI Chip Dashboard report job...")

    log.info("Step 1/3 — Fetching live prices (NASDAQ API)...")
    prices = fetch_prices()

    log.info("Step 2/3 — Fetching live commentary (StockAnalysis + Barchart)...")
    commentary = fetch_commentary(prices)

    log.info("Step 3/3 — Building Dashboard email & sending...")
    html_body = build_email_html(prices, commentary)
    send_email(html_body)

    log.info("Job complete.")
    log.info("=" * 60)


def main():
    log.info("AI Chip Dashboard Scheduler starting...")

    # ── Uncomment to test immediately ──────────────────────────────────────
    # run_report()

    scheduler = BlockingScheduler(timezone="Asia/Singapore")
    scheduler.add_job(
        run_report,
        trigger=CronTrigger(hour=6, minute=0, timezone="Asia/Singapore"),
        id="daily_chip_dashboard",
        name="AI Chip Dashboard Email",
        misfire_grace_time=300,
        replace_existing=True,
    )

    log.info(f"Scheduled: every day 06:00 SGT  ->  {RECIPIENT_EMAIL}")
    log.info("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
