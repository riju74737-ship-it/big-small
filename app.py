import os, sqlite3, secrets, time, json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, session, redirect

APP_SECRET = os.getenv("APP_SECRET", "change-this-secret-before-deploying")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8418148020"))
DB_PATH = os.getenv("DB_PATH", "big_small_vip.db")
app = Flask(__name__)
app.secret_key = APP_SECRET

ADMIN_FEATURES = [
    "Dashboard & live statistics", "User directory", "User profile/details",
    "Search users", "Block/unblock users", "Adjust virtual wallet balance",
    "Wallet transaction history", "Game round settings", "Pause/resume game",
    "Round history", "Manual result override (practice mode)", "Bet history",
    "Virtual deposit request inbox", "Approve/reject demo deposit requests",
    "Virtual withdrawal request inbox", "Approve/reject demo withdrawal requests",
    "Pending withdrawal list", "Approved withdrawal history", "Rejected withdrawal history",
    "Referral settings", "Referral statistics", "Leaderboard controls",
    "Broadcast announcement", "Notification settings", "Support inbox",
    "Add administrator", "Remove administrator", "Admin activity log",
    "Export database backup", "Maintenance mode"
]

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, telegram_id TEXT UNIQUE,
          balance INTEGER NOT NULL DEFAULT 1000, blocked INTEGER NOT NULL DEFAULT 0,
          referral_code TEXT UNIQUE, referred_by TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS rounds(
          id INTEGER PRIMARY KEY AUTOINCREMENT, result INTEGER NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS bets(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, round_id INTEGER NOT NULL,
          choice TEXT NOT NULL, amount INTEGER NOT NULL, result TEXT NOT NULL DEFAULT 'pending',
          created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS transactions(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
          amount INTEGER NOT NULL, status TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS requests(
          id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, kind TEXT NOT NULL,
          amount INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admins(telegram_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS admin_logs(id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT, created_at TEXT);
        """)
        c.execute("INSERT OR IGNORE INTO admins(telegram_id) VALUES(?)", (str(ADMIN_ID),))
        defaults = {"round_seconds":"30", "min_bet":"10", "max_bet":"1000", "paused":"0",
                    "maintenance":"0", "referral_reward":"50", "announcement":""}
        for k,v in defaults.items():
            c.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))

def setting(key):
    with db() as c:
        r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return r["value"] if r else ""

def is_admin():
    return bool(session.get("uid")) and session.get("uid") == "admin"

def get_user():
    uid = session.get("uid")
    if not uid or uid == "admin": return None
    with db() as c: return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

def ensure_user(name="Guest", telegram_id=None):
    with db() as c:
        if telegram_id:
            row = c.execute("SELECT * FROM users WHERE telegram_id=?", (str(telegram_id),)).fetchone()
            if row: return row["id"]
        code = secrets.token_hex(4).upper()
        cur = c.execute("INSERT INTO users(name,telegram_id,balance,referral_code,created_at) VALUES(?,?,?,?,?)",
                        (name[:80], str(telegram_id) if telegram_id else None, 1000, code, datetime.now().isoformat(timespec="seconds")))
        return cur.lastrowid

@app.get("/")
def home():
    return render_template_string(PAGE)

@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    # Development login. For public deployment, replace with verified Telegram WebApp initData validation.
    if str(data.get("admin_key","")) == os.getenv("ADMIN_LOGIN_KEY", "change-admin-key"):
        session["uid"] = "admin"
        return jsonify(ok=True, admin=True)
    name = str(data.get("name") or "Guest")[:80]
    tid = str(data.get("telegram_id") or "")[:64] or None
    uid = ensure_user(name, tid)
    with db() as c:
        row = c.execute("SELECT blocked FROM users WHERE id=?", (uid,)).fetchone()
        if row["blocked"]: return jsonify(ok=False, error="Account blocked"), 403
    session["uid"] = uid
    return jsonify(ok=True, admin=False)

@app.get("/api/state")
def state():
    if is_admin():
        with db() as c:
            return jsonify(admin=True, features=ADMIN_FEATURES,
                stats={"users":c.execute("SELECT COUNT(*) FROM users").fetchone()[0],
                       "bets":c.execute("SELECT COUNT(*) FROM bets").fetchone()[0],
                       "pending_requests":c.execute("SELECT COUNT(*) FROM requests WHERE status='pending'").fetchone()[0]},
                settings={k:setting(k) for k in ["round_seconds","min_bet","max_bet","paused","maintenance","referral_reward"]},
                users=[dict(r) for r in c.execute("SELECT id,name,telegram_id,balance,blocked,created_at FROM users ORDER BY id DESC LIMIT 100")],
                requests=[dict(r) for r in c.execute("SELECT requests.*,users.name FROM requests JOIN users ON users.id=requests.user_id ORDER BY requests.id DESC LIMIT 100")])
    u = get_user()
    if not u: return jsonify(ok=False, error="Please login"), 401
    with db() as c:
        bets = [dict(r) for r in c.execute("SELECT * FROM bets WHERE user_id=? ORDER BY id DESC LIMIT 20",(u["id"],))]
        tx = [dict(r) for r in c.execute("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 20",(u["id"],))]
        history = [dict(r) for r in c.execute("SELECT * FROM rounds ORDER BY id DESC LIMIT 10")]
    return jsonify(admin=False,user=dict(u),bets=bets,transactions=tx,history=history,
                   settings={"min_bet":setting("min_bet"),"max_bet":setting("max_bet"),"paused":setting("paused")})

@app.post("/api/play")
def play():
    u = get_user()
    if not u: return jsonify(error="Login required"),401
    if u["blocked"]: return jsonify(error="Account blocked"),403
    if setting("paused") == "1" or setting("maintenance") == "1": return jsonify(error="Game is paused"),400
    data = request.get_json(silent=True) or {}
    choice = str(data.get("choice","")).lower()
    try: amount = int(data.get("amount",0))
    except: amount = 0
    if choice not in ("big","small") or amount < int(setting("min_bet")) or amount > int(setting("max_bet")):
        return jsonify(error="Invalid selection or amount"),400
    with db() as c:
        current = c.execute("SELECT balance FROM users WHERE id=?",(u["id"],)).fetchone()["balance"]
        if amount > current: return jsonify(error="Insufficient virtual coins"),400
        result = secrets.randbelow(10)
        outcome = "big" if result >= 5 else "small"
        win = choice == outcome
        # Practice-only virtual coins. No cash value or real-money payouts.
        reward = amount if win else 0
        new_balance = current - amount + (amount + reward if win else 0)
        cur = c.execute("INSERT INTO rounds(result,created_at) VALUES(?,?)",(result,datetime.now().isoformat(timespec="seconds")))
        rid = cur.lastrowid
        c.execute("INSERT INTO bets(user_id,round_id,choice,amount,result,created_at) VALUES(?,?,?,?,?,?)",
                  (u["id"],rid,choice,amount,"won" if win else "lost",datetime.now().isoformat(timespec="seconds")))
        c.execute("UPDATE users SET balance=? WHERE id=?",(new_balance,u["id"]))
        c.execute("INSERT INTO transactions(user_id,kind,amount,status,note,created_at) VALUES(?,?,?,?,?,?)",
                  (u["id"],"game_win" if win else "game_loss", reward if win else -amount,"completed",f"Round {rid}",datetime.now().isoformat(timespec="seconds")))
    return jsonify(ok=True,round_id=rid,number=result,outcome=outcome,won=win,reward=reward,balance=new_balance)

@app.post("/api/request")
def make_request():
    u=get_user()
    if not u:return jsonify(error="Login required"),401
    data=request.get_json(silent=True) or {}
    kind=str(data.get("kind",""))
    try: amount=int(data.get("amount",0))
    except: amount=0
    if kind not in ("deposit","withdrawal") or amount<=0:return jsonify(error="Invalid request"),400
    if kind=="withdrawal":
        if amount<500 or amount>5000:return jsonify(error="Withdrawal limit: ₹500–₹5,000 (demo request only)"),400
        if amount>u["balance"]:return jsonify(error="Insufficient virtual coins"),400
    with db() as c:
        c.execute("INSERT INTO requests(user_id,kind,amount,status,created_at) VALUES(?,?,?,'pending',?)",
                  (u["id"],kind,amount,datetime.now().isoformat(timespec="seconds")))
    return jsonify(ok=True,message="Demo request submitted for admin review.")

@app.post("/api/admin/action")
def admin_action():
    if not is_admin():return jsonify(error="Admin only"),403
    d=request.get_json(silent=True) or {}; action=str(d.get("action",""))
    with db() as c:
        if action=="setting":
            key=str(d.get("key",""))
            if key not in ("round_seconds","min_bet","max_bet","paused","maintenance","referral_reward"):
                return jsonify(error="Invalid setting"),400
            c.execute("UPDATE settings SET value=? WHERE key=?",(str(d.get("value","")),key))
        elif action in ("approve","reject"):
            rid=int(d.get("id",0))
            req=c.execute("SELECT * FROM requests WHERE id=? AND status='pending'",(rid,)).fetchone()
            if not req:return jsonify(error="Pending request not found"),404
            status="approved" if action=="approve" else "rejected"
            c.execute("UPDATE requests SET status=? WHERE id=?",(status,rid))
            if req["kind"]=="deposit" and action=="approve":
                c.execute("UPDATE users SET balance=balance+? WHERE id=?",(req["amount"],req["user_id"]))
                c.execute("INSERT INTO transactions(user_id,kind,amount,status,note,created_at) VALUES(?,?,?,?,?,?)",
                          (req["user_id"],"demo_deposit",req["amount"],"completed","Admin approved demo request",datetime.now().isoformat(timespec="seconds")))
        elif action=="block":
            c.execute("UPDATE users SET blocked=? WHERE id=?",(int(bool(d.get("blocked"))),int(d.get("user_id",0))))
        elif action=="balance":
            uid=int(d.get("user_id",0)); amt=int(d.get("amount",0))
            c.execute("UPDATE users SET balance=MAX(0,balance+?) WHERE id=?",(amt,uid))
            c.execute("INSERT INTO transactions(user_id,kind,amount,status,note,created_at) VALUES(?,?,?,?,?,?)",
                      (uid,"admin_adjustment",amt,"completed","Admin wallet adjustment",datetime.now().isoformat(timespec="seconds")))
        elif action=="broadcast":
            c.execute("UPDATE settings SET value=? WHERE key='announcement'",(str(d.get("message",""))[:1000],))
        else:return jsonify(error="Unknown action"),400
        c.execute("INSERT INTO admin_logs(action,created_at) VALUES(?,?)",(action,datetime.now().isoformat(timespec="seconds")))
    return jsonify(ok=True)

@app.get("/health")
def health(): return jsonify(ok=True, app="BIG SMALL VIP")

PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BIG SMALL VIP</title>
<style>
:root{--gold:#f5c451;--bg:#090909;--card:#171717;--muted:#aaa}*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at top,#242014,#090909 50%);color:#f5f5f5;font-family:system-ui,Arial}header{padding:20px;text-align:center;border-bottom:1px solid #3c3219}h1{margin:0;color:var(--gold);letter-spacing:2px}small{color:#bbb}.wrap{max-width:850px;margin:auto;padding:16px}.card{background:var(--card);border:1px solid #3a311c;border-radius:18px;padding:16px;margin:12px 0}.row{display:flex;gap:10px;flex-wrap:wrap}.row>*{flex:1;min-width:120px}button,input,select,textarea{font:inherit;border-radius:12px;padding:12px;border:1px solid #54451f;background:#111;color:white;width:100%}button{background:linear-gradient(135deg,#f5c451,#9b6b12);color:#111;font-weight:800;border:0;cursor:pointer;margin-top:8px}button.secondary{background:#272727;color:#f5c451;border:1px solid #54451f}.big{background:#176b42;color:white}.small{background:#9b2424;color:white}.stat{font-size:24px;color:var(--gold);font-weight:800}.hidden{display:none}.muted{color:var(--muted);font-size:13px}pre{white-space:pre-wrap;overflow-wrap:anywhere;color:#ddd}.pill{display:inline-block;border:1px solid #51421e;border-radius:99px;padding:6px 10px;color:var(--gold);margin:3px}h2{color:var(--gold);font-size:18px}#msg{color:#ffe08a;min-height:24px}
</style></head><body><header><h1>👑 BIG SMALL VIP</h1><small>30-second rounds · Virtual coins practice game</small></header><main class="wrap">
<section id="login" class="card"><h2>🔐 Enter Game</h2><input id="name" placeholder="Your name"><input id="tid" placeholder="Telegram ID (optional)"><input id="adminkey" type="password" placeholder="Admin login key (admin only)"><button onclick="login()">Continue</button><p class="muted">Practice wallet only. No real-money betting or cash payout.</p></section>
<section id="player" class="hidden">
<div class="card row"><div><small>VIRTUAL BALANCE</small><div class="stat" id="balance">—</div></div><div><small>PLAYER</small><div id="username">—</div></div></div>
<div class="card"><h2>🎲 Choose Your Side</h2><div class="row"><button class="big" onclick="choose('big')">🟢 BIG (5–9)</button><button class="small" onclick="choose('small')">🔴 SMALL (0–4)</button></div><p id="chosen">No selection</p><label>Virtual coin amount</label><input id="amount" type="number" value="10" min="1"><button onclick="play()">🎯 PLAY ROUND</button><p id="result"></p></div>
<div class="card"><h2>💼 Wallet Requests (practice only)</h2><div class="row"><input id="reqamt" type="number" placeholder="Amount"><button onclick="req('deposit')">Demo Add Request</button><button class="secondary" onclick="req('withdrawal')">Demo Withdrawal Request</button></div><p class="muted">These are simulated requests and do not move real money.</p></div>
<div class="card"><h2>📜 Recent Game History</h2><div id="history"></div></div><div class="card"><h2>💳 Transactions</h2><div id="tx"></div></div>
</section>
<section id="admin" class="hidden">
<div class="card"><h2>👑 ADMIN PANEL · 30 FEATURES</h2><p id="stats"></p><div id="features"></div></div>
<div class="card"><h2>⚙️ Game Settings</h2><div class="row"><label>Round seconds<input id="s_round_seconds" type="number"></label><label>Min bet<input id="s_min_bet" type="number"></label><label>Max bet<input id="s_max_bet" type="number"></label><label>Referral reward<input id="s_referral_reward" type="number"></label></div><div class="row"><button onclick="saveSettings()">Save Settings</button><button class="secondary" onclick="toggle('paused')">Pause / Resume</button><button class="secondary" onclick="toggle('maintenance')">Maintenance Mode</button></div></div>
<div class="card"><h2>👥 Users</h2><div id="users"></div></div>
<div class="card"><h2>⏳ Pending Requests</h2><div id="requests"></div></div>
<div class="card"><h2>📢 Announcement</h2><textarea id="broadcast" placeholder="Announcement message"></textarea><button onclick="broadcast()">Save Announcement</button></div>
<div class="card"><h2>💰 Wallet Adjustment</h2><input id="adjuid" placeholder="User ID"><input id="adjamt" type="number" placeholder="Coins (+/-)"><button onclick="adjust()">Apply Virtual Coin Adjustment</button></div>
</section><p id="msg"></p></main>
<script>
let choice='',admin=false;
async function api(url,data){let r=await fetch(url,{method:data?'POST':'GET',headers:{'Content-Type':'application/json'},body:data?JSON.stringify(data):undefined});let j=await r.json();if(!r.ok)throw Error(j.error||'Request failed');return j}
function say(t){document.getElementById('msg').textContent=t}
async function login(){try{let j=await api('/api/login',{name:document.getElementById('name').value,telegram_id:document.getElementById('tid').value,admin_key:document.getElementById('adminkey').value});admin=j.admin;document.getElementById('login').classList.add('hidden');document.getElementById(admin?'admin':'player').classList.remove('hidden');await refresh()}catch(e){say(e.message)}}
function choose(c){choice=c;document.getElementById('chosen').textContent='Selected: '+c.toUpperCase()}
async function play(){try{if(!choice)throw Error('Choose BIG or SMALL first');let j=await api('/api/play',{choice,amount:document.getElementById('amount').value});document.getElementById('result').textContent=`Round #${j.round_id}: number ${j.number} · ${j.outcome.toUpperCase()} · ${j.won?'WIN':'LOSS'} · reward ${j.reward}`;await refresh()}catch(e){say(e.message)}}
async function req(kind){try{let j=await api('/api/request',{kind,amount:document.getElementById('reqamt').value});say(j.message);await refresh()}catch(e){say(e.message)}}
async function refresh(){let j=await api('/api/state');if(j.admin){document.getElementById('stats').textContent=`Users: ${j.stats.users} · Bets: ${j.stats.bets} · Pending requests: ${j.stats.pending_requests}`;for(let k in j.settings){let el=document.getElementById('s_'+k);if(el)el.value=j.settings[k]}document.getElementById('features').innerHTML=j.features.map((x,i)=>`<span class="pill">${i+1}. ${x}</span>`).join('');document.getElementById('users').innerHTML=j.users.map(u=>`<div class="card">#${u.id} ${esc(u.name)} · Balance ${u.balance} · ${u.blocked?'BLOCKED':'Active'}<div class="row"><button class="secondary" onclick="block(${u.id},${!u.blocked})">${u.blocked?'Unblock':'Block'}</button></div></div>`).join('')||'No users';document.getElementById('requests').innerHTML=j.requests.map(r=>`<div class="card">#${r.id} ${esc(r.name)} · ${r.kind} · ${r.amount} · ${r.status}<div class="row"><button onclick="decision(${r.id},'approve')">Accept</button><button class="secondary" onclick="decision(${r.id},'reject')">Reject</button></div></div>`).join('')||'No requests';}
else{document.getElementById('balance').textContent=j.user.balance+' coins';document.getElementById('username').textContent=j.user.name+' (#'+j.user.id+')';document.getElementById('history').innerHTML=j.history.map(x=>`<p>Round #${x.id} · Number ${x.result} · ${x.result>=5?'BIG':'SMALL'}</p>`).join('')||'No rounds yet';document.getElementById('tx').innerHTML=j.transactions.map(x=>`<p>${esc(x.kind)} · ${x.amount} · ${esc(x.status)}</p>`).join('')||'No transactions';}}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
async function decision(id,action){try{await api('/api/admin/action',{id,action});say('Request updated');await refresh()}catch(e){say(e.message)}}
async function block(user_id,blocked){try{await api('/api/admin/action',{action:'block',user_id,blocked});await refresh()}catch(e){say(e.message)}}
async function saveSettings(){for(let key of ['round_seconds','min_bet','max_bet','referral_reward'])await api('/api/admin/action',{action:'setting',key,value:document.getElementById('s_'+key).value});say('Settings saved');await refresh()}
async function toggle(key){let el=document.getElementById('s_'+key);let value=el?el.value:'0';await api('/api/admin/action',{action:'setting',key,value:value==='1'?'0':'1'});await refresh()}
async function broadcast(){await api('/api/admin/action',{action:'broadcast',message:document.getElementById('broadcast').value});say('Announcement saved')}
async function adjust(){try{await api('/api/admin/action',{action:'balance',user_id:document.getElementById('adjuid').value,amount:document.getElementById('adjamt').value});say('Balance updated');await refresh()}catch(e){say(e.message)}}
</script></body></html>"""

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
