"""OneDeskBiz Agent - Tally wale PC par chalao. Har 5 min me data server ko bhejta hai."""
import re, time, json, hashlib, logging
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from xml.sax.saxutils import escape
import requests

CFG = {"tally_url": "http://localhost:9000", "server_url": "http://localhost:8000", "api_key": "change-me", "interval_seconds": 300, "voucher_days": 90}
try: CFG.update(json.load(open("config.json")))
except Exception: pass
STATE_FILE = "state.json"
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("agent")


def tally(xml):
    r = requests.post(CFG["tally_url"], data=xml.encode("utf-8"), timeout=180)
    t = r.content.decode("utf-8", "ignore")
    t = re.sub(r"&#(?:[0-9]|1[0-9]|2[0-9]|3[01]);", "", t)      # Tally ke invalid chars
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", t)
    return ET.fromstring(t)


def collection(cid, ctype, fields, company=None, frm=None, to=None):
    sv = "<SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>"
    if company: sv += f"<SVCURRENTCOMPANY>{escape(company)}</SVCURRENTCOMPANY>"
    if frm: sv += f"<SVFROMDATE>{frm}</SVFROMDATE><SVTODATE>{to}</SVTODATE>"
    nm = "".join(f"<NATIVEMETHOD>{f}</NATIVEMETHOD>" for f in fields)
    xml = (f"<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST>"
           f"<TYPE>Collection</TYPE><ID>{cid}</ID></HEADER><BODY><DESC>"
           f"<STATICVARIABLES>{sv}</STATICVARIABLES><TDL><TDLMESSAGE>"
           f'<COLLECTION NAME="{cid}" ISMODIFY="No"><TYPE>{ctype}</TYPE>{nm}</COLLECTION>'
           f"</TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>")
    root = tally(xml)
    rows = []
    for el in root.iter(ctype.upper()):
        d = {c.tag.upper(): (c.text or "").strip() for c in el}
        d["NAME"] = el.get("NAME") or d.get("NAME", "")
        rows.append(d)
    return rows


def num(s):
    m = re.search(r"-?\d+(?:\.\d+)?", (s or "").replace(",", ""))
    return float(m.group()) if m else 0.0


def h(d): return hashlib.md5(json.dumps(d, sort_keys=True).encode()).hexdigest()


def load_state():
    try: return json.load(open(STATE_FILE))
    except Exception: return {}


def sync_once():
    state = load_state()
    to = date.today(); frm = to - timedelta(days=CFG["voucher_days"])
    f, t = frm.strftime("%Y%m%d"), to.strftime("%Y%m%d")
    companies = [c["NAME"] for c in collection("CompColl", "Company", ["Name"]) if c["NAME"]]
    for co in companies:
        ledgers = [{"name": r["NAME"], "parent": r.get("PARENT", ""),
                    "opening": num(r.get("OPENINGBALANCE")), "closing": num(r.get("CLOSINGBALANCE"))}
                   for r in collection("LedgerColl", "Ledger", ["Parent", "OpeningBalance", "ClosingBalance"], co)]
        vouchers = [{"id": r.get("MASTERID", ""), "date": r.get("DATE", ""), "vtype": r.get("VOUCHERTYPENAME", ""),
                     "number": r.get("VOUCHERNUMBER", ""), "party": r.get("PARTYLEDGERNAME", ""),
                     "amount": num(r.get("AMOUNT")), "narration": r.get("NARRATION", "")}
                    for r in collection("VchColl", "Voucher",
                        ["MasterId", "Date", "VoucherTypeName", "VoucherNumber", "PartyLedgerName", "Amount", "Narration"],
                        co, f, t)]
        stocks = [{"name": r["NAME"], "parent": r.get("PARENT", ""), "unit": r.get("BASEUNITS", ""), "qty": num(r.get("CLOSINGBALANCE")),
                   "value": num(r.get("CLOSINGVALUE")), "rate": num(r.get("CLOSINGRATE"))}
                  for r in collection("StkColl", "StockItem", ["Parent", "BaseUnits", "ClosingBalance", "ClosingValue", "ClosingRate"], co)]
        old = state.get(co, {})
        new = {}
        chg_l = [x for x in ledgers if new.setdefault("L:" + x["name"], h(x)) != old.get("L:" + x["name"])]
        chg_v = [x for x in vouchers if new.setdefault("V:" + x["id"], h(x)) != old.get("V:" + x["id"])]
        chg_s = [x for x in stocks if new.setdefault("S:" + x["name"], h(x)) != old.get("S:" + x["name"])]
        payload = {"stocks": chg_s, "company": co, "ledgers": chg_l, "vouchers": chg_v,
                   "window": [f, t], "voucher_ids": [v["id"] for v in vouchers]}
        r = requests.post(CFG["server_url"] + "/api/sync", json=payload,
                          headers={"x-api-key": CFG["api_key"]}, timeout=120)
        r.raise_for_status()
        state[co] = new
        log.info("%s: %d ledgers, %d vouchers sent (changed only)", co, len(chg_l), len(chg_v))
    json.dump(state, open(STATE_FILE, "w"))


if __name__ == "__main__":
    while True:
        try: sync_once()
        except Exception as e: log.error("Sync fail (Tally open hai? port 9000 on hai?): %s", e)
        time.sleep(CFG["interval_seconds"])
