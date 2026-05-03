"""
Aura AI — Flask Backend v3.0
SQLite coin system, streaming AI, tier-based access, true auth, chat history, limits.
"""
import os, io, base64, json, time, hashlib, sqlite3, re
from datetime import datetime
from flask import Flask, request, jsonify, session, send_from_directory, Response, stream_with_context
from flask_cors import CORS
from dotenv import load_dotenv

load_dotenv()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

app = Flask(__name__, static_folder="static", static_url_path="/static")
app.secret_key = os.getenv("SECRET_KEY", "aura-ultra-2025")
CORS(app, supports_credentials=True)

DATABASE_URL = os.getenv("DATABASE_URL")

if os.getenv("VERCEL"):
    DB_PATH = "/tmp/aura.db"
else:
    DB_PATH = os.path.join(os.path.dirname(__file__), "aura.db")

class DBWrapper:
    def __init__(self, conn):
        self.conn = conn
    def execute(self, query, params=None):
        import psycopg2.extras
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        # Convert SQLite ? to Postgres %s
        query = query.replace('?', '%s')
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur
    def executescript(self, query):
        cur = self.conn.cursor()
        cur.execute(query)
        return cur

from contextlib import contextmanager

@contextmanager
def get_db():
    if DATABASE_URL:
        import psycopg2
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        try:
            yield DBWrapper(conn)
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(DB_PATH, timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

def init_db():
    with get_db() as conn:
        if DATABASE_URL:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                coins INTEGER DEFAULT 0,
                plan TEXT DEFAULT 'free',
                plan_expires_at INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_login_date TEXT DEFAULT '',
                created_at INTEGER DEFAULT 0,
                images_today INTEGER DEFAULT 0,
                slides_today INTEGER DEFAULT 0,
                last_action_date TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tasks (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                coins_reward INTEGER NOT NULL,
                icon TEXT DEFAULT 'star',
                repeatable INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_tasks (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                task_key TEXT NOT NULL,
                completed_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER DEFAULT 0
            );
            """)
            tasks = [
                ("daily_login",    "Kunlik kirish",             "Har kuni platformaga kiring",                    5,  "calendar", 1),
                ("first_chat",     "Birinchi suhbat",           "AI bilan birinchi marta yozishing",             10, "message",  0),
                ("first_image",    "Birinchi rasm",             "Imagine AI da birinchi rasmni yarating",        10, "image",    0),
                ("first_slide",    "Birinchi prezentatsiya",    "Slides AI da ilk slaydni yarating",             10, "layout",   0),
                ("share_app",      "Do'stlarga ulashish",       "Aura AI ni do'stlarga ulashing",                20, "share",    0),
            ]
            for t in tasks:
                conn.execute("INSERT INTO tasks (key,title,description,coins_reward,icon,repeatable) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (key) DO NOTHING", t)
        else:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                coins INTEGER DEFAULT 0,
                plan TEXT DEFAULT 'free',
                plan_expires_at INTEGER DEFAULT 0,
                streak INTEGER DEFAULT 0,
                last_login_date TEXT DEFAULT '',
                created_at INTEGER DEFAULT 0,
                images_today INTEGER DEFAULT 0,
                slides_today INTEGER DEFAULT 0,
                last_action_date TEXT DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS tasks (
                key TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                coins_reward INTEGER NOT NULL,
                icon TEXT DEFAULT 'star',
                repeatable INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS user_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                task_key TEXT NOT NULL,
                completed_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                type TEXT NOT NULL,
                description TEXT,
                created_at INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at INTEGER DEFAULT 0
            );
            """)
            tasks = [
                ("daily_login",    "Kunlik kirish",             "Har kuni platformaga kiring",                    5,  "calendar", 1),
                ("first_chat",     "Birinchi suhbat",           "AI bilan birinchi marta yozishing",             10, "message",  0),
                ("first_image",    "Birinchi rasm",             "Imagine AI da birinchi rasmni yarating",        10, "image",    0),
                ("first_slide",    "Birinchi prezentatsiya",    "Slides AI da ilk slaydni yarating",             10, "layout",   0),
                ("share_app",      "Do'stlarga ulashish",       "Aura AI ni do'stlarga ulashing",                20, "share",    0),
            ]
            for t in tasks:
                conn.execute("INSERT OR IGNORE INTO tasks (key,title,description,coins_reward,icon,repeatable) VALUES (?,?,?,?,?,?)", t)

init_db()

try:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
except ImportError:
    groq_client = None

MODELS = {
    "llama-3.1-8b-instant":    {"name": "⚡ LLaMA 3.1 8B (Tez & Kuchli)", "speed": "ultra", "tier": "free"},
    "llama-3.3-70b-versatile": {"name": "🦙 LLaMA 3.3 70B (Eng Aqlli)",   "speed": "fast",  "tier": "premium"},
}

PLAN_LEVELS = {
    "free":    {"models": ["llama-3.1-8b-instant"], "images": 3, "slides": 2, "history": 10},
    "pro":     {"models": ["llama-3.1-8b-instant"], "images": 20, "slides": 10, "history": 50},
    "premium": {"models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], "images": 50, "slides": 20, "history": 150},
    "ultra":   {"models": ["llama-3.1-8b-instant", "llama-3.3-70b-versatile"], "images": 9999, "slides": 9999, "history": 9999},
}

PLAN_PRICES = {
    "pro":     {"monthly": 50,  "yearly": 400},
    "premium": {"monthly": 100, "yearly": 800},
    "ultra":   {"monthly": 200, "yearly": 1700},
}

SYSTEM_BASE = """Sen Aura AI – O'zbekiston uchun yaratilgan ilg'or sun'iy intellektsan. Seni Nurbek Qulmamatov (6 yillik tajribaga ega Full-Stack & AI dasturchi) yaratgan.

QOIDALAR:

1. SALOMLASHISH: Agar foydalanuvchi salomlashsa yoki hol-ahvol so'rasa, xuddi shunday do'stona javob ber (Masalan: "Salom! Men yaxshiman, o'zingiz yaxshimi? Sizga qanday yordam bera olaman?").

2. TILNI O'ZGARTIRISH (MUHIM): Agar foydalanuvchi boshqa tilda gapirishni so'rasa (masalan: "inglizcha yoz", "write in english"), darhol o'sha tilga o't va o'sha tilda javob ber. O'sha tilda gapirishingni tushuntirish uchun o'zbekcha gaplarni aralashtirma.

3. TO'G'RIDAN-TO'G'RI JAVOB: Oddiy savollarga javob berayotganda gapni keraksiz "Salom", "Xush kelibsiz" kabi kirish so'zlari bilan boshlama. To'g'ri javobga o't.

4. IMLO VA O'ZLIK: O'zbek tilida 100% xatosiz yoz. O'zing haqingda "Men" deb gapir. Javoblaring lo'nda va professional bo'lsin."""

QUIZ_QUESTIONS = [
    {"id": 1, "q": "ChatGPT qaysi kompaniya tomonidan yaratilgan?", "options": ["Google", "OpenAI", "Meta", "Microsoft"], "answer": 1, "coins": 5, "diff": "Oson"},
    {"id": 2, "q": "Sun'iy intellekt atamasini 1956 yilda birinchi bo'lib kim kiritgan?", "options": ["Alan Turing", "John McCarthy", "Elon Musk", "Bill Gates"], "answer": 1, "coins": 15, "diff": "Qiyin"},
    {"id": 3, "q": "GPU qisqartmasining ma'nosi nima?", "options": ["General Processing Unit", "Graphics Processing Unit", "Global Power Unit", "Gaming Processing Unit"], "answer": 1, "coins": 5, "diff": "Oson"},
    {"id": 4, "q": "Qaysi biri dasturlash tili EMAS?", "options": ["Python", "Java", "HTML", "C++"], "answer": 2, "coins": 5, "diff": "Oson"},
    {"id": 5, "q": "Deep Learning bu nimaning bir qismi?", "options": ["Web dasturlash", "Machine Learning", "Kibernetika", "Blockchain"], "answer": 1, "coins": 10, "diff": "O'rta"},
    {"id": 6, "q": "Birinchi dasturchi ayol kim hisoblanadi?", "options": ["Marie Curie", "Ada Lovelace", "Grace Hopper", "Margaret Hamilton"], "answer": 1, "coins": 15, "diff": "Qiyin"},
    {"id": 7, "q": "LLM qisqartmasining ma'nosi nima?", "options": ["Large Logic Model", "Large Language Model", "Long Language Memory", "Lightweight Learning Machine"], "answer": 1, "coins": 10, "diff": "O'rta"},
    {"id": 8, "q": "Dunyodagi eng katta sun'iy neyron tarmoqlaridan biri nima asosida ishlaydi?", "options": ["Transformer", "Microcontroller", "CPU", "HTML"], "answer": 0, "coins": 15, "diff": "Qiyin"},
    {"id": 9, "q": "API qisqartmasi nimani anglatadi?", "options": ["Advanced Programming Interface", "Application Programming Interface", "Automated Process Integration", "Application Process Intel"], "answer": 1, "coins": 10, "diff": "O'rta"},
    {"id": 10, "q": "Ochiq kodli dasturiy ta'minot loyihalari uchun eng katta platforma?", "options": ["GitLab", "Bitbucket", "GitHub", "SourceForge"], "answer": 2, "coins": 5, "diff": "Oson"},
    {"id": 11, "q": "HTML da eng katta sarlavha qaysi teg orqali yoziladi?", "options": ["<head>", "<h6>", "<h1>", "<title>"], "answer": 2, "coins": 5, "diff": "Oson"},
    {"id": 12, "q": "Neyron tarmoqlar (Neural Networks) nima asosida yaratilgan?", "options": ["Hayvonlarning ko'rish qobiliyati", "Inson miyasining ishlash mexanizmi", "Matematik ehtimollar nazariyasi", "Kompyuter grafikasi"], "answer": 1, "coins": 10, "diff": "O'rta"},
    {"id": 13, "q": "Qaysi texnologiya kriptovalyutalarning asosini tashkil etadi?", "options": ["Cloud Computing", "Artificial Intelligence", "Blockchain", "Quantum Computing"], "answer": 2, "coins": 5, "diff": "Oson"},
    {"id": 14, "q": "Python tilini kim yaratgan?", "options": ["Dennis Ritchie", "Guido van Rossum", "James Gosling", "Bjarne Stroustrup"], "answer": 1, "coins": 15, "diff": "Qiyin"},
    {"id": 15, "q": "CSS da orqa fon rangini o'zgartirish xususiyati?", "options": ["color", "background-color", "bg-color", "fill"], "answer": 1, "coins": 5, "diff": "Oson"}
]

def _hash(pw): return hashlib.sha256(pw.encode()).hexdigest()

def get_current_user():
    uid = session.get("user_id")
    if not uid: return None
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user: return None
        # Check subscription expiration
        if user["plan"] != "free" and user["plan_expires_at"] > 0 and time.time() > user["plan_expires_at"]:
            conn.execute("UPDATE users SET plan='free', plan_expires_at=0 WHERE id=?", (uid,))
            user = dict(user)
            user["plan"] = "free"
        
        # Reset daily usage
        today = datetime.now().strftime("%Y-%m-%d")
        if user["last_action_date"] != today:
            conn.execute("UPDATE users SET images_today=0, slides_today=0, last_action_date=? WHERE id=?", (today, uid))
            user = dict(user)
            user["images_today"] = 0
            user["slides_today"] = 0
            
        return dict(user)

def add_coins(user_id, amount, type_, desc=""):
    with get_db() as conn:
        conn.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
        conn.execute("INSERT INTO coin_transactions(user_id,amount,type,description,created_at) VALUES(?,?,?,?,?)",
                     (user_id, amount, type_, desc, int(time.time())))

def add_coins_conn(conn, user_id, amount, type_, desc=""):
    conn.execute("UPDATE users SET coins=coins+? WHERE id=?", (amount, user_id))
    conn.execute("INSERT INTO coin_transactions(user_id,amount,type,description,created_at) VALUES(?,?,?,?,?)",
                 (user_id, amount, type_, desc, int(time.time())))

def check_task(user_id, task_key):
    with get_db() as conn:
        task = conn.execute("SELECT * FROM tasks WHERE key=?", (task_key,)).fetchone()
        if not task: return 0
        
        if task["repeatable"]:
            today = datetime.now().strftime("%Y-%m-%d")
            # Database agnostic date check
            ex_tasks = conn.execute("SELECT completed_at FROM user_tasks WHERE user_id=? AND task_key=?", (user_id, task_key)).fetchall()
            for row in ex_tasks:
                if datetime.fromtimestamp(row["completed_at"]).strftime("%Y-%m-%d") == today:
                    return 0
        else:
            ex = conn.execute("SELECT * FROM user_tasks WHERE user_id=? AND task_key=?", (user_id, task_key)).fetchone()
            if ex: return 0
            
        conn.execute("INSERT INTO user_tasks(user_id,task_key,completed_at) VALUES(?,?,?)", (user_id, task_key, int(time.time())))
        add_coins_conn(conn, user_id, task["coins_reward"], "task", task["title"])
        return task["coins_reward"]

def get_allowed_model(plan, requested_model):
    if requested_model not in MODELS: return "llama-3.1-8b-instant"
    tier = MODELS[requested_model]["tier"]
    plan_levels = {"free":0, "pro":1, "premium":2, "ultra":3}
    if plan_levels.get(plan, 0) >= plan_levels.get(tier, 0):
        return requested_model
    return "llama-3.1-8b-instant"

HTML_PAGES = ["index","ai","about","contact","creator","imagine","plans","login","register","slides","tasks","profile"]

@app.route("/")
def index(): return send_from_directory(".", "index.html")

@app.route("/<page>.html")
def serve_page(page):
    if page in HTML_PAGES: return send_from_directory(".", f"{page}.html")
    return "Sahifa topilmadi", 404

# ── AUTH ──────────────────────────────────────────────────────────────

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    data = request.get_json(force=True) or {}
    name  = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    pw    = (data.get("password") or "").strip()
    if not name or not email or not pw:
        return jsonify({"error": "Barcha maydonlarni to'ldiring"}), 400
    if len(pw) < 6:
        return jsonify({"error": "Parol kamida 6 ta belgidan iborat bo'lishi kerak"}), 400
    try:
        with get_db() as conn:
            conn.execute("INSERT INTO users(name,email,password_hash,coins,plan,created_at) VALUES(?,?,?,0,'free',?)",
                         (name, email, _hash(pw), int(time.time())))
            user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
            session["user_id"] = user["id"]
        return jsonify({"message": "Muvaffaqiyatli ro'yxatdan o'tdingiz!"})
    except Exception as e:
        err_str = str(e).lower()
        if "unique" in err_str or "integrity" in err_str or "duplicate" in err_str:
            return jsonify({"error": "Bu email allaqachon ro'yxatdan o'tgan"}), 409
        raise e

@app.route("/api/auth/login", methods=["POST"])
def api_login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    pw    = (data.get("password") or "").strip()
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE email=? AND password_hash=?", (email, _hash(pw))).fetchone()
        if not user:
            return jsonify({"error": "Email yoki parol noto'g'ri"}), 401
        session["user_id"] = user["id"]
        
    check_task(user["id"], "daily_login") # Check daily login task
    return jsonify({"message": "Muvaffaqiyatli kirdingiz!"})

@app.route("/api/auth/logout", methods=["POST"])
def api_logout():
    session.pop("user_id", None)
    return jsonify({"message": "Chiqdingiz."})

@app.route("/api/auth/me")
def api_me():
    user = get_current_user()
    if not user: return jsonify({"logged_in": False}), 401
    return jsonify({"logged_in": True, "user": {"name": user["name"], "email": user["email"], "plan": user["plan"], "coins": user["coins"]}})

# ── AI CHAT ───────────────────────────────────────────────────────────

@app.route("/api/models")
def api_models():
    user = get_current_user()
    plan = user["plan"] if user else "free"
    plan_levels = {"free":0, "pro":1, "premium":2, "ultra":3}
    user_level = plan_levels.get(plan, 0)
    
    return jsonify({"models": [
        {"id": k, "name": v["name"], "speed": v["speed"], "locked": plan_levels.get(v["tier"],0) > user_level, "tier": v["tier"]} 
        for k, v in MODELS.items()
    ]})

@app.route("/api/chat/history", methods=["GET"])
def api_chat_history():
    user = get_current_user()
    if not user: return jsonify({"history": []})
    limit = PLAN_LEVELS[user["plan"]]["history"]
    with get_db() as conn:
        msgs = conn.execute("SELECT role, content FROM chat_messages WHERE user_id=? ORDER BY created_at ASC", (user["id"],)).fetchall()
        # Ensure we only return the latest `limit` messages
        return jsonify({"history": [{"role": m["role"], "content": m["content"]} for m in msgs][-limit:]})

@app.route("/api/chat/clear", methods=["POST"])
def api_chat_clear():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    with get_db() as conn:
        conn.execute("DELETE FROM chat_messages WHERE user_id=?", (user["id"],))
    return jsonify({"status": "ok"})

@app.route("/api/chat/stream", methods=["POST"])
def api_chat_stream():
    user = get_current_user()
    user_id = user["id"] if user else 0
    plan = user["plan"] if user else "free"
    
    data = request.get_json(force=True) or {}
    user_msg = (data.get("message") or "").strip()
    model_req = data.get("model") or "llama-3.1-8b-instant"
    
    if not user_msg: return jsonify({"error": "Xabar bo'sh"}), 400
    model = get_allowed_model(plan, model_req)
    
    # Save user msg
    if user:
        with get_db() as conn:
            conn.execute("INSERT INTO chat_messages(user_id,role,content,created_at) VALUES(?,?,?,?)", (user_id, "user", user_msg, int(time.time())))
        check_task(user_id, "first_chat")
            
    # Load history
    history_limit = PLAN_LEVELS[plan]["history"]
    messages = [{"role": "system", "content": SYSTEM_BASE}]
    if user:
        with get_db() as conn:
            hist = conn.execute("SELECT role, content FROM chat_messages WHERE user_id=? ORDER BY created_at ASC", (user_id,)).fetchall()
            for h in hist[-history_limit:]:
                messages.append({"role": h["role"], "content": h["content"]})
    else:
        messages.append({"role": "user", "content": user_msg})

    if not groq_client:
        def err():
            yield f"data: {json.dumps({'content':'⚠️ Groq API kaliti topilmadi.'})}\n\n"
            yield "data: [DONE]\n\n"
        return Response(stream_with_context(err()), mimetype="text/event-stream")

    def generate():
        full_text = ""
        try:
            stream = groq_client.chat.completions.create(model=model, messages=messages, temperature=0.7, max_tokens=2048, stream=True)
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta: 
                    full_text += delta
                    yield f"data: {json.dumps({'content': delta})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'content': f'⚠️ Xato: {str(e)}'})}\n\n"
            
        if user and full_text:
            with get_db() as conn:
                conn.execute("INSERT INTO chat_messages(user_id,role,content,created_at) VALUES(?,?,?,?)", (user_id, "assistant", full_text, int(time.time())))
        yield "data: [DONE]\n\n"
        
    return Response(stream_with_context(generate()), mimetype="text/event-stream", headers={"Cache-Control":"no-cache","X-Accel-Buffering":"no"})

# ── IMAGINE & SLIDES ──────────────────────────────────────────────────

@app.route("/api/imagine", methods=["POST"])
def api_imagine():
    user = get_current_user()
    if not user: return jsonify({"error": "Iltimos, tizimga kiring"}), 401
    
    data = request.get_json(force=True) or {}
    prompt = data.get("prompt", "").strip()
    style = data.get("style", "realistic")
    ratio = data.get("ratio", "1:1")
    
    if not prompt: return jsonify({"error": "Rasmni tasvirlang"}), 400
    
    limit = PLAN_LEVELS[user["plan"]]["images"]
    if user["images_today"] >= limit:
        return jsonify({"error": f"Bugungi rasm limiti tugadi ({limit} ta). Tarifingizni oshiring!"}), 403

    # Style-specific quality modifiers
    STYLE_MAP = {
        "realistic":  "photorealistic, ultra-detailed, 8k UHD, sharp focus, cinematic lighting, professional photography",
        "anime":      "anime art style, vibrant colors, detailed linework, Studio Ghibli quality, cel shading",
        "3d":         "3D render, Pixar style, octane render, volumetric lighting, subsurface scattering, ultra-realistic",
        "cyberpunk":  "cyberpunk, neon lights, futuristic cityscape, rain-soaked streets, synthwave aesthetic, cinematic",
        "oil":        "oil painting, impressionist brushstrokes, museum quality, rich textures, dramatic lighting, masterpiece",
        "watercolor": "watercolor painting, soft edges, vibrant washes, artistic, delicate details, paper texture",
        "fantasy":    "epic fantasy art, magical atmosphere, dramatic lighting, highly detailed, concept art, ArtStation",
    }
    style_suffix = STYLE_MAP.get(style, "high quality, detailed")

    # Enhance prompt via Groq
    try:
        sys_p = (
            "You are a professional AI image prompt engineer. "
            "Your job: translate the user's description (which may be in Uzbek or Russian) into English "
            "and enhance it with vivid, specific visual details. "
            "Output ONLY the enhanced English prompt as a single paragraph. "
            "Maximum 80 words. NO quotes, NO markdown, NO introduction."
        )
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": sys_p},
                      {"role": "user", "content": f"Translate and enhance this image description: {prompt}"}],
            max_tokens=120,
            temperature=0.6
        )
        base_prompt = res.choices[0].message.content.strip()
        base_prompt = base_prompt.replace('"', '').replace("'", '').replace('\n', ' ').strip()
    except Exception:
        base_prompt = prompt

    final_prompt = f"{base_prompt}, {style_suffix}"

    # Dimensions
    w, h = 1024, 1024
    if ratio == "16:9":  w, h = 1344, 768
    elif ratio == "9:16": w, h = 768, 1344
    elif ratio == "4:3":  w, h = 1152, 896
    elif ratio == "3:4":  w, h = 896, 1152

    import urllib.parse, random
    seed = random.randint(1, 999999)
    safe_prompt = urllib.parse.quote(final_prompt, safe='')
    img_url = (
        f"https://image.pollinations.ai/prompt/{safe_prompt}"
        f"?width={w}&height={h}&seed={seed}&model=flux&nologo=true&enhance=true"
    )

    with get_db() as conn:
        conn.execute("UPDATE users SET images_today=images_today+1 WHERE id=?", (user["id"],))
    check_task(user["id"], "first_image")

    return jsonify({"url": img_url, "prompt_used": base_prompt, "left": limit - user["images_today"] - 1})

@app.route("/api/slides", methods=["POST"])
def api_slides():
    user = get_current_user()
    if not user: return jsonify({"error": "Iltimos, tizimga kiring"}), 401
    
    data = request.get_json(force=True) or {}
    prompt = data.get("prompt", "").strip()
    count = int(data.get("count", 5))
    lang = data.get("lang", "uz")
    
    if not prompt: return jsonify({"error": "Mavzuni kiriting"}), 400
    
    limit = PLAN_LEVELS[user["plan"]]["slides"]
    if user["slides_today"] >= limit:
        return jsonify({"error": f"Bugungi slayd limiti tugadi ({limit} ta). Tarifingizni oshiring!"}), 403

    # Language label for the prompt
    LANG_MAP = {"uz": "O'zbek", "en": "English", "ru": "Russian"}
    lang_label = LANG_MAP.get(lang, "O'zbek")

    sys_msg = "You are a JSON generator. Output ONLY a valid JSON array. No markdown, no text, no code fences. Start with [ and end with ]."

    user_msg = (
        f'Create exactly {count} presentation slides about: "{prompt}"\n'
        f'Language: {lang_label} — ALL text must be in {lang_label}.\n'
        f'Format: [{{"type":"title","title":"...","subtitle":"..."}},{{"type":"content","title":"...","points":["...","...","..."]}},...]\n'
        f'First slide must be type "title". All others must be type "content" with 3-4 points.\n'
        f'Output ONLY the JSON array starting with [ and ending with ].'
    )

    def try_parse(raw):
        """Try multiple strategies to extract valid JSON array."""
        raw = raw.strip()
        # Remove code fences
        raw = re.sub(r'```(?:json)?\s*', '', raw).strip()
        # Find outermost [ ... ]
        s = raw.find('[')
        e = raw.rfind(']') + 1
        if s >= 0 and e > s:
            raw = raw[s:e]
        return json.loads(raw)

    parsed = None
    last_err = ""

    # First attempt: llama-3.1-8b-instant (Fast and high limits)
    try:
        res = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": sys_msg},
                      {"role": "user", "content": user_msg}],
            temperature=0.1,
            max_tokens=2048
        )
        raw = res.choices[0].message.content
        parsed = try_parse(raw)
    except Exception as e1:
        last_err = str(e1)
        # Fallback: llama-3.1-8b-instant with simpler prompt
        try:
            simple_msg = (
                f'Make {count} slides in {lang_label} about: {prompt}\n'
                f'JSON only: [{{"type":"title","title":"T","subtitle":"S"}},{{"type":"content","title":"T","points":["P1","P2","P3"]}}]'
            )
            res2 = groq_client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "system", "content": sys_msg},
                          {"role": "user", "content": simple_msg}],
                temperature=0.1,
                max_tokens=2048
            )
            raw2 = res2.choices[0].message.content
            parsed = try_parse(raw2)
        except Exception as e2:
            return jsonify({"error": f"Slayd yaratib bo'lmadi. Boshqacha mavzu bilan urinib ko'ring. (Xato 1: {last_err[:40]}... Xato 2: {str(e2)[:40]})"}), 500

    if not parsed or not isinstance(parsed, list) or len(parsed) == 0:
        return jsonify({"error": "AI noto'g'ri javob qaytardi. Boshqacha mavzu bilan urinib ko'ring."}), 500

    # Ensure dict type
    if isinstance(parsed, dict):
        parsed = parsed.get("slides", [parsed])

    # Update usage
    with get_db() as conn:
        conn.execute("UPDATE users SET slides_today=slides_today+1 WHERE id=?", (user["id"],))
    check_task(user["id"], "first_slide")

    return jsonify({"slides": parsed, "left": limit - user["slides_today"] - 1})

# ── COINS & TASKS ─────────────────────────────────────────────────────

@app.route("/api/coins")
def api_coins():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    with get_db() as conn:
        completed = [r["task_key"] for r in conn.execute("SELECT DISTINCT task_key FROM user_tasks WHERE user_id=?", (user["id"],)).fetchall()]
        all_tasks = conn.execute("SELECT * FROM tasks").fetchall()
        txs = conn.execute("SELECT * FROM coin_transactions WHERE user_id=? ORDER BY created_at DESC LIMIT 15", (user["id"],)).fetchall()
        
        # Check daily tasks done today
        today = datetime.now().strftime("%Y-%m-%d")
        daily_done = [r["task_key"] for r in conn.execute("SELECT task_key FROM user_tasks WHERE user_id=? AND date(datetime(completed_at,'unixepoch'))=?", (user["id"], today)).fetchall()]

    tasks_resp = []
    for t in all_tasks:
        done = (t["key"] in daily_done) if t["repeatable"] else (t["key"] in completed)
        tasks_resp.append({
            "key": t["key"], "title": t["title"], "description": t["description"],
            "reward": t["coins_reward"], "icon": t["icon"], "done": done, "repeatable": bool(t["repeatable"])
        })
        
    return jsonify({
        "coins": user["coins"],
        "tasks": tasks_resp,
        "transactions": [{"amount": t["amount"], "desc": t["description"]} for t in txs]
    })

@app.route("/api/tasks/claim", methods=["POST"])
def api_claim_task():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    data = request.get_json(force=True) or {}
    key = data.get("task_key")
    
    # Only some tasks can be manually claimed (like share_app). Others are auto.
    if key == "share_app":
        earned = check_task(user["id"], key)
        if earned > 0: return jsonify({"message": f"{earned} coin berildi!"})
        else: return jsonify({"error": "Allaqachon olingan"}), 400
    
    return jsonify({"error": "Bu vazifa avtomatik bajariladi"}), 400

@app.route("/api/quiz")
def api_quiz():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    
    answered = session.get("answered_quizzes", [])
    
    if len(answered) >= len(QUIZ_QUESTIONS):
        answered = []
        session["answered_quizzes"] = answered

    import random
    available = [q for q in QUIZ_QUESTIONS if q["id"] not in answered]
    random.shuffle(available)
    
    return jsonify({
        "coins": user["coins"],
        "questions": [{"id": q["id"], "q": q["q"], "options": q["options"], "coins": q["coins"], "diff": q["diff"]} for q in available[:10]],
        "answered_count": len(answered),
        "total": "Cheksiz"
    })

@app.route("/api/quiz/answer", methods=["POST"])
def api_quiz_answer():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    
    data = request.get_json(force=True) or {}
    q_id = int(data.get("question_id", 0))
    ans_idx = int(data.get("answer_index", -1))
    
    q = next((x for x in QUIZ_QUESTIONS if x["id"] == q_id), None)
    if not q: return jsonify({"error": "Savol topilmadi"}), 400
    
    answered = session.get("answered_quizzes", [])
    if q_id in answered: return jsonify({"error": "Siz bu savolga javob bergansiz"}), 400
    
    wrong_streak = session.get("wrong_streak", 0)
    
    if ans_idx == q["answer"]:
        answered.append(q_id)
        session["answered_quizzes"] = answered
        session["wrong_streak"] = 0 # reset
        with get_db() as conn:
            add_coins_conn(conn, user["id"], q["coins"], "quiz", "Test: Tog'ri javob")
        return jsonify({"correct": True, "message": f"To'g'ri! +{q['coins']} coin."})
    else:
        wrong_streak += 1
        session["wrong_streak"] = wrong_streak
        penalty_msg = ""
        if wrong_streak >= 3:
            with get_db() as conn:
                add_coins_conn(conn, user["id"], -5, "quiz_penalty", "Test: 3 ta ketma-ket xato")
            session["wrong_streak"] = 0
            penalty_msg = "3 marta xato qildingiz, -5 coin olib tashlandi."
            
        return jsonify({"correct": False, "message": f"Noto'g'ri javob. {penalty_msg}"})

@app.route("/api/plans/subscribe", methods=["POST"])
def api_subscribe():
    user = get_current_user()
    if not user: return jsonify({"error": "Auth required"}), 401
    data = request.get_json(force=True) or {}
    plan = data.get("plan")
    period = data.get("period", "monthly")
    
    if plan not in PLAN_PRICES: return jsonify({"error": "Noto'g'ri tarif"}), 400
    cost = PLAN_PRICES[plan][period]
    if user["coins"] < cost: return jsonify({"error": f"Yetarli coin yo'q. Kerak: {cost}, Sizda: {user['coins']}"}), 400
    
    days = 30 if period == "monthly" else 365
    expires = int(time.time()) + days * 86400
    with get_db() as conn:
        conn.execute("UPDATE users SET plan=?, plan_expires_at=?, coins=coins-? WHERE id=?", (plan, expires, cost, user["id"]))
        conn.execute("INSERT INTO coin_transactions(user_id,amount,type,description,created_at) VALUES(?,?,?,?,?)",
                     (user["id"], -cost, "subscription", f"{plan} ({period})", int(time.time())))
    return jsonify({"message": f"✅ {plan.capitalize()} tarif faollashtirildi! {days} kun amal qiladi."})

# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
