import re

STORIES_FILE = "stories.txt"

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

# weekday: (pillar, language, [styles that rotate week by week], story tags (used by the story style), angles)
# 0 = Monday ... 6 = Sunday
PILLARS = {
    0: ("Business Analyst career guidance for freshers from non-tech backgrounds", "en", ["opinion", "story"],
        ["career", "sql", "tool", "fnb"], [
        "what people get wrong about the Business Analyst job",
        "how to read a Data/Business Analyst job description and spot what really matters",
        "the first skills to learn for a BA role, and what to skip",
        "how to turn a college or course project into a strong resume line",
    ]),
    1: ("Practical tool tip (Google Sheets, Excel, SQL)", "en", ["tutorial", "mistake"],
        [], [
        "one Google Sheets formula that saves time",
        "a beginner SQL pattern (like GROUP BY) in plain words",
        "a common data cleaning mistake and how to fix it",
        "one habit that makes a report easy for a manager to read",
    ]),
    2: ("Project breakdown from real work", "en", ["project"], [], []),
    3: ("Job hunt reality for freshers", "mix", ["story", "opinion"],
        ["job", "career", "fnb"], [
        "how to follow up politely after applying",
        "what to do when applications get no replies",
        "how to prepare for a business case question in a BA interview",
        "how to explain a career switch honestly in an interview",
    ]),
    4: ("Myth vs reality, and real work", "mix", ["myth", "project"],
        [], [
        "myth: you must be a coding expert to become a Business Analyst",
        "myth: only an MBA or a top college gets you a good analyst job",
        "myth: more certificates means more job offers",
        "myth: you need a perfect resume to start applying",
    ]),
    5: ("Personal update: job search and portfolio", "mix", ["notes"], [], []),
    6: ("Weekend discussion", "mix", ["discussion"],
        [], [
        "ask the community what helped them most in their career this year",
        "ask which skill people are learning right now and why",
        "ask what advice they wish they got as a fresher",
        "ask what they would tell their younger self about work",
    ]),
}

BLUEPRINTS = {
    "story": """STYLE: Story-led post, conversational.
- Line 1: a sharp line drawn from the real moment that makes people want to read on.
- The real moment in 2 to 4 plain sentences: the situation and what happened. Use ONLY what is in the real moment. Stay concrete.
- One short paragraph on what it taught, or what most people miss.
- One practical tip for the reader in a sentence or two.
- Closing line as required.""",
    "opinion": """STYLE: Honest opinion.
- Line 1: a clear stance a thoughtful practitioner would defend, slightly uncomfortable or surprising.
- Two short paragraphs on why, with one concrete example in plain prose (a hypothetical one is fine if introduced with 'Imagine' or 'Say').
- One sentence of fairness: when the opposite is true.
- One sentence on what the reader should do about it.
- Closing line as required.""",
    "tutorial": """STYLE: One small useful tip, explained the way a friendly colleague would.
- Line 1: the problem, or a surprising claim about the tip.
- A tiny concrete scenario in flowing prose, introduced with 'Imagine' or 'Say', with numbers that add up.
- The tip itself in 2 or 3 plain sentences: the formula, function or query to use and why it works.
- At most 3 short steps, and only if the tip truly has steps; otherwise write plain prose.
- Closing line as required.""",
    "mistake": """STYLE: A mistake worth fixing.
- Line 1: name the mistake plainly.
- What it looks like in practice (use the real moment only if one is provided; otherwise a hypothetical introduced with 'Imagine' or 'Say').
- Why it hurts, in one or two sentences.
- The fix in two or three plain sentences.
- Closing line as required.""",
    "myth": """STYLE: Myth-busting, sharp and short.
- Line 1: the myth, stated the way people actually say it.
- One sentence flipping it, then the proof in plain prose with one concrete example or named tool.
- What to do instead, in two sentences.
- Closing line as required.""",
    "project": """STYLE: Project breakdown, told like you are explaining it to a colleague.
- Line 1: the business question, or the most striking real finding from the facts.
- The problem in one or two sentences.
- What was built or analysed (data and tools) in two sentences, only from the facts.
- One or two findings, only from the facts, in plain prose.
- One honest limit or lesson, only if the facts contain one.
- Closing line as required.""",
    "discussion": """STYLE: Insight plus discussion.
- Line 1: a specific observation or question.
- One useful insight in 3 to 4 lines with a concrete example.
- 2 or 3 options readers can answer with, written in one flowing sentence.
- The closing question is required.""",
}

HOOKS = [
    "Open with a blunt, slightly uncomfortable statement.",
    "Open with a specific number or concrete detail.",
    "Open by naming the thing people get wrong.",
    "Open with 'Imagine' and a tiny scene (hypothetical, never about the creator).",
    "Open with a short contrast, like 'X is easy. Y is the hard part.'",
]

ENDINGS = {
    "question": "End with one easy-to-answer question that a reader could answer in a single line.",
    "takeaway": "End with one punchy takeaway line (no question).",
    "invite": "End by inviting readers to drop their own example in the comments.",
}
ENDING_ROTATION = ["question", "takeaway", "question", "invite"]

def format_rules(ending="question"):
    return f"""FORMAT (plain text only):
- Line 1 is the hook, under 14 words.
- Blank line between paragraphs. Each paragraph is 1 to 3 sentences. Do NOT put every sentence on its own line.
- {ENDINGS[ending]} This is the second last block.
- The last line is exactly 3 relevant hashtags.
- No markdown: no asterisks, no headings, no bullet symbols. Do not use dashes as punctuation."""

FORMAT_RULES = format_rules("question")

TONE_RULES = """TONE: a thoughtful working professional sharing something useful. Calm, specific, respectful. Not an influencer.
No emojis."""

HUMAN_RULES = """HUMAN VOICE (very important):
- Write like a sharp colleague talking to one person. Plain words, contractions are fine (don't, it's).
- The first two lines must make someone want to tap 'see more'. Never open with a generic question like 'Do you know what X does?'.
- One idea only. Do not try to teach everything.
- Vary sentence length. Avoid symmetrical lists. Use a numbered list only if the content truly has steps.
- Never use these: 'Here is how', 'Here's how', 'In today's', 'game-changer', 'unlock', 'dive into', 'delve', 'journey', 'leverage', "Let's", 'tips and tricks', 'Try this today', 'In conclusion', 'At the end of the day'.
- Do not use the labels 'Example:' or 'Reality:'. Introduce a hypothetical with 'Imagine' or 'Say'.
- Do not use em dashes or en dashes anywhere.
- Check every calculation. If you are not sure the numbers add up, use no numbers."""

BANNED = ["here is how", "here's how", "in today's", "game-changer", "game changer", "unlock", "dive into",
          "delve", "journey", "leverage", "let's", "tips and tricks", "try this today", "in conclusion",
          "at the end of the day", "example:", "reality:"]

def find_tells(text, style="x"):
    t = text.lower()
    return [b for b in BANNED if b in t]

# ---------------- formatting helper ----------------

def format_post(text):
    text = text.replace("\r\n", "\n").replace("**", "").replace("__", "")
    text = text.replace(" — ", ", ").replace("—", ", ").replace(" – ", ", ")
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

# ---------------- projects ----------------

PROJECTS_FILE = "projects.txt"

def load_projects():
    items = []
    try:
        with open(PROJECTS_FILE, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "|" not in line:
                    continue
                name, facts = line.split("|", 1)
                name, facts = name.strip(), facts.strip()
                if len(facts) >= 30:
                    items.append(f"{name}: {facts}")
    except FileNotFoundError:
        print("projects.txt not found, continuing without projects")
    return items

def pick_project(s):
    projects = load_projects()
    if not projects:
        return None
    used = s.setdefault("used_projects", [])
    unused = [p for p in projects if p[:40] not in used]
    if not unused:
        s["used_projects"] = []
        unused = projects
    project = unused[0]
    s["used_projects"].append(project[:40])
    return project
