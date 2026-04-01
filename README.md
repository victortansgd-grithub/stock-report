# 📈 Daily Stock Report

Automatically fetches live prices for **NVDA, AMD, AVGO, MU** and emails a formatted HTML report to `victortansgd@gmail.com` every day at **06:00 SGT**.

---

## Prerequisites

- Python 3.9+
- A Gmail account with **2-Step Verification** enabled

---

## Setup

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Gmail credentials

```bash
cp .env.example .env
```

Then edit `.env` with your actual values:

```
GMAIL_SENDER=yourgmail@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
RECIPIENT_EMAIL=victortansgd@gmail.com
```

#### How to get a Gmail App Password

1. Go to [Google Account → Security](https://myaccount.google.com/security)
2. Enable **2-Step Verification** if not already done
3. Go to [App Passwords](https://myaccount.google.com/apppasswords)
4. Select **"Mail"** as the app, any device name
5. Copy the generated 16-character password into `GMAIL_APP_PASSWORD`

> ⚠️ Never commit `.env` to git. It is already listed in `.gitignore`.

---

## Usage

### Run the scheduler (keeps running in background)

```bash
python stock_report.py
```

The scheduler will fire every day at **06:00 SGT**. Keep the process alive (e.g., in a `tmux` session, or set up a `systemd` service).

### Send a test email immediately

Edit `stock_report.py` and uncomment this line inside `main()`:

```python
# run_report()
```

Then run:

```bash
python stock_report.py
```

---

## Email Format Preview

| Field | Content |
|---|---|
| **Subject** | 📈 Daily Stock Report – NVDA \| AMD \| AVGO \| MU [Date] |
| **Stocks** | NVDA, AMD, AVGO, MU |
| **Data** | Latest close price, daily change %, support levels, commentary |
| **Source** | Yahoo Finance (free, no API key needed) |
| **Schedule** | 06:00 SGT daily |

---

## Run as a Background Service (Optional)

### Using `nohup`

```bash
nohup python stock_report.py > stock_report.log 2>&1 &
echo $! > stock_report.pid
```

Stop with:
```bash
kill $(cat stock_report.pid)
```

### Using `systemd` (Linux server)

Create `/etc/systemd/system/stock-report.service`:

```ini
[Unit]
Description=Daily Stock Report Emailer
After=network.target

[Service]
ExecStart=/usr/bin/python3 /workspace/stock-report/stock_report.py
WorkingDirectory=/workspace/stock-report
Restart=always
User=root

[Install]
WantedBy=multi-user.target
```

Then:
```bash
systemctl daemon-reload
systemctl enable stock-report
systemctl start stock-report
```

---

## File Structure

```
stock-report/
├── stock_report.py     # Main script
├── .env                # Your credentials (create from .env.example)
├── .env.example        # Credential template
├── requirements.txt    # Python dependencies
└── README.md           # This file
```
