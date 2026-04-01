#!/usr/bin/env python3
"""
Daily Stock Report Emailer  —  AI Chip Dashboard Edition
Sends NVDA · AMD · AVGO · MU report to victortansgd@gmail.com
Scheduled at 06:00 SGT (Asia/Singapore) every day

Price data  : NASDAQ Official API  (no API key needed)
Commentary  : Live-scraped from StockAnalysis.com + Barchart.com
Design      : Dark-mode Dashboard  (chip-dashboard.html template)
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

# ─── Stock configuration ──────────────────────────────────────────────────────
STOCKS = [
    {
        "ticker":    "NVDA",
        "name":      "NVIDIA Corporation",
        "css_class": "nvda",
        "color":     "#76b900",
        "support":   [
            ("S1 — Range floor",   "$160", "watch",  "TESTING"),
            ("S2 — Major support", "$150", "watch",  "WATCH"),
        ],
        "resistance": [
            ("R1 — MA resistance", "$174–$183", "", ""),
        ],
        "fwd_pe":    "35.9x",
        "rev_growth": "+65% YoY",
        "mkt_cap":   "$4.1T",
        "catalyst":  "Earnings May 27, 2026. Rubin chip launch late 2026. $500B backlog; $300B recognized in 2026.",
    },
    {
        "ticker":    "AMD",
        "name":      "Advanced Micro Devices",
        "css_class": "amd",
        "color":     "#ed1c24",
        "support":   [
            ("S1 — 200-day MA",  "$192–$193", "holding", "KEY"),
            ("S2 — Pivot",       "$176",      "watch",   "WATCH"),
            ("S3 — 2026 Low",    "$149",      "",        ""),
        ],
        "resistance": [
            ("R1 — Prior support", "$215–$225", "", ""),
        ],
        "fwd_pe":    "40x",
        "rev_growth": "+32% YoY",
        "mkt_cap":   "$329B",
        "catalyst":  "Earnings May 5, 2026. Meta GPU supply deal (6GW Instinct). CPU data center ramp H2 2026. EPS beat last Q: $1.53 vs $1.32 est.",
    },
    {
        "ticker":    "AVGO",
        "name":      "Broadcom Inc.",
        "css_class": "avgo",
        "color":     "#cc0000",
        "support":   [
            ("S1 — $300 level",  "$300",      "broken", "BROKEN"),
            ("S2 — Next target", "$250",      "watch",  "IN FOCUS"),
            ("S3 — 200-day MA",  "$240–$250", "",       ""),
        ],
        "resistance": [
            ("R1 — Rejection zone", "$316–$350", "broken", "FAILED"),
        ],
        "fwd_pe":    "58.6x",
        "rev_growth": "+106% YoY",
        "mkt_cap":   "$1.38T",
        "catalyst":  "Earnings Jun 4, 2026. AI rev guided +140% YoY. Rosenblatt PT $500. Death cross forming — watch closely.",
    },
    {
        "ticker":    "MU",
        "name":      "Micron Technology",
        "css_class": "mu",
        "color":     "#0071c5",
        "support":   [
            ("S1 — Range floor",   "$80", "watch",  "WATCH"),
            ("S2 — Major support", "$70", "watch",  "LEVEL"),
        ],
        "resistance": [
            ("R1 — Near-term",  "$110–$115", "", ""),
        ],
        "fwd_pe":    "~10x",
        "rev_growth": "+38% YoY",
        "mkt_cap":   "$~120B",
        "catalyst":  "Earnings ~Jun 2026. HBM4 ramp for AI servers. Memory cycle inflection; NAND pricing improving.",
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
            arrow = "▲" if info["change"] >= 0 else "▼"
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
        n_str = f" · {sa['analysts']} analysts" if sa.get("analysts") else ""
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
            target_line += f'  |  Range ${sa["low"]}–${sa["high"]}'

    if bc:
        pct = int(re.search(r"\d+", bc).group())
        sig = bc.split()[-1]
        if sig == "Buy":
            tech_line = f"Barchart: {bc} — bullish technicals."
        elif sig == "Sell":
            tech_line = f"Barchart: {bc} — bearish technicals."
        else:
            tech_line = f"Barchart: {bc} — mixed signals."

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
#  SECTION 3 — EMAIL HTML  (Dashboard design)
# ══════════════════════════════════════════════════════════════════════════════

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=DM+Sans:wght@300;400;500;600&display=swap');
:root{
  --bg:#f0f2f5;--surface:#ffffff;--border:#e2e8f0;--border-bright:#cbd5e1;
  --text:#1e293b;--muted:#64748b;--dim:#94a3b8;
  --green:#16a34a;--green-dim:#dcfce7;
  --red:#dc2626;--red-dim:#fee2e2;
  --yellow:#ca8a04;--yellow-dim:#fef9c3;
  --blue:#0284c7;--blue-dim:#e0f2fe;
  --nvda:#76b900;--amd:#ed1c24;--avgo:#cc0000;--mu:#0071c5;
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

/* ── Stock Grid ── */
.stocks-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;
      padding:16px;position:relative;overflow:hidden;
      box-shadow:0 1px 4px rgba(0,0,0,.06);}
.card::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;}
.nvda::before{background:var(--nvda);}
.amd::before{background:var(--amd);}
.avgo::before{background:var(--avgo);}
.mu::before{background:var(--mu);}

.card-hdr{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:12px;}
.ticker{font-family:'Space Mono',monospace;font-size:18px;font-weight:700;}
.nvda .ticker{color:var(--nvda);}
.amd  .ticker{color:var(--amd);}
.avgo .ticker{color:var(--avgo);}
.mu   .ticker{color:var(--mu);}
.cname{font-size:10px;color:var(--muted);margin-top:2px;}

.badge{padding:2px 9px;border-radius:20px;font-size:9px;font-family:'Space Mono',monospace;
       font-weight:700;letter-spacing:.08em;}
.badge.watch{background:var(--yellow-dim);color:var(--yellow);border:1px solid #ca8a0444;}
.badge.buy{background:var(--green-dim);color:var(--green);border:1px solid #16a34a44;}
.badge.caution{background:var(--red-dim);color:var(--red);border:1px solid #dc262644;}
.badge.strong-buy{background:var(--green-dim);color:var(--green);border:1px solid #16a34a44;}

.price-row{display:flex;align-items:baseline;gap:8px;margin-bottom:12px;flex-wrap:wrap;}
.price-now{font-family:'Space Mono',monospace;font-size:22px;font-weight:700;color:var(--text);}
.pchg{font-family:'Space Mono',monospace;font-size:11px;}
.pchg.neg{color:var(--red);}
.pchg.pos{color:var(--green);}

/* ── Range bar ── */
.range-sec{margin-bottom:12px;}
.range-lbl{font-size:9px;color:var(--muted);margin-bottom:5px;font-family:'Space Mono',monospace;letter-spacing:.1em;}
.range-bar{height:5px;background:var(--border);border-radius:3px;position:relative;margin-bottom:3px;}
.range-fill{position:absolute;left:0;top:0;bottom:0;border-radius:3px;
            background:linear-gradient(90deg,var(--red),var(--yellow),var(--green));}
.range-marker{position:absolute;top:-4px;width:11px;height:11px;border-radius:50%;
              background:white;border:2px solid var(--border-bright);transform:translateX(-50%);
              box-shadow:0 1px 4px rgba(0,0,0,.2);}
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
.commentary{background:var(--blue-dim);border:1px solid #bae6fd;border-radius:6px;
            padding:8px 11px;font-size:10px;margin-bottom:8px;}
.comm-label{font-size:8px;color:var(--blue);letter-spacing:.1em;text-transform:uppercase;
            margin-bottom:4px;font-family:'Space Mono',monospace;}
.comm-line{color:var(--text);line-height:1.5;margin-bottom:3px;}
.comm-line:last-child{margin-bottom:0;}
.comm-line.tech{color:var(--muted);}

/* ── Catalyst ── */
.catalyst{background:var(--green-dim);border:1px solid #bbf7d0;border-radius:6px;padding:7px 11px;font-size:10px;}
.cat-lbl{font-size:8px;color:var(--green);letter-spacing:.1em;text-transform:uppercase;
         margin-bottom:3px;font-family:'Space Mono',monospace;}
.cat-text{color:#374151;line-height:1.45;}

/* ── Bottom panels ── */
.bottom-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:18px;}
.panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;
       box-shadow:0 1px 4px rgba(0,0,0,.06);}
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


def _signal_badge(rating: str) -> str:
    r = (rating or "").lower()
    if "strong buy" in r:
        return '<span class="badge strong-buy">STRONG BUY</span>'
    elif "buy" in r:
        return '<span class="badge buy">BUY</span>'
    elif "caution" in r or "sell" in r:
        return '<span class="badge caution">CAUTION</span>'
    else:
        return '<span class="badge watch">WATCH</span>'


def _range_marker_pct(price: float, low: float, high: float) -> int:
    if high == low:
        return 50
    return int(min(max((price - low) / (high - low) * 100, 2), 98))


def _build_card(stock: dict, info: dict, comm: dict) -> str:
    ticker    = stock["ticker"]
    css       = stock["css_class"]
    price     = info.get("price")
    change    = info.get("change", 0)
    chg_pct   = info.get("change_pct", 0)
    wk52_low  = info.get("wk52_low")
    wk52_high = info.get("wk52_high")

    # Price display
    price_str = f"${price:.2f}" if price else "N/A"
    chg_cls   = "pos" if change >= 0 else "neg"
    chg_arrow = "▲" if change >= 0 else "▼"
    chg_str   = f"{chg_arrow} {abs(change):.2f} ({chg_pct:+.2f}%)"

    # From 52W high
    from_high_str = ""
    if price and wk52_high:
        fh = (price - wk52_high) / wk52_high * 100
        from_high_str = f"  {fh:.1f}% from 52W high"

    # Range bar
    range_html = ""
    if price and wk52_low and wk52_high:
        pct = _range_marker_pct(price, wk52_low, wk52_high)
        range_html = f"""
        <div class="range-sec">
          <div class="range-lbl">52-WEEK RANGE</div>
          <div class="range-bar">
            <div class="range-fill" style="width:100%"></div>
            <div class="range-marker" style="left:{pct}%"></div>
          </div>
          <div class="range-ends">
            <span>${wk52_low:.2f}</span>
            <span>{price_str}</span>
            <span>${wk52_high:.2f}</span>
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

    # Fund grid
    rev_color = "var(--green)" if "+" in stock["rev_growth"] else "var(--red)"
    rating_color = "var(--green)" if comm.get("rating") and "buy" in comm["rating"].lower() else "var(--yellow)"
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
        lines.append(f'<div class="comm-line">📊 {comm["analyst_line"]}</div>')
    if comm.get("target_line"):
        lines.append(f'<div class="comm-line">🎯 {comm["target_line"]}</div>')
    if comm.get("tech_line"):
        lines.append(f'<div class="comm-line tech">⚙️ {comm["tech_line"]}</div>')
    if lines:
        comm_html = f"""
    <div class="commentary">
      <div class="comm-label">💬 Analyst Commentary</div>
      {"".join(lines)}
    </div>"""

    # Signal badge
    badge = _signal_badge(comm.get("rating", ""))

    return f"""
  <div class="card {css}">
    <div class="card-hdr">
      <div>
        <div class="ticker">{ticker}</div>
        <div class="cname">{stock['name']}</div>
      </div>
      {badge}
    </div>
    <div class="price-row">
      <div class="price-now mono">{price_str}</div>
      <div class="pchg {chg_cls} mono">{chg_str}{from_high_str}</div>
    </div>
    {range_html}
    <div class="levels">
      <div class="lvl-title">Price Levels</div>
      {lvl_rows}
    </div>
    {fund_html}
    {comm_html}
    <div class="catalyst">
      <div class="cat-lbl">📅 Next Catalyst</div>
      <div class="cat-text">{stock['catalyst']}</div>
    </div>
  </div>"""


def build_email_html(prices: dict, commentary: dict) -> str:
    sgt_now  = datetime.now(ZoneInfo("Asia/Singapore"))
    date_str = sgt_now.strftime("%b %d, %Y")
    time_str = sgt_now.strftime("%H:%M SGT")

    cards = "".join(
        _build_card(s, prices.get(s["ticker"], {}), commentary.get(s["ticker"], {}))
        for s in STOCKS
    )

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
  <div class="header-left">
    <h1>AI Chip · Decision Dashboard</h1>
    <p>NVDA · AMD · AVGO · MU &nbsp;|&nbsp; Updated: {date_str} &nbsp;|&nbsp; {time_str}</p>
  </div>
  <div class="mkt-bar">
    <div class="mkt-item">
      <div class="lbl">NASDAQ</div>
      <div class="val mono" id="nasdaq-val">—</div>
      <div class="neg mono" id="nasdaq-chg">live</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">VIX</div>
      <div class="val mono">—</div>
      <div class="neg mono">—</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">10Y UST</div>
      <div class="val mono">—</div>
      <div class="neg mono">—</div>
    </div>
    <div class="mkt-item">
      <div class="lbl">GOLD</div>
      <div class="val mono">—</div>
      <div class="pos mono">—</div>
    </div>
  </div>
</header>

<!-- Stock Cards -->
<div class="stocks-grid">
{cards}
</div>

<!-- Bottom panels -->
<div class="bottom-grid">

  <!-- Decision Framework -->
  <div class="panel">
    <div class="panel-title">⚡ Buy / Sell Decision Framework</div>
    <div class="factor-row">
      <div class="ficon green">✓</div>
      <div class="fcontent">
        <div class="fname">Price vs. Support</div>
        <div class="fdesc">Buy near confirmed S1/S2 with volume confirmation. Wait for candle close above level — avoid catching falling knife.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon yellow">⚡</div>
      <div class="fcontent">
        <div class="fname">Moving Average Position</div>
        <div class="fdesc">Price below 50-day &amp; 200-day MA = bearish. Wait for reclaim before adding. AVGO death cross = extra caution.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon green">✓</div>
      <div class="fcontent">
        <div class="fname">Earnings Beat + Guidance Raise</div>
        <div class="fdesc">Strong buy signal. AMD beat Q4 by $0.21; AVGO beat by $0.03. Watch May 5 (AMD) and May 27 (NVDA) closely.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon red">✕</div>
      <div class="fcontent">
        <div class="fname">VIX &gt; 28 = Risk-Off</div>
        <div class="fdesc">Elevated VIX signals fear. Reduce position sizing or hold cash until VIX cools below 20.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon yellow">⚡</div>
      <div class="fcontent">
        <div class="fname">Geopolitical / Export Risk</div>
        <div class="fdesc">China export controls = headwind for NVDA. MU also exposed to NAND/DRAM pricing volatility. Monitor for resolution.</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon green">✓</div>
      <div class="fcontent">
        <div class="fname">Analyst Consensus</div>
        <div class="fdesc">All four rated Strong Buy / Buy. NVDA avg target $266 (+56%). AVGO avg $431 (+42%). MU avg $443 (+36%). AMD avg $261 (+30%).</div>
      </div>
    </div>
    <div class="factor-row">
      <div class="ficon red">✕</div>
      <div class="fcontent">
        <div class="fname">Margin Buffer (Leveraged)</div>
        <div class="fdesc">With leveraged positions, monitor margin buffer daily. Support breaks = cut before forced liquidation.</div>
      </div>
    </div>
  </div>

  <!-- Macro + Timeline -->
  <div style="display:flex;flex-direction:column;gap:12px;">

    <div class="panel">
      <div class="panel-title">🌐 Macro Environment</div>
      <div class="macro-item"><span class="macro-lbl">VIX (Fear Index)</span><span class="macro-val danger">ELEVATED — monitor</span></div>
      <div class="macro-item"><span class="macro-lbl">Nasdaq Trend</span><span class="macro-val caution">Volatile — correction risk</span></div>
      <div class="macro-item"><span class="macro-lbl">10Y Treasury</span><span class="macro-val caution">~4.4% — Holding</span></div>
      <div class="macro-item"><span class="macro-lbl">Gold</span><span class="macro-val danger">Risk-off signal elevated</span></div>
      <div class="macro-item"><span class="macro-lbl">China Export Controls</span><span class="macro-val caution">Ongoing — NVDA &amp; MU exposed</span></div>
      <div class="macro-item"><span class="macro-lbl">AI Capex Trend</span><span class="macro-val ok">$571B forecast 2026 ✓</span></div>
      <div class="macro-item"><span class="macro-lbl">HBM Demand</span><span class="macro-val ok">Surging — MU beneficiary ✓</span></div>
    </div>

    <div class="panel">
      <div class="panel-title">📅 Catalyst Timeline</div>
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
          <div class="t-date">~JUN 2026</div>
          <div class="t-event">MU Q3 2026 Earnings</div>
          <div class="t-detail">HBM4 ramp update. NAND/DRAM pricing inflection watch.</div>
        </div>
        <div class="tl-item upcoming">
          <div class="t-date">JUN 4, 2026</div>
          <div class="t-event">AVGO Q2 2026 Earnings</div>
          <div class="t-detail">AI rev guided +140% YoY. Q2 total rev est. $22.02B.</div>
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
  DATA AS OF {date_str.upper()} &nbsp;·&nbsp; {time_str}
  &nbsp;·&nbsp; PRICES: NASDAQ API &nbsp;·&nbsp; COMMENTARY: STOCKANALYSIS · BARCHART
  &nbsp;·&nbsp; FOR INFORMATIONAL PURPOSES ONLY &nbsp;·&nbsp; NOT FINANCIAL ADVICE
</footer>

</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 4 — EMAIL SENDER
# ══════════════════════════════════════════════════════════════════════════════

def send_email(html_body: str):
    if not GMAIL_SENDER or not GMAIL_APP_PASSWORD:
        log.error("❌ Gmail credentials not configured. Fill in .env")
        return

    sgt_date = datetime.now(ZoneInfo("Asia/Singapore")).strftime("%d %b %Y")
    subject  = f"📈 AI Chip Dashboard — NVDA | AMD | AVGO | MU  [{sgt_date}]"

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
        log.info(f"✅ Email sent to {RECIPIENT_EMAIL}")
    except smtplib.SMTPAuthenticationError:
        log.error("❌ Gmail auth failed. Use App Password (not your Gmail password).")
    except Exception as e:
        log.error(f"❌ Email failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
#  SECTION 5 — MAIN JOB + SCHEDULER
# ══════════════════════════════════════════════════════════════════════════════

def run_report():
    log.info("=" * 60)
    log.info("🚀 Running AI Chip Dashboard report job...")

    log.info("📊 Step 1/3 — Fetching live prices (NASDAQ API)...")
    prices = fetch_prices()

    log.info("💬 Step 2/3 — Fetching live commentary (StockAnalysis + Barchart)...")
    commentary = fetch_commentary(prices)

    log.info("📧 Step 3/3 — Building Dashboard email & sending...")
    html_body = build_email_html(prices, commentary)
    send_email(html_body)

    log.info("✅ Job complete.")
    log.info("=" * 60)


def main():
    log.info("📅 AI Chip Dashboard Scheduler starting...")

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

    log.info(f"⏰ Scheduled: every day 06:00 SGT  →  {RECIPIENT_EMAIL}")
    log.info("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
