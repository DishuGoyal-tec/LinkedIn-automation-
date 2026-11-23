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
