import os, re, sys, json, time, datetime, base64, requests

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
LI_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("AUTHOR_URN")
DRY_RUN = os.environ.get("DRY_RUN") == "1"

STATE_FILE = "state.json"
STORIES_FILE = "stories.txt"
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

ACTIVE = ("pending", "awaiting_notes", "awaiting_edit", "awaiting_suggest", "awaiting_image")

# Sirf wahi facts likho jo sach hain.
PROFILE = """
- Data analyst by background (BBA plus a Post Graduate Program in Data Science and ML).
- Was the first dedicated data hire at an F&B chain with 25+ outlets and built its reporting from scratch, mostly in Google Sheets.
- Earlier worked in a finance and reporting role.
- Works with SQL and Google Sheets. Not a pure techie, believes business thinking matters more than tools.
- Now shares practical guidance for freshers aiming for Data Analyst and Business Analyst roles.
"""

LANG_RULES = {
    "en": "Write in clear, professional English. Simple words, short sentences.",
    "mix": ("Write in clear, professional English as the base. You may add at most one or two short, "
            "natural Hindi phrases in Roman script (for example in the closing line), only where it feels warm. "
            "Never write full Hindi sentences, never use slang or casual fillers like 'yaar' or 'bhai'."),
}

# weekday: (pillar, language, style, story tags, angles)   0 = Monday ... 6 = Sunday
PILLARS = {
    0: ("Business Analyst career guidance for freshers from non-tech backgrounds", "en", "tutorial",
        ["career", "job", "general"], [
        "what a Business Analyst actually does in a normal work day",
        "how to read a Data/Business Analyst job description and spot what really matters",
        "the first 3 skills to learn for a BA role, in order",
        "how to turn a college or course project into a strong resume line",
    ]),
    1: ("Practical tool tip (Google Sheets, Excel, SQL)", "en", "tutorial",
        ["tool", "sql", "mistake", "general"], [
        "one Google Sheets formula that saves time, with a tiny worked example",
        "a beginner SQL pattern (like GROUP BY) explained with a small example table",
        "a common data cleaning mistake and how to fix it step by step",
        "one habit that makes a report easy for a manager to read",
    ]),
    2: ("F&B plus data: lessons from business reporting", "en", "story",
        ["fnb", "mistake", "general"], [
        "why daily sales numbers mislead without context",
        "what a small cafe or restaurant should track every day",
        "why a simple report beats a fancy dashboard",
        "how messy data teaches you to ask better questions",
    ]),
    3: ("Job hunt reality for freshers", "mix", "story",
        ["job", "mistake", "career", "general"], [
        "how to follow up politely after applying",
        "what to do when applications get no replies",
        "how to prepare for a business case question in a BA interview",
        "how to explain a career switch honestly in an interview",
    ]),
    4: ("Myth vs reality in data and analyst careers", "mix", "myth",
        ["career", "job", "mistake", "general"], [
        "myth: you must be a coding expert to become a Business Analyst",
        "myth: only an MBA or a top college gets you a good analyst job",
        "myth: more certificates means more job offers",
        "myth: you need a perfect resume to start applying",
    ]),
    5: ("Personal update: job search and portfolio", "mix", "notes", [], []),
    6: ("Weekend discussion", "mix", "discussion",
        ["career", "job", "general"], [
        "ask the community what helped them most in their career this year",
        "ask which skill people are learning right now and why",
        "ask what advice they wish they got as a fresher",
        "ask what they would tell their younger self about work",
    ]),
}

BLUEPRINTS = {
    "tutorial": """STYLE: Mini tutorial. Build the post in this order:
- Hook: the problem or a specific scenario in one line.
- A concrete scenario with specific details (for example a cafe's daily sales, a small table, a job application).
- A named formula, function or method that solves it (for example Sales = customers x average bill, a Sheets function, GROUP BY), with a tiny worked example using concrete numbers.
- 3 short numbered steps the reader can follow.
- One common mistake to avoid.
- A line starting with "Try this today:" giving one small 10-minute exercise.
- A closing question.""",
    "story": """STYLE: Story plus lesson. Build the post in this order:
- Hook taken from the real moment.
- Tell the real moment in 3 to 4 plain sentences: the situation, what was done, what happened. Use ONLY what is in the real moment.
- The lesson as 2 or 3 numbered takeaways the reader can apply, each with a concrete detail.
- A line starting with "Try this today:" giving one small action.
- A closing question.""",
    "myth": """STYLE: Myth-busting with an example. Build the post in this order:
- Hook starting with "Myth:" and the myth.
- One line starting with "Reality:".
- A concrete example or mini-scenario that proves it, with numbers, named tools or a named method.
- What to do instead as 3 short numbered steps.
- A line starting with "Try this today:" giving one small action.
- A closing question.""",
    "discussion": """STYLE: Insight plus discussion. Build the post in this order:
- Hook: a specific observation or question.
- One useful insight in 3 to 4 lines, with a concrete example.
- 2 or 3 numbered options or prompts the readers can answer with.
- A closing question that is easy to answer in one line.""",
}

FORMAT_RULES = """FORMAT (plain text only):
- Line 1 is the hook, under 14 words.
- Blank line between every block. Each paragraph is at most 2 short lines.
- Numbered steps: each on its own line as 1) 2) 3), with a blank line before the list.
- Labels like "Example:", "Reality:" or "Try this today:" start their own line.
- The second last block is one genuine question for readers.
- The last line is exactly 3 relevant hashtags.
- No markdown: no asterisks, no headings, no bullet symbols."""

TONE_RULES = """TONE: a thoughtful working professional sharing something useful. Calm, specific, respectful. Not an influencer.
Avoid phrases like: game-changer, brutal truth, let that sink in, unlock, dive deep, in today's fast-paced world.
No emojis."""

# ---------------- formatting helper ----------------

def format_post(text):
    text = text.replace("\r\n", "\n").replace("**", "").replace("__", "")
    text = re.sub(r"^\s*[\*\-•]\s+", "", text, flags=re.M)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"(?<=\S)[ \t]+(?=\d\) )", "\n", text)
    text = re.sub(r"([^\n])\n(1\) )", r"\1\n\n\2", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    parts = text.rsplit("\n", 1)
    if len(parts) == 2 and parts[1].lstrip().startswith("#") and not parts[0].endswith("\n"):
        text = parts[0].rstrip() + "\n\n" + parts[1].strip()
    return text

# ---------------- stories ----------------

def load_stories():
    stories = []
    try:
        with open(STORIES_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "|" not in line:
                    continue
                tag, story = line.split("|", 1)
                tag, story = tag.strip().lower(), story.strip()
                if len(story) >= 15:
                    stories.append((tag, story))
    except FileNotFoundError:
        print("stories.txt not found, continuing without stories")
    return stories

def pick_story(tags, s):
    if not tags:
        return None
    pool = [(t, x) for t, x in load_stories() if t in tags]
    if not pool:
        return None
    used = s.setdefault("used_stories", [])
    unused = [(t, x) for t, x in pool if x[:50] not in used]
    if not unused:
        pool_keys = [x[:50] for _, x in pool]
        s["used_stories"] = [k for k in used if k not in pool_keys]
        unused = pool
    story = unused[0][1]
    s["used_stories"].append(story[:50])
    return story

# ---------------- state ----------------

def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except Exception:
        return {"offset": 0, "status": "idle"}

def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=1, ensure_ascii=False)

# ---------------- telegram ----------------

def tg_call(method, payload=None, files=None):
    try:
        if files:
            r = requests.post(f"{TG_API}/{method}", data=payload, files=files, timeout=60)
        else:
            r = requests.post(f"{TG_API}/{method}", json=payload or {}, timeout=30)
        data = r.json()
        if not data.get("ok"):
            print(f"Telegram {method} error:", str(data)[:200])
        return data
    except Exception as e:
        print(f"Telegram {method} failed:", type(e).__name__)
        return {"ok": False}

def say(text, markup=None):
    payload = {"chat_id": TG_CHAT, "text": text[:4000]}
    if markup:
        payload["reply_markup"] = markup
    return tg_call("sendMessage", payload)

BUTTONS = {"inline_keyboard": [
    [{"text": "✅ Approve & Post", "callback_data": "approve"},
     {"text": "❌ Skip today", "callback_data": "decline"}],
    [{"text": "✏️ Edit text", "callback_data": "edit"},
     {"text": "💡 Suggest change", "callback_data": "suggest"}],
    [{"text": "🖼 Add my image", "callback_data": "img_own"},
     {"text": "🎨 AI image", "callback_data": "img_ai"}],
    [{"text": "🗑 Remove image", "callback_data": "img_none"}],
]}

def send_preview(s):
    if s.get("image_file_id"):
        tg_call("sendPhoto", {"chat_id": TG_CHAT, "photo": s["image_file_id"]})
    words = len(s["text"].split())
    header = f"📝 Draft | {s.get('pillar', '')}\nStyle: {s.get('style', '-')} | {words} words"
    if s.get("used_story"):
        header += " | real story used"
    if s.get("image_file_id"):
        header += " | 🖼 image attached"
    say(f"{header}\n\n{s['text']}", BUTTONS)

def get_updates(offset):
    body = {"offset": offset, "timeout": 0, "allowed_updates": ["message", "callback_query"]}
    d = tg_call("getUpdates", body)
    if d.get("error_code") == 409:
        print("Webhook active, removing it")
        tg_call("deleteWebhook", {"drop_pending_updates": False})
        d = tg_call("getUpdates", body)
    return d.get("result") or []

def from_me(chat_id):
    return str(chat_id) == str(TG_CHAT)

def download_telegram_file(file_id):
    d = tg_call("getFile", {"file_id": file_id})
    try:
        path = d["result"]["file_path"]
        r = requests.get(f"https://api.telegram.org/file/bot{TG_TOKEN}/{path}", timeout=60)
        if r.status_code == 200:
            return r.content
    except Exception as e:
        print("Telegram download failed:", type(e).__name__)
    return None

# ---------------- gemini text ----------------

def gemini_text(prompt, min_words=150, max_words=260):
    if not GEMINI_KEY:
        print("Gemini key missing")
        return None
    for model in GEMINI_MODELS:
        url = f"{GEMINI_BASE}/models/{model}:generateContent"
        for attempt in range(1, 3):
            try:
                r = requests.post(
                    url,
                    headers={"x-goog-api-key": GEMINI_KEY},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=60,
                )
                print(f"[{model}] attempt {attempt} status:", r.status_code)
                if r.status_code == 200:
                    text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = format_post(text)
                    words = len(text.split())
                    if min_words <= words <= max_words:
                        print(f"Used model: {model}, words: {words}")
                        return text
                    print(f"Bad length ({words} words), retrying")
                elif r.status_code in (400, 401, 403):
                    print(r.text[:300])
                    return None
                elif r.status_code == 404:
                    print("Model not found, trying next model")
                    break
                else:
                    print(r.text[:200])
            except Exception as e:
                print(f"[{model}] attempt {attempt} failed:", type(e).__name__)
            time.sleep(5)
    return None

def story_block(story, required):
    if not story:
        return ("No real moment is provided. Speak to the reader as 'you'. "
                "Do not write 'I' anywhere and do not claim any personal experience.")
    use = ("Build the post around it." if required else
           "Use it in 1 to 3 lines as the opening or as proof, only if it fits naturally; otherwise ignore it.")
    return (f"REAL MOMENT FROM THE CREATOR (true; the only personal facts you may use; "
            f"do not add any detail, number, name or outcome that is not in it; first person is allowed only for this moment). {use}\n"
            f"{story}")

def build_prompt(pillar, style, angle, lang, story):
    return f"""You are ghostwriting a LinkedIn post for a creator who gives practical career and data guidance to freshers and small business people in India.

CREATOR FACTS (background only; never expand or embellish them; mention at most one, exactly as written, only if it truly fits):
{PROFILE}

{story_block(story, style == "story")}

LANGUAGE: {LANG_RULES[lang]}
{TONE_RULES}

TODAY'S PILLAR: {pillar}
TODAY'S ANGLE: {angle}

{BLUEPRINTS[style]}

{FORMAT_RULES}

CONTENT RULES:
- Length: around 200 words (between 170 and 230).
- The post must be genuinely useful: include at least one concrete example with specific numbers, a named formula, function, query or tool. No generic advice like "stay consistent" or "believe in yourself" unless made concrete.
- Illustrative examples are fine, but label them "Example:" and never present them as something that happened to the creator. Do not invent clients, companies, names or results.
- Every sentence should add information. No filler, no repeating the hook.
Output only the post text."""

def quality_pass(text, style, story):
    needs_try = style in ("tutorial", "story", "myth")
    prompt = f"""You are a strict LinkedIn editor. Check the post below against this checklist:
1) The hook is specific and under 14 words.
2) It has at least one concrete example, formula, function or tool with specifics (numbers, names).
3) It has numbered steps or points, each on its own line.
4) {"It has a line starting with 'Try this today:' with one small action." if needs_try else "It ends with an easy-to-answer question."}
5) It is between 170 and 230 words.
6) No generic advice, no cliches, no invented claims, no personal experience claims beyond the real moment.
7) It follows the format rules.

{FORMAT_RULES}

{story_block(story, style == "story")}

If every item passes, output the post unchanged. Otherwise rewrite it to fix the failures, keeping the same topic and facts. Output only the post text.

POST:
{text}"""
    return gemini_text(prompt, 150, 260)

def polish_notes(notes, lang):
    prompt = f"""Turn the creator's own notes into a LinkedIn post.

LANGUAGE: {LANG_RULES[lang]}
{TONE_RULES}

{FORMAT_RULES}

CONTENT RULES:
- Use ONLY facts present in the notes. Do not invent details, numbers, names, companies or outcomes.
- First person is allowed because these are the creator's own notes. Fix grammar and make it clear.
- Where possible, turn the notes into one useful takeaway for the reader, using only what the notes support.
- 120 to 200 words in total.

NOTES:
{notes}

Output only the post text."""
    return gemini_text(prompt, 60, 240)

def revise_text(current, instruction):
    prompt = f"""Edit this LinkedIn post according to the instruction.
Keep it professional, keep the same language style, and keep the format below.
Do not invent personal stories, numbers or results. Keep it concrete and useful.

INSTRUCTION: {instruction}

{FORMAT_RULES}

POST:
{current}

Output only the final post text."""
    return gemini_text(prompt, 40, 300)

# ---------------- gemini image (optional) ----------------

def image_models():
    try:
        r = requests.get(f"{GEMINI_BASE}/models?pageSize=1000",
                         headers={"x-goog-api-key": GEMINI_KEY}, timeout=30)
        names = []
        for m in r.json().get("models", []):
            n = m.get("name", "").replace("models/", "")
            if "image" in n and "imagen" not in n and "generateContent" in m.get("supportedGenerationMethods", []):
                names.append(n)
        print("Image models found:", names)
        return names
    except Exception as e:
        print("Image model lookup failed:", type(e).__name__)
        return []

def gen_image(text):
    prompt = ("Create a clean, modern, minimal illustration for a LinkedIn post. "
              "No text, no letters, no logos, no real people. Soft colors, flat design, landscape. "
              "Theme: " + text[:300].replace("\n", " "))
    for model in image_models()[:3]:
        try:
            r = requests.post(
                f"{GEMINI_BASE}/models/{model}:generateContent",
                headers={"x-goog-api-key": GEMINI_KEY},
                json={"contents": [{"parts": [{"text": prompt}]}],
                      "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]}},
                timeout=90,
            )
            print(f"[image {model}] status:", r.status_code)
            if r.status_code == 200:
                for part in r.json()["candidates"][0]["content"]["parts"]:
                    inline = part.get("inlineData") or part.get("inline_data")
                    if inline and inline.get("data"):
                        return base64.b64decode(inline["data"])
            else:
                print(r.text[:200])
        except Exception as e:
            print(f"[image {model}] failed:", type(e).__name__)
    return None

# ---------------- linkedin ----------------

def li_headers():
    return {
        "Authorization": f"Bearer {LI_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0",
    }

def li_upload_image(img_bytes):
    body = {"registerUploadRequest": {
        "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
        "owner": AUTHOR_URN,
        "serviceRelationships": [{"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}],
    }}
    r = requests.post("https://api.linkedin.com/v2/assets?action=registerUpload",
                      headers=li_headers(), json=body, timeout=30)
    print("LinkedIn registerUpload status:", r.status_code)
    if r.status_code not in (200, 201):
        print(r.text[:300])
        return None
    v = r.json()["value"]
    upload_url = v["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
    asset = v["asset"]
    u = requests.put(upload_url, headers={"Authorization": f"Bearer {LI_TOKEN}"}, data=img_bytes, timeout=90)
    print("LinkedIn image upload status:", u.status_code)
    if u.status_code not in (200, 201):
        return None
    return asset

def post_linkedin(text, asset=None):
    content = {"shareCommentary": {"text": text}, "shareMediaCategory": "NONE"}
    if asset:
        content["shareMediaCategory"] = "IMAGE"
        content["media"] = [{"status": "READY", "media": asset}]
    body = {
        "author": AUTHOR_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }
    r = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=li_headers(), json=body, timeout=30)
    print("LinkedIn post status:", r.status_code, r.text[:300])
    return r.status_code in (200, 201), r.status_code

# ---------------- actions ----------------

def do_post(s):
    if DRY_RUN:
        say("🧪 DRY RUN on hai, isliye LinkedIn par post nahi hui. Buttons ka flow test kar sakti ho.")
        return
    if not LI_TOKEN or not AUTHOR_URN:
        say("LinkedIn token ya URN secret missing hai.")
        return
    asset = None
    if s.get("image_file_id"):
        img = download_telegram_file(s["image_file_id"])
        asset = li_upload_image(img) if img else None
        if not asset:
            say("Image upload fail hua. 🗑 Remove image dabake dobara Approve karo, ya doosri image try karo.")
            return
    ok, code = post_linkedin(s["text"], asset)
    if ok:
        s["status"] = "posted"
        say("✅ Post LinkedIn par live ho gayi.")
    else:
        say(f"LinkedIn post fail hui (code {code}). Draft safe hai, dobara Approve kar sakti ho. 401 ho to token expire hua hai.")

def handle_callback(s, cq):
    if not from_me(cq.get("message", {}).get("chat", {}).get("id")):
        return
    tg_call("answerCallbackQuery", {"callback_query_id": cq["id"]})
    data = cq.get("data")
    if s.get("status") not in ACTIVE:
        say("Ye draft ab active nahi hai. Agla draft kal shaam ko aayega.")
        return
    if s["status"] == "awaiting_notes":
        say("Pehle apne notes ek message mein bhejo.")
        return
    if data == "approve":
        do_post(s)
    elif data == "decline":
        s["status"] = "declined"
        say("Theek hai, aaj ki post skip. Kal milte hain.")
    elif data == "edit":
        s["status"] = "awaiting_edit"
        say("✏️ Apna final text ek message mein bhejo. Main wahi use karungi.")
    elif data == "suggest":
        s["status"] = "awaiting_suggest"
        say("💡 Kya change chahiye? Jaise: chhota karo, F&B example daalo, tone halka karo.")
    elif data == "img_own":
        s["status"] = "awaiting_image"
        say("🖼 Image ko Photo ki tarah bhejo (File ki tarah nahi).")
    elif data == "img_ai":
        say("🎨 AI image bana rahi hu, 1 min lagega...")
        img = gen_image(s["text"])
        if not img:
            say("AI image nahi ban payi (free key par ye kabhi kabhi nahi chalta). Apni image bhej sakti ho: 🖼 Add my image.")
            return
        d = tg_call("sendPhoto", {"chat_id": TG_CHAT}, files={"photo": ("image.png", img)})
        try:
            s["image_file_id"] = d["result"]["photo"][-1]["file_id"]
        except Exception:
            say("Image mili par Telegram par save nahi ho payi.")
            return
        send_preview(s)
    elif data == "img_none":
        s["image_file_id"] = None
        send_preview(s)

def handle_message(s, m):
    if not from_me(m.get("chat", {}).get("id")):
        return
    status = s.get("status")
    text = (m.get("text") or "").strip()
    if text.startswith("/"):
        return
    if status == "awaiting_notes" and text:
        say("Notes mil gaye, post bana rahi hu...")
        new = polish_notes(text, s.get("lang", "mix") if s.get("lang") in LANG_RULES else "mix")
        if not new:
            say("Post nahi ban payi. Notes dobara bhejo.")
            return
        s["text"], s["status"] = new, "pending"
        send_preview(s)
    elif status == "awaiting_edit" and text:
        if len(text) > 3000:
            say("Text 3000 characters se chhota rakho (LinkedIn ki limit).")
            return
        s["text"], s["status"] = text, "pending"
        send_preview(s)
    elif status == "awaiting_suggest" and text:
        say("Badal rahi hu...")
        new = revise_text(s["text"], text)
        if not new:
            say("Change nahi ho paya. Dobara suggestion bhejo.")
            return
        s["text"], s["status"] = new, "pending"
        send_preview(s)
    elif status == "awaiting_image":
        if m.get("photo"):
            s["image_file_id"] = m["photo"][-1]["file_id"]
            s["status"] = "pending"
            send_preview(s)
        else:
            say("Image ko Photo ki tarah bhejo (gallery se, File ki tarah nahi).")
    elif status == "pending" and text:
        say("Neeche ke buttons use karo, ya Edit / Suggest change dabao.")

# ---------------- commands ----------------

def cmd_generate():
    s = load_state()
    if not s.get("offset"):
        res = get_updates(-1)
        if res:
            s["offset"] = res[-1]["update_id"] + 1
    now = datetime.datetime.now(IST)
    weekday = int(os.environ.get("TEST_WEEKDAY") or now.weekday())
    pillar, lang, style, tags, angles = PILLARS[weekday]
    angle = angles[now.isocalendar()[1] % len(angles)] if angles else ""
    s.update({"date": now.strftime("%Y-%m-%d"), "pillar": pillar, "angle": angle,
              "lang": lang, "style": style, "text": "", "image_file_id": None, "used_story": False})
    if style == "notes":
        s["status"] = "awaiting_notes"
        save_state(s)
        say("🗓 Aaj Saturday hai, personal update ka din.\n\n"
            "Job search ya portfolio ka kya update hai? 3-5 lines mein notes bhejo "
            "(Hinglish chalega). Main unhe sirf polish karungi, kuch nayi cheez nahi jodungi.")
        return
    story = pick_story(tags, s)
    if style == "story" and not story:
        style = "tutorial"
        s["style"] = style
    s["used_story"] = bool(story)
    text = gemini_text(build_prompt(pillar, style, angle, lang, story))
    if text:
        improved = quality_pass(text, style, story)
        text = improved or text
    if not text:
        s["status"] = "idle"
        save_state(s)
        say("Gemini failed. Aaj ka draft nahi ban paya.")
        sys.exit(1)
    s["text"], s["status"] = text, "pending"
    save_state(s)
    send_preview(s)

def cmd_poll():
    s = load_state()
    if s.get("status") not in ACTIVE:
        print("Nothing pending")
        return
    for u in get_updates(s.get("offset", 0)):
        s["offset"] = u["update_id"] + 1
        if "callback_query" in u:
            handle_callback(s, u["callback_query"])
        elif "message" in u:
            handle_message(s, u["message"])
        save_state(s)
    save_state(s)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "generate":
        cmd_generate()
    elif mode == "poll":
        cmd_poll()
    else:
        print("Usage: python script.py generate|poll")
