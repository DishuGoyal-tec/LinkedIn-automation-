import os, sys, time, datetime, requests

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
LI_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("AUTHOR_URN")
DRY_RUN = os.environ.get("DRY_RUN") == "1"

# Pehla model busy ho to agla try hoga
GEMINI_MODELS = [
    "gemini-3.8-flash",
    "gemini-flash-latest",
    "gemini-flash-lite-latest",
]

TOPICS = [
    "a practical career guidance tip for freshers",
    "a healthy habit for focus and mental clarity while working",
    "a data analytics lesson explained simply",
    "a lesson from building something from scratch",
    "a common mistake people make while job hunting",
    "how to learn a new skill consistently",
    "a weekend reflection on growth and patience",
]

def tg(text):
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram secrets missing")
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": TG_CHAT, "text": text[:4000]},
        timeout=30,
    )
    print("Telegram status:", r.status_code)

def generate():
    if not GEMINI_KEY:
        print("Gemini key missing")
        return None
    topic = TOPICS[datetime.date.today().weekday()]
    prompt = (
        f"Write a LinkedIn post under 180 words about {topic}. "
        "Start with a strong one-line hook. Short lines with line breaks. "
        "Practical, warm tone. End with one question for readers. "
        "No markdown symbols like ** or #, max 3 hashtags at the end."
    )
    for model in GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
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
                    text = text.replace("**", "").strip()
                    if text:
                        print(f"Used model: {model}")
                        return text
                    print("Empty text returned")
                elif r.status_code in (400, 401, 403):
                    print(r.text[:300])
                    return None  # key ya request ki problem, model badalne se nahi theek hoga
                elif r.status_code == 404:
                    print("Model not found, trying next model")
                    break
                else:
                    print(r.text[:200])
            except Exception as e:
                print(f"[{model}] attempt {attempt} failed:", type(e).__name__)
            time.sleep(5)
    return None

def post_linkedin(text):
    if not LI_TOKEN or not AUTHOR_URN:
        print("LinkedIn secrets missing")
        return False
    r = requests.post(
        "https://api.linkedin.com/v2/ugcPosts",
        headers={
            "Authorization": f"Bearer {LI_TOKEN}",
            "Content-Type": "application/json",
            "X-Restli-Protocol-Version": "2.0.0",
        },
        json={
            "author": AUTHOR_URN,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": text},
                    "shareMediaCategory": "NONE",
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
        },
        timeout=30,
    )
    print("LinkedIn status:", r.status_code, r.text[:300])
    return r.status_code in (200, 201)

if __name__ == "__main__":
    text = generate()
    if not text:
        tg("Gemini failed. Nothing posted today.")
        sys.exit(1)
    tg("New LinkedIn post draft:\n\n" + text)
    if DRY_RUN:
        print("DRY RUN: not posting to LinkedIn")
    elif not post_linkedin(text):
        tg("LinkedIn post FAILED. Check token or URN.")
        sys.exit(1)
