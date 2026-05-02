# 🤖 Aura AI — O'zbekiston's #1 AI Platform

> O'zbek tilidagi sun'iy intellekt platformasi: Chat, Rasm yaratish, Prezentatsiya va Coin tizimi.

**Muallif:** Nurbek Qulmamatov

---

## ✨ Imkoniyatlar

- 💬 **AI Chat** — LLaMA 3.3 70B modeli orqali real-time streaming
- 🎨 **Imagine AI** — Matndan HD rasm yaratish (Pollinations Flux)
- 📊 **Slides AI** — Avtomatik prezentatsiya yaratish (O'zbek/Ingliz/Rus)
- 🪙 **Coin tizimi** — Vazifalar bajarib coin yig'ish, obuna sotib olish
- 🎮 **Quiz** — AI savollari orqali coin ishlash
- 👤 **Auth** — Ro'yxatdan o'tish, kirish, profil

## 🛠 Tech Stack

- **Backend:** Python + Flask
- **AI:** Groq API (LLaMA 3.3-70B, LLaMA 3.1-8B)
- **Images:** Pollinations.ai (Flux model)
- **DB:** SQLite
- **Frontend:** Vanilla HTML + CSS + JS
- **Deploy:** Vercel

## 🚀 Local da ishga tushirish

```bash
# 1. Klonlash
git clone https://github.com/YOUR_USERNAME/aura-ai.git
cd aura-ai

# 2. Virtual muhit
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # Mac/Linux

# 3. Kutubxonalar
pip install -r requirements.txt

# 4. .env fayl yaratish
# .env.example ni nusxalab .env ga o'zgartiring
cp .env.example .env
# GROQ_API_KEY ni to'ldiring: https://console.groq.com

# 5. Ishga tushirish
python app.py
```

Brauzerda oching: `http://localhost:5000`

## 🌐 Vercel ga deploy qilish

1. [vercel.com](https://vercel.com) ga kiring
2. **New Project** → GitHub repo ni tanlang
3. **Environment Variables** qo'shing:
   - `GROQ_API_KEY` = sizning Groq API kalitingiz
   - `SECRET_KEY` = kuchli maxfiy kalit (masalan: `openssl rand -hex 32`)
4. **Deploy** bosing

> ⚠️ SQLite Vercel serverless da ishlamaydi (stateless). Production uchun [Supabase](https://supabase.com) yoki [PlanetScale](https://planetscale.com) ga o'tishni tavsiya etamiz.

## 📁 Fayl strukturasi

```
aura-ai/
├── app.py              # Flask backend
├── requirements.txt    # Python kutubxonalar
├── vercel.json         # Vercel konfiguratsiya
├── .env                # Muhit o'zgaruvchilari (gitga kirmaydi)
├── .env.example        # Namuna env fayl
├── index.html          # Bosh sahifa
├── ai.html             # AI Chat
├── imagine.html        # Rasm yaratish
├── slides.html         # Prezentatsiya
├── plans.html          # Tariflar
├── tasks.html          # Vazifalar
├── profile.html        # Profil
├── login.html          # Kirish
├── register.html       # Ro'yxat
├── about.html          # Haqida
├── contact.html        # Aloqa
└── creator.html        # Muallif
```

## 📜 Litsenziya

MIT © 2025 Nurbek Qulmamatov
