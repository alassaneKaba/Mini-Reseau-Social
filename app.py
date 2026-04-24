from flask import Flask, render_template, request, redirect, session,jsonify
import sqlite3, os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.urandom(24)

@app.route("/")
def home():
    with sqlite3.connect("database.db") as db:
        posts = db.execute("""
        SELECT posts.*, users.avatar,
            (SELECT COUNT(*) FROM reactions WHERE post_id=posts.id AND type='thumb') as thumbs,
            (SELECT COUNT(*) FROM reactions WHERE post_id=posts.id AND type='heart') as hearts,
            (SELECT type FROM reactions WHERE post_id=posts.id AND username=?) as user_reaction
        FROM posts
        JOIN users ON posts.username = users.username
        ORDER BY posts.id DESC
        """, (session.get("user"),)).fetchall()
        comments = db.execute("SELECT * FROM comments").fetchall()
    return render_template("home.html", posts=posts, comments=comments)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        with sqlite3.connect("database.db") as db:
            user = db.execute(
                "SELECT * FROM users WHERE username = ? AND password = ?",
                (username, password)
            ).fetchone()
        if user:
            session["user"] = username
            return redirect("/")
        else:
            return "Identifiants incorrects ❌"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        file = request.files.get("avatar")
        avatar_filename = None
        if file and file.filename != "":
            avatar_filename = secure_filename(file.filename)
            file.save(os.path.join("static/avatars", avatar_filename))
        with sqlite3.connect("database.db") as db:
            try:
                db.execute(
                    "INSERT INTO users (username, password, avatar) VALUES (?, ?, ?)",
                    (username, password, avatar_filename)
                )
            except:
                return "Utilisateur existe déjà"
        return redirect("/login")
    return render_template("register.html")

UPLOAD_FOLDER = "static/uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
@app.route("/post", methods=["POST"])
def post():
    if not session.get("user"):
        return redirect("/login")
    content = request.form["content"]
    file = request.files.get("image")
    filename = None
    if file and file.filename != "":
        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
    with sqlite3.connect("database.db") as db:
        db.execute(
            "INSERT INTO posts (username, content, likes, image) VALUES (?, ?, 0, ?)",
            (session["user"], content, filename)
        )
    return redirect("/")

@app.route("/react/<int:post_id>/<reaction_type>", methods=["POST"])
def react(post_id, reaction_type):
    if not session.get("user"):
        return jsonify({"error": "not_logged"}), 403
    username = session["user"]
    with sqlite3.connect("database.db") as db:
        # récupérer le propriétaire du post
        owner = db.execute(
            "SELECT username FROM posts WHERE id=?",
            (post_id,)
        ).fetchone()[0]
        # créer notification (si ce n'est pas soi-même)
        if owner != username:
            db.execute(
                "INSERT INTO notifications (username, message) VALUES (?, ?)",
                (owner, f"{username} a réagi à ton post")
            )
        # vérifier si réaction existe
        existing = db.execute(
            "SELECT type FROM reactions WHERE username=? AND post_id=?",
            (username, post_id)
        ).fetchone()
        if existing:
            if existing[0] == reaction_type:
                # même réaction → on supprime (toggle off)
                db.execute(
                    "DELETE FROM reactions WHERE username=? AND post_id=?",
                    (username, post_id)
                )
            else:
                # changer réaction
                db.execute(
                    "UPDATE reactions SET type=? WHERE username=? AND post_id=?",
                    (reaction_type, username, post_id)
                )
        else:
            # nouvelle réaction
            db.execute(
                "INSERT INTO reactions (username, post_id, type) VALUES (?, ?, ?)",
                (username, post_id, reaction_type)
            )
        # compter les réactions
        counts = db.execute("""
            SELECT type, COUNT(*) 
            FROM reactions 
            WHERE post_id=? 
            GROUP BY type
        """, (post_id,)).fetchall()
    result = {"thumb": 0, "heart": 0}
    for t, c in counts:
        result[t] = c
    return jsonify(result)

@app.route("/notifications")
def notifications():
    if not session.get("user"):
        return redirect("/login")
    with sqlite3.connect("database.db") as db:
        notifs = db.execute(
            "SELECT message FROM notifications WHERE username=? ORDER BY id DESC",
            (session["user"],)
        ).fetchall()
    return render_template("notifications.html", notifs=notifs)

@app.route("/comment/<int:post_id>", methods=["POST"])
def comment(post_id):
    if not session.get("user"):
        return jsonify({"error": "not_logged"}), 403
    content = request.form["content"]
    username = session["user"]
    with sqlite3.connect("database.db") as db:
        db.execute(
            "INSERT INTO comments (post_id, username, content) VALUES (?, ?, ?)",
            (post_id, username, content)
        )
    return jsonify({
        "username": username,
        "content": content
    })

@app.route("/user/<username>")
def profile(username):
    with sqlite3.connect("database.db") as db:
        posts = db.execute("""
        SELECT posts.*, users.avatar,
            (SELECT COUNT(*) FROM reactions WHERE post_id=posts.id AND type='thumb'),
            (SELECT COUNT(*) FROM reactions WHERE post_id=posts.id AND type='heart')
        FROM posts
        JOIN users ON posts.username = users.username
        WHERE posts.username=?
        ORDER BY posts.id DESC
        """, (username,)).fetchall()
    return render_template("profile.html", posts=posts, username=username)

@app.route("/delete/<int:post_id>", methods=["POST"])
def delete(post_id):
    if not session.get("user"):
        return redirect("/login")
    with sqlite3.connect("database.db") as db:
        db.execute(
            "DELETE FROM posts WHERE id=? AND username=?",
            (post_id, session["user"])
        )
    return redirect("/")

def init_db():
    db = sqlite3.connect("database.db")
    db.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        avatar TEXT
    )
    """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        content TEXT,
        likes INTEGER DEFAULT 0,
        image TEXT
    )
    """)
    db.execute("""
   CREATE TABLE IF NOT EXISTS comments (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       post_id INTEGER,
       username TEXT,
       content TEXT
    )
    """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS reactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        post_id INTEGER,
        type TEXT,
        UNIQUE(username, post_id)
    )
    """)
    db.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT,
        message TEXT
    )
    """)
    db.commit()
    db.close()

init_db()

if __name__ == "__main__":
    app.run(debug=True)