import os, re, sys, json, time, datetime, base64, requests

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
LI_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("AUTHOR_URN")
DRY_RUN = os.environ.get("DRY_RUN") == "1"
# 1 = Telegram updates Cloudflare Worker se aate hain (getUpdates band). 0/khali = purana polling tareeka.
WEBHOOK_MODE = os.environ.get("WEBHOOK_MODE") == "1"

STATE_FILE = "state.json"
TG_API = f"https://api.telegram.org/bot{TG_TOKEN}"
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"

GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

ACTIVE = ("pending", "scheduled", "awaiting_notes", "awaiting_edit", "awaiting_suggest", "awaiting_image")

# Approve dabane par post is time par jayegi (IST). Window: POST_HOUR:00 se 30 min.
POST_HOUR = 11
LATE_LIMIT_HOURS = 3

from content import *

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
    [{"text": "✅ Approve (post 11 AM)", "callback_data": "approve"},
     {"text": "⚡ Post now", "callback_data": "post_now"}],
    [{"text": "✏️ Edit text", "callback_data": "edit"},
     {"text": "💡 Suggest change", "callback_data": "suggest"}],
    [{"text": "🖼 Add my image", "callback_data": "img_own"},
     {"text": "🎨 AI image", "callback_data": "img_ai"}],
    [{"text": "🗑 Remove image", "callback_data": "img_none"},
     {"text": "❌ Skip today", "callback_data": "decline"}],
]}

def send_preview(s):
    if s.get("image_file_id"):
        tg_call("sendPhoto", {"chat_id": TG_CHAT, "photo": s["image_file_id"]})
    words = len(s["text"].split())
    header = f"📝 Draft | {s.get('pillar', '')}\nStyle: {s.get('style', '-')} | {words} words"
    if s.get("used_story"):
        header += " | real story used"
    if s.get("used_project"):
        header += " | real project used"
    if s.get("image_file_id"):
        header += " | 🖼 image attached"
    if s.get("style") == "project" and not s.get("image_file_id"):
        header += "\n📸 Tip: is project ka screenshot lagao (🖼 Add my image)"
    say(f"{header}\n\n{s['text']}", BUTTONS)

def get_updates(offset):
    if WEBHOOK_MODE:
        return []
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
                "Do not write 'I' as if you had personal experience. Opinions such as 'I think' are allowed, "
                "but never claim things happened to the creator.")
    use = ("Build the post around it." if required else
           "Use it in 1 to 3 lines as the opening or as proof, only if it fits naturally; otherwise ignore it.")
    return (f"REAL MOMENT FROM THE CREATOR (true; the only personal facts you may use; "
            f"do not add any detail, number, name or outcome that is not in it; first person is allowed only for this moment). {use}\n"
            f"{story}")

def material_block(style, story, project):
    if style == "project":
        return ("PROJECT FACTS (true, from the creator's own project; these are the ONLY facts you may use; "
                "first person 'I' is allowed because it is the creator's own work; do not add any number, "
                "finding, tool, name or outcome that is not listed here):\n" + project)
    return story_block(story, style == "story")

def build_prompt(pillar, style, angle, lang, story, project, hook, ending):
    hook_rule = "" if style in ("myth", "discussion", "story", "project") else f"HOOK STYLE: {hook}\n"
    angle_line = f"TODAY'S ANGLE: {angle}\n" if (angle and style not in ("project", "story")) else ""
    return f"""You are ghostwriting a LinkedIn post for a creator who gives practical career and data guidance to freshers and small business people in India.

CREATOR FACTS (background only; never expand or embellish them; mention at most one, exactly as written, only if it truly fits):
{PROFILE}

{material_block(style, story, project)}

LANGUAGE: {LANG_RULES[lang]}
{TONE_RULES}

{HUMAN_RULES}

TODAY'S PILLAR: {pillar}
{angle_line}{hook_rule}
{BLUEPRINTS[style]}

{format_rules(ending)}

CONTENT RULES:
- Length: around 130 words (between 110 and 150). Shorter is better than padded.
- Include at least one concrete detail: a number, a named tool, a formula, a query or a real finding.
- Illustrative examples are fine, but introduce them with 'Imagine' or 'Say' and never present them as something that happened to the creator. Do not invent clients, companies, names or results.
- Every sentence should add something. No filler, no repeating the hook.
Output only the post text."""

def quality_pass(text, style, story, project, ending):
    facts_check = ("9) Every number, finding and tool in the post appears in the PROJECT FACTS. Remove anything that does not.\n"
                   if style == "project" else "")
    prompt = f"""You are a strict LinkedIn editor. Check the post below against this checklist:
1) The first line is under 14 words and makes someone want to read on (not a generic question).
2) One idea only.
3) It sounds like a person talking: plain words, varied sentence lengths, no listicle symmetry, no AI-sounding phrases.
4) None of the banned phrases or labels from the HUMAN VOICE rules, and no dashes used as punctuation.
5) Every calculation and number is correct and consistent. Hypothetical numbers are introduced with 'Imagine' or 'Say'.
6) No invented experiences. Personal facts come only from the real material below.
7) It is between 110 and 150 words.
8) The ending follows the ending rule, and the last line is exactly 3 hashtags.
{facts_check}
{HUMAN_RULES}

{format_rules(ending)}

{material_block(style, story, project)}

If every item passes, output the post unchanged. Otherwise rewrite it to fix the failures, keeping the same topic and facts. Output only the post text.

POST:
{text}"""
    return gemini_text(prompt, 90, 180)

def fix_tells(text, style):
    found = find_tells(text, style)
    if not found:
        return text
    prompt = f"""Rewrite this LinkedIn post so it no longer contains these phrases or labels: {', '.join(found)}.
Do not use dashes as punctuation. Keep the meaning, the facts, the length and the layout. Output only the post text.

POST:
{text}"""
    fixed = gemini_text(prompt, 90, 180)
    return fixed or text

def polish_notes(notes, lang):
    prompt = f"""Turn the creator's own notes into a LinkedIn post.

LANGUAGE: {LANG_RULES[lang]}
{TONE_RULES}

{HUMAN_RULES}

{FORMAT_RULES}

CONTENT RULES:
- Use ONLY facts present in the notes. Do not invent details, numbers, names, companies or outcomes.
- First person is allowed because these are the creator's own notes. Fix grammar and make it clear and warm.
- Where possible, add one useful takeaway for the reader, using only what the notes support.
- 90 to 150 words in total.

NOTES:
{notes}

Output only the post text."""
    return gemini_text(prompt, 50, 200)

def revise_text(current, instruction):
    prompt = f"""Edit this LinkedIn post according to the instruction.
Change only what the instruction asks for. Keep the human, conversational voice and the format below.
Do not invent personal stories, numbers or results. Do not use dashes as punctuation.

INSTRUCTION: {instruction}

{FORMAT_RULES}

POST:
{current}

Output only the final post text."""
    return gemini_text(prompt, 40, 250)

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

def next_slot():
    now = datetime.datetime.now(IST)
    slot = now.replace(hour=POST_HOUR, minute=0, second=0, microsecond=0)
    if now < slot:
        return slot
    if now < slot + datetime.timedelta(minutes=30):
        return None  # abhi window ke andar hai, turant post
    return slot + datetime.timedelta(days=1)

def post_failed(s, msg):
    s["fail_count"] = s.get("fail_count", 0) + 1
    if s.get("status") == "scheduled" and s["fail_count"] >= 3:
        s["status"] = "pending"
        s["fail_count"] = 0
        say(msg + "\nSchedule 3 baar fail hua, isliye ruk gaya. Draft pending hai: Approve ya ⚡ Post now dabao.")
    else:
        say(msg)

def do_post(s):
    if DRY_RUN:
        if s.get("status") == "scheduled":
            s["status"] = "pending"
        say("🧪 DRY RUN on hai, isliye LinkedIn par post nahi hui. Buttons ka flow test kar sakti ho.")
        return
    if not LI_TOKEN or not AUTHOR_URN:
        post_failed(s, "LinkedIn token ya URN secret missing hai.")
        return
    asset = None
    if s.get("image_file_id"):
        img = download_telegram_file(s["image_file_id"])
        asset = li_upload_image(img) if img else None
        if not asset:
            post_failed(s, "Image upload fail hua. 🗑 Remove image dabake dobara Approve karo, ya doosri image try karo.")
            return
    ok, code = post_linkedin(s["text"], asset)
    if ok:
        s["status"] = "posted"
        s["fail_count"] = 0
        say("✅ Post LinkedIn par live ho gayi.")
    else:
        post_failed(s, f"LinkedIn post fail hui (code {code}). Draft safe hai. 401 ho to token expire hua hai.")

def handle_callback(s, cq):
    if not from_me(cq.get("message", {}).get("chat", {}).get("id")):
        return
    tg_call("answerCallbackQuery", {"callback_query_id": cq["id"]})
    data = cq.get("data")
    if s.get("status") not in ACTIVE:
        say("Ye draft ab active nahi hai. Agla draft kal shaam ko aayega.")
        return
    if s["status"] == "scheduled":
        if data == "decline":
            s["status"] = "declined"
            say("Theek hai, schedule cancel. Post nahi jayegi.")
        elif data == "post_now":
            do_post(s)
        else:
            say("⏰ Post pehle se scheduled hai. Cancel karna ho to ❌ Skip today dabao, ya ⚡ Post now se abhi post karo.")
        return
    if s["status"] == "awaiting_notes":
        say("Pehle apne notes ek message mein bhejo.")
        return
    if data == "approve":
        slot = next_slot()
        if slot is None:
            do_post(s)
        else:
            s["status"] = "scheduled"
            s["publish_at"] = slot.isoformat()
            s["fail_count"] = 0
            say(f"⏰ Scheduled: {slot.strftime('%a %d %b, %I:%M %p')} IST "
                f"({POST_HOUR}:00 ke baad ~30 min ke andar post hogi). "
                "Cancel karna ho to ❌ Skip today dabao.")
    elif data == "post_now":
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
    if s.get("status") == "scheduled":
        say("⏸ Pichli post abhi scheduled hai, isliye nayi draft nahi bana rahi. "
            "Pehle use post ya ❌ Skip karo.")
        return
    if not WEBHOOK_MODE and not s.get("offset"):
        res = get_updates(-1)
        if res:
            s["offset"] = res[-1]["update_id"] + 1
    now = datetime.datetime.now(IST)
    weekday = int(os.environ.get("TEST_WEEKDAY") or now.weekday())
    pillar, lang, styles, tags, angles = PILLARS[weekday]
    week = now.isocalendar()[1]
    style = styles[week % len(styles)]
    angle = angles[week % len(angles)] if angles else ""
    ordinal = now.toordinal()
    hook = HOOKS[ordinal % len(HOOKS)]
    ending = "question" if style == "discussion" else ENDING_ROTATION[(ordinal + 1) % len(ENDING_ROTATION)]
    s.update({"date": now.strftime("%Y-%m-%d"), "pillar": pillar, "angle": angle,
              "lang": lang, "style": style, "text": "", "image_file_id": None,
              "used_story": False, "used_project": False})
    if style == "notes":
        s["status"] = "awaiting_notes"
        save_state(s)
        say("🗓 Aaj Saturday hai, personal update ka din.\n\n"
            "Job search ya portfolio ka kya update hai? 3-5 lines mein notes bhejo "
            "(Hinglish chalega). Main unhe sirf polish karungi, kuch nayi cheez nahi jodungi.")
        return
    story = None
    project = None
    if style == "story":
        story = pick_story(tags, s)
        if not story:
            style = "opinion"
    elif style == "mistake":
        story = pick_story(["mistake"], s)
    elif style == "project":
        project = pick_project(s)
        if not project:
            style = "opinion"
    if style in ("opinion", "tutorial", "mistake", "myth") and not angle:
        angle = "one thing freshers get wrong about data jobs"
    s["style"] = style
    s["used_story"] = bool(story)
    s["used_project"] = bool(project)
    text = gemini_text(build_prompt(pillar, style, angle, lang, story, project, hook, ending), 90, 180)
    if text:
        text = quality_pass(text, style, story, project, ending) or text
        text = fix_tells(text, style)
    if not text:
        s["status"] = "idle"
        save_state(s)
        say("Gemini failed. Aaj ka draft nahi ban paya.")
        sys.exit(1)
    s["text"], s["status"] = text, "pending"
    save_state(s)
    send_preview(s)

def cmd_handle():
    raw = os.environ.get("UPDATE_JSON", "")
    try:
        u = json.loads(raw)
    except Exception:
        print("No valid update received")
        return
    if not isinstance(u, dict):
        print("Update is not an object")
        return
    s = load_state()
    uid = u.get("update_id") or 0
    if uid and uid <= s.get("last_update_id", 0):
        print("Duplicate update, skipping")
        return
    if uid:
        s["last_update_id"] = uid
    if "callback_query" in u:
        handle_callback(s, u["callback_query"])
    elif "message" in u:
        handle_message(s, u["message"])
    save_state(s)

def cmd_poll():
    s = load_state()
    if s.get("status") not in ACTIVE:
        print("Nothing pending")
        return
    updates = [] if WEBHOOK_MODE else get_updates(s.get("offset", 0))
    for u in updates:
        s["offset"] = u["update_id"] + 1
        if "callback_query" in u:
            handle_callback(s, u["callback_query"])
        elif "message" in u:
            handle_message(s, u["message"])
        save_state(s)
    if s.get("status") == "scheduled":
        try:
            due = datetime.datetime.fromisoformat(s["publish_at"])
        except Exception:
            due = None
        now = datetime.datetime.now(IST)
        if due and now >= due:
            if now > due + datetime.timedelta(hours=LATE_LIMIT_HOURS):
                s["status"] = "pending"
                say("⚠️ Scheduled time nikal gaya (GitHub late chala), isliye post nahi ki. "
                    "Approve (agla slot) ya ⚡ Post now dabao.")
            else:
                do_post(s)
    save_state(s)

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "generate":
        cmd_generate()
    elif mode == "poll":
        cmd_poll()
    elif mode == "handle":
        cmd_handle()
    else:
        print("Usage: python script.py generate|poll|handle")
