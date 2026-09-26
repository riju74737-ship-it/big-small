# BIG SMALL VIP — Virtual Coin Practice App

A small Flask web app with a virtual-coin Big/Small game and an admin dashboard. This is a practice/demo project only: coins have no cash value; no real-money betting, deposits, or payouts are implemented.

## Features
- 0–9 outcomes; 0–4 SMALL and 5–9 BIG
- Virtual coin balance, game history, transactions
- Demo deposit/withdrawal request queue for admin review
- Admin dashboard with 30 listed controls/features, user blocking, virtual balance adjustments, basic settings, pause/maintenance toggles, and announcements
- SQLite database auto-created on first start

## Setup
Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

Set environment variables before launching:
- `APP_SECRET`: long random secret
- `ADMIN_ID`: Telegram ID (default 8418148020; currently used as the admin seed identifier)
- `ADMIN_LOGIN_KEY`: choose a private admin login key (the default is insecure and must be changed)
- `PORT`: optional, defaults to 5000

Run:
```bash
python app.py
```
Open `http://127.0.0.1:5000`.

## Important security notes
- This starter uses a simple admin-key login and development player login. Do not expose it publicly as-is.
- Replace the development login with verified Telegram Mini App `initData` validation before deployment.
- Use HTTPS, a strong `APP_SECRET`, a private `ADMIN_LOGIN_KEY`, rate limiting, and production WSGI hosting.
- Real-money betting/payment/payouts are intentionally not included. Review applicable laws and payment-provider rules before considering any real-money product.
