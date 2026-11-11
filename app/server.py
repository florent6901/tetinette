import json, os, sqlite3, mimetypes
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

DB = os.environ.get("DB_PATH", "/data/bebe.db")
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
os.makedirs(os.path.dirname(DB), exist_ok=True)

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

with db() as c:
    c.execute("CREATE TABLE IF NOT EXISTS babies(id INTEGER PRIMARY KEY, name TEXT NOT NULL, birth TEXT)")
    c.execute("""CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, ts TEXT NOT NULL,
        kind TEXT NOT NULL, side TEXT, milk TEXT, ml INTEGER, baby_id INTEGER)""")
    c.execute("CREATE TABLE IF NOT EXISTS weights(id INTEGER PRIMARY KEY, day TEXT NOT NULL, grams INTEGER NOT NULL, baby_id INTEGER)")
    # Migration depuis la première version (sans multi-bébés)
    for t in ("events", "weights"):
        if "baby_id" not in [r["name"] for r in c.execute(f"PRAGMA table_info({t})")]:
            c.execute(f"ALTER TABLE {t} ADD COLUMN baby_id INTEGER")
    if any(c.execute(f"SELECT 1 FROM {t} WHERE baby_id IS NULL").fetchone() for t in ("events", "weights")):
        bid = c.execute("INSERT INTO babies(name) VALUES('Bébé')").lastrowid
        for t in ("events", "weights"):
            c.execute(f"UPDATE {t} SET baby_id=? WHERE baby_id IS NULL", (bid,))

class H(BaseHTTPRequestHandler):
    def send(self, code, body, ctype="application/json", cache=None):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if cache: self.send_header("Cache-Control", cache)
        self.end_headers()
        self.wfile.write(data)

    def body(self):
        return json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/data":
            with db() as c:
                out = {t: [dict(r) for r in c.execute(q)] for t, q in (
                    ("babies", "SELECT * FROM babies ORDER BY id"),
                    ("events", "SELECT * FROM events ORDER BY ts DESC, id DESC"),
                    ("weights", "SELECT * FROM weights ORDER BY day ASC"))}
            return self.send(200, out)
        name = "index.html" if path in ("/", "") else os.path.basename(path)
        full = os.path.join(STATIC, name)
        if not os.path.isfile(full):
            return self.send(404, {"error": "introuvable"})
        ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
        with open(full, "rb") as f:
            self.send(200, f.read(), ctype + ("; charset=utf-8" if ctype.startswith("text") else ""),
                      "public, max-age=86400" if name.endswith(".png") else "no-cache")

    def do_POST(self):
        d = self.body()
        with db() as c:
            if self.path == "/api/events":
                c.execute("INSERT INTO events(ts,kind,side,milk,ml,baby_id) VALUES(?,?,?,?,?,?)",
                          (d["ts"], d["kind"], d.get("side"), d.get("milk"), d.get("ml"), d["baby_id"]))
            elif self.path == "/api/weights":
                c.execute("INSERT INTO weights(day,grams,baby_id) VALUES(?,?,?)", (d["day"], int(d["grams"]), d["baby_id"]))
            elif self.path == "/api/babies":
                cur = c.execute("INSERT INTO babies(name,birth) VALUES(?,?)", (d["name"], d.get("birth") or None))
                return self.send(200, {"id": cur.lastrowid})
            else:
                return self.send(404, {})
        self.send(200, {"ok": True})

    def do_PUT(self):
        parts = self.path.strip("/").split("/")
        if parts[:2] != ["api", "babies"] or len(parts) != 3:
            return self.send(404, {})
        d = self.body()
        with db() as c:
            c.execute("UPDATE babies SET name=?, birth=? WHERE id=?", (d["name"], d.get("birth") or None, int(parts[2])))
        self.send(200, {"ok": True})

    def do_DELETE(self):
        parts = self.path.strip("/").split("/")
        if len(parts) != 3 or parts[1] not in ("events", "weights", "babies"):
            return self.send(404, {})
        i = int(parts[2])
        with db() as c:
            if parts[1] == "babies":
                c.execute("DELETE FROM events WHERE baby_id=?", (i,))
                c.execute("DELETE FROM weights WHERE baby_id=?", (i,))
            c.execute(f"DELETE FROM {parts[1]} WHERE id=?", (i,))
        self.send(200, {"ok": True})

    def log_message(self, *a): pass

if __name__ == "__main__":
    print("Tétinette écoute sur le port 8086")
    ThreadingHTTPServer(("0.0.0.0", 8086), H).serve_forever()
