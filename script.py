import os
import requests

# Load secrets from GitHub environment variables
TELEGRAM_BOT_TOKEN = os.environ.get("8828879065:AAG2_w-Tb00HKajCcYm7Zn2934ra40LvHEA")
TELEGRAM_CHAT_ID = os.environ.get("6051624414")
GEMINI_API_KEY = os.environ.get("AQ.Ab8RN6KPC1gbtcaV5OZuazgB27lH1ygWMaKBKbf7ESb137HedA")
CLIENT_ID = os.environ.get("78yfc0yemxgo91")
CLIENT_SECRET = os.environ.get("WPL_AP1.B6zdEWzrvCmqGnUf.R6q1dg==")
AUTHOR_URN = os.environ.get("urn:li:person:19d052002")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"}
    requests.post(url, json=payload)

def generate_post_content():
    gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = "Write an engaging, high-retention LinkedIn post about tech trends and personal growth, formatted with clean line breaks and hooks for an influencer."
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(gemini_url, json=payload).json()
    
    try:
        return response['candidates'][0]['content']['parts'][0]['text']
    except Exception as e:
        return f"Error generating text: {response}"

if __name__ == "__main__":
    post_text = generate_post_content()
    
    # Send draft to Telegram so you can check it
    send_telegram_message(f"📝 *New LinkedIn Draft Generated:*\n\n{post_text}\n\n*(This is running live from GitHub Actions)*")
