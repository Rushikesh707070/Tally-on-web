"""OneDeskBiz Tally Connector - double-click app (Tally wale PC par)."""
import os, sys, json, threading, logging, queue
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
import tkinter as tk
from tkinter import ttk, messagebox
import requests
APP = os.path.join(os.environ.get("APPDATA", "."), "OneDeskBiz"); os.makedirs(APP, exist_ok=True); os.chdir(APP)
import agent
SET = os.path.join(APP, "connector.json")
D = {"tally_url": "http://localhost:9000", "server_url": "http://localhost:8000", "api_key": "", "interval_seconds": 300, "autostart": False}
try: D.update(json.load(open(SET)))
except Exception: pass
q = queue.Queue(); stop = threading.Event(); th = None
class QH(logging.Handler):
    def emit(self, r): q.put(self.format(r))
h = QH(); h.setFormatter(logging.Formatter("%(asctime)s  %(message)s", "%H:%M:%S")); agent.log.addHandler(h); agent.log.setLevel(logging.INFO)

root = tk.Tk(); root.title("OneDeskBiz - Tally Connector"); root.geometry("560x470"); root.configure(bg="#F1F5F9")
tk.Label(root, text="OneDeskBiz  Tally Connector", bg="#0F766E", fg="white", font=("Segoe UI", 15, "bold"), pady=10).pack(fill="x")
fr = tk.Frame(root, bg="#F1F5F9", padx=14, pady=8); fr.pack(fill="x")
V = {}
for i, (k, lab) in enumerate([("tally_url", "Tally URL"), ("server_url", "OneDeskBiz Server URL"), ("api_key", "API Key"), ("interval_seconds", "Sync every (seconds)")]):
    tk.Label(fr, text=lab, bg="#F1F5F9").grid(row=i, column=0, sticky="w", pady=3)
    V[k] = tk.StringVar(value=str(D[k])); tk.Entry(fr, textvariable=V[k], width=44, show="*" if k == "api_key" else "").grid(row=i, column=1, padx=8)
auto = tk.BooleanVar(value=D["autostart"]); tk.Checkbutton(fr, text="Windows start hote hi Connector chalu karo", variable=auto, bg="#F1F5F9").grid(row=4, column=1, sticky="w")
status = tk.StringVar(value="Stopped"); tk.Label(root, textvariable=status, bg="#F1F5F9", font=("Segoe UI", 11, "bold"), fg="#0F766E").pack()
log = tk.Text(root, height=12, font=("Consolas", 9)); log.pack(fill="both", expand=True, padx=14, pady=6)

def put(s): q.put(s)
def save():
    try: iv = max(60, int(V["interval_seconds"].get()))
    except ValueError: iv = 300
    d = {k: V[k].get().strip() for k in ("tally_url", "server_url", "api_key")}; d.update(interval_seconds=iv, autostart=auto.get())
    json.dump(d, open(SET, "w")); agent.CFG.update(d); set_autostart(auto.get()); return d
def set_autostart(on):
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if on: winreg.SetValueEx(k, "OneDeskBizConnector", 0, winreg.REG_SZ, f'"{sys.executable}" --auto')
        else:
            try: winreg.DeleteValue(k, "OneDeskBizConnector")
            except FileNotFoundError: pass
    except Exception as e: put(f"Autostart set nahi hua: {e}")
def test():
    d = save()
    try: names = [c["NAME"] for c in agent.collection("CompColl", "Company", ["Name"])]; put(f"Tally OK. Companies: {', '.join(names) or 'none open'}")
    except Exception as e: put(f"Tally connect nahi hua (Tally open? Port 9000 on?): {e}")
    try: put(f"Server OK ({requests.get(d['server_url'], timeout=10).status_code})")
    except Exception as e: put(f"Server connect nahi hua: {e}")
def worker():
    while not stop.is_set():
        try: agent.sync_once(); status.set("Running - last sync OK")
        except Exception as e: put(f"Sync fail: {e}"); status.set("Running - error, retrying")
        stop.wait(agent.CFG["interval_seconds"])
    status.set("Stopped")
def start():
    global th
    if th and th.is_alive(): return
    save(); stop.clear(); th = threading.Thread(target=worker, daemon=True); th.start(); status.set("Running...")
def halt(): stop.set()
bf = tk.Frame(root, bg="#F1F5F9"); bf.pack(pady=6)
for t, f in (("Test Connection", lambda: threading.Thread(target=test, daemon=True).start()), ("Start Sync", start), ("Stop", halt)):
    tk.Button(bf, text=t, command=f, width=16, bg="#0F766E", fg="white", relief="flat").pack(side="left", padx=5)
def pump():
    while not q.empty(): log.insert("end", q.get() + "\n"); log.see("end")
    root.after(300, pump)
pump()
if "--auto" in sys.argv and D["api_key"]: root.after(500, start)
root.mainloop()
