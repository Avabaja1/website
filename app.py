from flask import Flask, render_template, request, redirect, abort
import sqlite3
from contextlib import closing

app = Flask(__name__)
DB_PATH = "database.db"
ADMIN_PASSWORD = "k123"  # поменяй на свой

def init_db():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    status TEXT,
                    ip TEXT
                )
            """)

@app.before_request
def protect_admin():
    if request.path.startswith("/admin") or request.path.startswith("/update"):
        auth = request.authorization
        if not auth or auth.username != "admin" or auth.password != ADMIN_PASSWORD:
            return abort(401)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", status=None)

@app.route("/check", methods=["POST"])
def check():
    username = request.form.get("username")
    if not username:
        return redirect("/")

    user_ip = request.remote_addr

    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT status FROM users WHERE username = ?", (username,))
        row = c.fetchone()
        if row:
            status = row[0]
            if status == "проверено":
                return render_template("thank_you.html")
            elif status == "отказано":
                return render_template("status.html", message="Вам отказано в подписке.")
            elif status == "ожидание":
                return render_template("status.html", message="Ваш запрос в ожидании проверки.")
        else:
            c.execute("INSERT INTO users (username, status, ip) VALUES (?, ?, ?)", (username, "ожидание", user_ip))
            conn.commit()
            return render_template("status.html", message="Ваш запрос в ожидании проверки.")

    return redirect("/")

@app.route("/admin", methods=["GET"])
def admin():
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, status, ip FROM users ORDER BY id")
        users = c.fetchall()
    return render_template("admin.html", users=users)

@app.route("/update", methods=["POST"])
def update():
    username = request.form.get("username")
    status = request.form.get("status")
    with closing(sqlite3.connect(DB_PATH)) as conn:
        c = conn.cursor()
        c.execute("UPDATE users SET status = ? WHERE username = ?", (status, username))
        conn.commit()
    return redirect("/admin")

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000)

