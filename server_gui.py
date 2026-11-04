"""OneDeskBiz App - double-click server + dashboard (server wale PC par)."""
import os, sys, json, socket, threading, webbrowser
if sys.stdout is None: sys.stdout = open(os.devnull, "w")
if sys.stderr is None: sys.stderr = open(os.devnull, "w")
import tkinter as tk
from tkinter import messagebox
APP = os.path.join(os.environ.get("APPDATA", "."), "OneDeskBiz"); os.makedirs(APP, exist_ok=True); os.chdir(APP)
SET = os.path.join(APP, "app.json"); D = {"port": "8000", "api_key": "", "admin_password": "admin123"}
try: D.update(json.load(open(SET)))
except Exception: pass
srv = None
def ip():
    try: s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80)); return s.getsockname()[0]
    except Exception: return "localhost"
root = tk.Tk(); root.title("OneDeskBiz App"); root.geometry("460x330"); root.configure(bg="#F1F5F9")
tk.Label(root, text="OneDeskBiz  Dashboard Server", bg="#0F766E", fg="white", font=("Segoe UI", 15, "bold"), pady=10).pack(fill="x")
fr = tk.Frame(root, bg="#F1F5F9", padx=14, pady=10); fr.pack(fill="x"); V = {}
for i, (k, lab) in enumerate([("port", "Port"), ("api_key", "Connector API Key"), ("admin_password", "Admin password (first run)")]):
    tk.Label(fr, text=lab, bg="#F1F5F9").grid(row=i, column=0, sticky="w", pady=4)
    V[k] = tk.StringVar(value=D[k]); tk.Entry(fr, textvariable=V[k], width=30).grid(row=i, column=1, padx=8)
st = tk.StringVar(value="Stopped"); tk.Label(root, textvariable=st, bg="#F1F5F9", font=("Segoe UI", 11, "bold"), fg="#0F766E").pack(pady=4)
info = tk.StringVar(); tk.Label(root, textvariable=info, bg="#F1F5F9", justify="left", wraplength=420).pack()
def start():
    global srv
    if srv: return
    d = {k: V[k].get().strip() for k in V}
    if len(d["api_key"]) < 6: messagebox.showwarning("API Key", "API Key kam se kam 6 characters ka rakho. Wahi key Connector me daalni hai."); return
    json.dump(d, open(SET, "w")); os.environ["API_KEY"] = d["api_key"]; os.environ["ADMIN_PASSWORD"] = d["admin_password"]
    import uvicorn, server
    srv = uvicorn.Server(uvicorn.Config(server.app, host="0.0.0.0", port=int(d["port"]), log_config=None))
    threading.Thread(target=srv.run, daemon=True).start()
    st.set("Running"); info.set(f"Is PC par: http://localhost:{d['port']}\nMobile / dusre PC par: http://{ip()}:{d['port']}\nLogin: admin / (upar wala admin password)\nConnector me Server URL: http://{ip()}:{d['port']}")
def stop():
    global srv
    if srv: srv.should_exit = True; srv = None; st.set("Stopped (dobara start ke liye app band karke kholo)")
bf = tk.Frame(root, bg="#F1F5F9"); bf.pack(pady=8)
for t, f in (("Start Server", start), ("Open Dashboard", lambda: webbrowser.open(f"http://localhost:{V['port'].get()}")), ("Stop", stop)):
    tk.Button(bf, text=t, command=f, width=15, bg="#0F766E", fg="white", relief="flat").pack(side="left", padx=5)
root.mainloop()
