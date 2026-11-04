"""OneDeskBiz Cloud Server: sync API + login + web app.  Run: uvicorn server:app --host 0.0.0.0 --port 8000"""
import os, sys, sqlite3, time, hmac, hashlib, secrets
from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.responses import HTMLResponse

API_KEY = os.getenv("API_KEY", "change-me")
if os.path.exists("secret.key"): SECRET = open("secret.key").read()
else: SECRET = secrets.token_hex(32); open("secret.key", "w").write(SECRET)
db = sqlite3.connect("data.db", check_same_thread=False); db.row_factory = sqlite3.Row
db.executescript("""
CREATE TABLE IF NOT EXISTS ledgers(company, name, parent, opening, closing, PRIMARY KEY(company,name));
CREATE TABLE IF NOT EXISTS vouchers(company, id, date, vtype, number, party, amount, narration, PRIMARY KEY(company,id));
CREATE TABLE IF NOT EXISTS stocks(company, name, parent, unit, qty, value, rate, PRIMARY KEY(company,name));
CREATE TABLE IF NOT EXISTS syncs(company PRIMARY KEY, ts);
CREATE TABLE IF NOT EXISTS users(username PRIMARY KEY, pw, role, companies);
""")
def pw(p): return hashlib.pbkdf2_hmac("sha256", p.encode(), SECRET.encode(), 100000).hex()
if not db.execute("SELECT 1 FROM users").fetchone():
    db.execute("INSERT INTO users VALUES(?,?,?,?)", ("admin", pw(os.getenv("ADMIN_PASSWORD", "admin123")), "admin", "*")); db.commit()
sig = lambda u, e: hmac.new(SECRET.encode(), f"{u}.{e}".encode(), hashlib.sha256).hexdigest()
app = FastAPI(title="OneDeskBiz")

def auth(authorization: str = Header("")):
    try:
        u, e, s = authorization.replace("Bearer ", "").split(".")
        assert hmac.compare_digest(s, sig(u, e)) and int(e) > time.time()
        return dict(db.execute("SELECT * FROM users WHERE username=?", (u,)).fetchone())
    except Exception: raise HTTPException(401, "login required")

def comps(u):
    allc = [r[0] for r in db.execute("SELECT company FROM syncs ORDER BY company")]
    return allc if u["companies"] == "*" else [c for c in allc if c in u["companies"].split(",")]

def co(u, c):
    cs = comps(u)
    if c and c not in cs: raise HTTPException(403, "no access")
    return c or (cs[0] if cs else "")

@app.post("/api/sync")                       # Agent yaha data bhejta hai
def sync(p: dict, x_api_key: str = Header("")):
    if x_api_key != API_KEY: raise HTTPException(401, "bad key")
    c = p["company"]
    for l in p["ledgers"]: db.execute("REPLACE INTO ledgers VALUES(?,?,?,?,?)", (c, l["name"], l["parent"], l["opening"], l["closing"]))
    for s in p.get("stocks", []): db.execute("REPLACE INTO stocks VALUES(?,?,?,?,?,?,?)", (c, s["name"], s["parent"], s["unit"], s["qty"], s["value"], s["rate"]))
    for v in p["vouchers"]: db.execute("REPLACE INTO vouchers VALUES(?,?,?,?,?,?,?,?)", (c, v["id"], v["date"], v["vtype"], v["number"], v["party"], v["amount"], v["narration"]))
    f, t = p["window"]; ids = set(p["voucher_ids"])
    for (i,) in db.execute("SELECT id FROM vouchers WHERE company=? AND date BETWEEN ? AND ?", (c, f, t)).fetchall():
        if i not in ids: db.execute("DELETE FROM vouchers WHERE company=? AND id=?", (c, i))
    db.execute("REPLACE INTO syncs VALUES(?,?)", (c, int(time.time()))); db.commit()
    return {"ok": True}

@app.post("/api/login")
def login(p: dict):
    r = db.execute("SELECT * FROM users WHERE username=?", (p.get("username", ""),)).fetchone()
    if not r or not hmac.compare_digest(r["pw"], pw(p.get("password", ""))): raise HTTPException(401, "wrong username/password")
    e = int(time.time()) + 30 * 86400
    return {"token": f"{r['username']}.{e}.{sig(r['username'], e)}", "role": r["role"], "user": r["username"]}

@app.get("/api/companies")
def companies(u=Depends(auth)):
    return [{"name": c, "last_sync": db.execute("SELECT ts FROM syncs WHERE company=?", (c,)).fetchone()[0]} for c in comps(u)]

@app.get("/api/summary")
def summary(company: str = "", u=Depends(auth)):
    c = co(u, company); one = lambda s, *a: db.execute(s, (c, *a)).fetchone()[0]
    rows = lambda s: [dict(r) for r in db.execute(s, (c,))]
    sales = one("SELECT COALESCE(SUM(ABS(amount)),0) FROM vouchers WHERE company=? AND vtype LIKE '%Sales%'")
    by = lambda t: one(f"SELECT COALESCE(SUM(ABS(amount)),0) FROM vouchers WHERE company=? AND vtype LIKE '%{t}%'")
    d = {"company": c, "sales": sales, "purchase": by("Purchase"), "receipts": by("Receipt"), "payments": by("Payment"),
         "receivable": one("SELECT COALESCE(SUM(ABS(closing)),0) FROM ledgers WHERE company=? AND parent='Sundry Debtors'"),
         "payable": one("SELECT COALESCE(SUM(ABS(closing)),0) FROM ledgers WHERE company=? AND parent='Sundry Creditors'"),
         "cash_bank": one("SELECT COALESCE(SUM(closing),0) FROM ledgers WHERE company=? AND parent IN ('Cash-in-Hand','Bank Accounts')"),
         "monthly": rows("SELECT substr(date,1,6) m, SUM(CASE WHEN vtype LIKE '%Sales%' THEN ABS(amount) ELSE 0 END) sales, SUM(CASE WHEN vtype LIKE '%Purchase%' THEN ABS(amount) ELSE 0 END) purchase FROM vouchers WHERE company=? GROUP BY m ORDER BY m DESC LIMIT 6")[::-1]}
    if u["role"] == "sales": d["purchase"] = d["payable"] = d["payments"] = None
    return d

@app.get("/api/outstanding")
def outstanding(kind: str = "debtors", q: str = "", company: str = "", u=Depends(auth)):
    c = co(u, company); g = "Sundry Creditors" if kind == "creditors" else "Sundry Debtors"
    if g == "Sundry Creditors" and u["role"] == "sales": raise HTTPException(403, "no access")
    return [dict(r) for r in db.execute("""SELECT l.name, ABS(l.closing) bal, (SELECT MAX(date) FROM vouchers v WHERE v.company=l.company AND v.party=l.name) last_date
        FROM ledgers l WHERE l.company=? AND l.parent=? AND l.closing!=0 AND l.name LIKE ? ORDER BY bal DESC LIMIT 300""", (c, g, f"%{q}%"))]

@app.get("/api/daybook")
def daybook(vtype: str = "", q: str = "", party: str = "", company: str = "", u=Depends(auth)):
    c = co(u, company)
    return [dict(r) for r in db.execute("""SELECT date, vtype, number, party, amount, narration FROM vouchers WHERE company=? AND vtype LIKE ?
        AND (party LIKE ? OR number LIKE ? OR narration LIKE ?) AND party LIKE ? ORDER BY date DESC, id DESC LIMIT 300""", (c, f"%{vtype}%", f"%{q}%", f"%{q}%", f"%{q}%", f"%{party}%"))]

@app.get("/api/stock")
def stock(q: str = "", company: str = "", u=Depends(auth)):
    c = co(u, company)
    return [dict(r) for r in db.execute("SELECT name, parent, unit, qty, rate, value FROM stocks WHERE company=? AND name LIKE ? ORDER BY ABS(value) DESC LIMIT 500", (c, f"%{q}%"))]

@app.get("/api/users")
def users(u=Depends(auth)):
    if u["role"] != "admin": raise HTTPException(403, "admin only")
    return [dict(r) for r in db.execute("SELECT username, role, companies FROM users")]

@app.post("/api/users")
def add_user(p: dict, u=Depends(auth)):
    if u["role"] != "admin": raise HTTPException(403, "admin only")
    n = p.get("username", "").strip()
    if not n.isalnum() or len(p.get("password", "")) < 6 or p.get("role") not in ("admin", "accountant", "sales"): raise HTTPException(400, "invalid: username letters/numbers, password 6+, role admin/accountant/sales")
    db.execute("REPLACE INTO users VALUES(?,?,?,?)", (n, pw(p["password"]), p["role"], p.get("companies") or "*")); db.commit(); return {"ok": True}

@app.delete("/api/users/{name}")
def del_user(name: str, u=Depends(auth)):
    if u["role"] != "admin" or name == u["username"]: raise HTTPException(403, "not allowed")
    db.execute("DELETE FROM users WHERE username=?", (name,)); db.commit(); return {"ok": True}

@app.get("/", response_class=HTMLResponse)
def home(): return open(os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "web.html"), encoding="utf-8").read()
