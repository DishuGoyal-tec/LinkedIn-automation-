import os
import requests

# Load environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LINKEDIN_ACCESS_TOKEN = os.environ.get("LINKEDIN_ACCESS_TOKEN")
AUTHOR_URN = os.environ.get("AUTHOR_URN")

# Debugging: Print status of environment variables (Yeh batayega ki kaun sa secret missing hai)
print(f"TELEGRAM_BOT_TOKEN present: {bool(TELEGRAM_BOT_TOKEN)}")
print(f"TELEGRAM_CHAT_ID present: {bool(TELEGRAM_CHAT_ID)}")
print(f"GEMINI_API_KEY present: {bool(GEMINI_API_KEY)}")
print(f"LINKEDIN_ACCESS_TOKEN present: {bool(LINKEDIN_ACCESS_TOKEN)}")
print(f"AUTHOR_URN present: {bool(AUTHOR_URN)}")

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram tokens missing, skipping message.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    res = requests.post(url, json=payload)
    print(f"Telegram Response: {res.status_code}")

def generate_post_content():
    if not GEMINI_API_KEY:
        return "Error: Gemini API Key is missing."
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = "Write an engaging, high-retention LinkedIn post about tech trends and personal growth, formatted with clean line breaks and hooks for an influencer."
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(gemini_url, json=payload).json()
    try:
        return response['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error generating text: {response}"

def post_to_linkedin(text):
    if not LINKEDIN_ACCESS_TOKEN or not AUTHOR_URN:
        print("LinkedIn tokens missing, skipping post.")
        return
    url = "https://api.linkedin.com/v2/ugcPosts"
    headers = {
        "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }
    payload = {
        "author": AUTHOR_URN,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {
            "com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"
        }
    }
    response = requests.post(url, headers=headers, json=payload)
    print(f"LinkedIn API Response: {response.status_code} - {response.text}")

if __name__ == "__main__":
    post_text = generate_post_content()
    print("Generated Post Text Preview:", post_text[:100])
    
    # Send draft to Telegram
    send_telegram_message(f"📝 *New LinkedIn Post Generated:*\n\n{post_text}")
    
    # Post to LinkedIn
    post_to_linkedin(post_text)
