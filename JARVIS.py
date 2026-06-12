"""
JARVIS - Personal AI for Chattychop
Run: python JARVIS.py
Browser handles mic + voice — no audio library issues
"""
import os, sys, json, threading, time, webbrowser, signal, subprocess, platform, uuid
from datetime import datetime
from pathlib import Path

OS = platform.system()
Path("jarvis_data").mkdir(exist_ok=True)

# ── AUTO INSTALL ──────────────────────────────────────────────────────────────
def install(pkg, imp=None):
    try: __import__(imp or pkg.replace("-","_"))
    except ImportError:
        print(f"  Installing {pkg}...")
        subprocess.run([sys.executable,"-m","pip","install",pkg,"-q","--quiet"], capture_output=True)

print("Checking packages...")
for p,i in [("flask",None),("flask-socketio","flask_socketio"),("requests",None),("tavily-python","tavily"),
            ("groq",None),("google-generativeai","google.generativeai"),("cohere",None),
            ("google-auth","google.auth"),("google-auth-oauthlib","google_auth_oauthlib"),
            ("google-auth-httplib2","google_auth_httplib2"),("google-api-python-client","googleapiclient")]:
    install(p,i)
print("✓ Ready\n")

# ── KEY SETUP ─────────────────────────────────────────────────────────────────
ENV = "jarvis_data/.env"

def load_env():
    if os.path.exists(ENV):
        for line in open(ENV, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k,v = line.strip().split("=",1)
                if v.strip(): os.environ.setdefault(k.strip(), v.strip())

def save_env():
    with open(ENV,"w",encoding="utf-8") as f:
        for k in ["AI_KEY","TAVILY_API_KEY"]:
            v = os.environ.get(k,"")
            if v: f.write(f"{k}={v}\n")

load_env()

if not os.environ.get("AI_KEY","").strip() or len(os.environ.get("AI_KEY","")) < 8:
    print("╔══════════════════════════════════════╗")
    print("║     JARVIS — First Time Setup        ║")
    print("╚══════════════════════════════════════╝\n")
    print("  Groq(gsk_) | Gemini(AIza) | OpenRouter(sk-or-) | Cohere | Anthropic(sk-ant)")
    k = input("  Paste your AI API key: ").strip()
    os.environ["AI_KEY"] = k
    t = input("  Paste Tavily key for web search (Enter to skip): ").strip()
    if t: os.environ["TAVILY_API_KEY"] = t
    save_env()
    print("\n  ✓ Saved!\n")

# ── MEMORY ────────────────────────────────────────────────────────────────────
MEM_FILE = "jarvis_data/memory.json"
def load_mem():
    try: return json.load(open(MEM_FILE,encoding="utf-8")) if os.path.exists(MEM_FILE) else {}
    except: return {}
def save_mem(m): json.dump(m,open(MEM_FILE,"w",encoding="utf-8"),indent=2)
MEM = load_mem()

def mem_summary():
    lines = []
    if MEM.get("facts"): lines.append("Facts: " + "; ".join(f"{k}={v}" for k,v in list(MEM["facts"].items())[:5]))
    if MEM.get("files"): lines.append("Files: " + "; ".join(list(MEM["files"].keys())[-4:]))
    if MEM.get("preferences"): lines.append("Prefs: " + "; ".join(f"{k}={v}" for k,v in list(MEM.get("preferences",{}).items())[:4]))
    return "\n".join(lines) or "No memories yet."

def auto_learn(user_input, response):
    txt = user_input.lower()
    for trigger, cat in [("i like","like"),("i love","love"),("i prefer","prefer"),("i hate","hate"),("i always","habit")]:
        if trigger in txt:
            after = txt.split(trigger, 1)[1].strip()[:60]
            if after:
                MEM.setdefault("preferences", {})[f"{cat}_{len(MEM.get('preferences',{}))}"] = after
                save_mem(MEM)
                break
    if any(x in txt for x in ["working on","building","my project","my startup"]):
        MEM.setdefault("learned", {})[f"proj_{len(MEM.get('learned',{}))}"] = user_input[:80]
        save_mem(MEM)

work_start_time = time.time()
last_active_time = time.time()
last_water_reminder = time.time()
BREAK_INTERVAL = 7200
WATER_INTERVAL = 3600
IDLE_TIMEOUT = 1800
birthday_wished_year = None

def check_timers():
    global work_start_time, last_active_time, last_water_reminder, birthday_wished_year
    now = time.time()
    today = datetime.now()
    msgs = []
    if today.month == 6 and today.day == 18:
        if birthday_wished_year != today.year:
            birthday_wished_year = today.year
            msgs.append("Happy Birthday Chattychop! You are " + str(today.year - 2011) + " today!")
    elapsed = now - work_start_time
    if elapsed > BREAK_INTERVAL:
        hours = int(elapsed // 3600)
        msgs.append(f"Bro you have been working {hours} hours, take a break!")
        work_start_time = now
    if now - last_water_reminder > WATER_INTERVAL:
        last_water_reminder = now
        msgs.append("Drink water bhai. Right now.")
    if now - last_active_time > IDLE_TIMEOUT:
        last_active_time = now
        msgs.append("Hey you went quiet. You there?")
    return msgs

def timer_loop():
    while True:
        time.sleep(60)
        try:
            msgs = check_timers()
            for msg in msgs:
                sio.emit("jarvis_notification", {"text": msg})
        except Exception:
            pass




SESSIONS_DIR = Path("jarvis_data/sessions")
SESSIONS_DIR.mkdir(exist_ok=True)
SETTINGS_FILE = "jarvis_data/settings.json"

def load_settings():
    try: return json.load(open(SETTINGS_FILE, encoding="utf-8")) if os.path.exists(SETTINGS_FILE) else {}
    except: return {}

def save_settings(s): json.dump(s, open(SETTINGS_FILE,"w",encoding="utf-8"), indent=2)

SETTINGS = load_settings()

def get_chrome_path():
    # Check user-saved path first
    saved = SETTINGS.get("chrome_path","").strip()
    if saved and os.path.exists(saved): return saved
    # Auto-detect
    defaults = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
        os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "google-chrome","chromium-browser"
    ]
    for p in defaults:
        if os.path.exists(p): return p
    return None

def open_in_chrome(url):
    try:
        # Open in a completely new CMD window - most reliable
        subprocess.Popen(
            f'start "" "{url}"',
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE if hasattr(subprocess, 'CREATE_NEW_CONSOLE') else 0
        )
        return True
    except Exception as e:
        try:
            os.system(f'start "" "{url}"')
            return True
        except:
            print(f"Open error: {e}")
            return False
current_session_id = None
HISTORY = []

def new_session():
    global current_session_id, HISTORY
    current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + str(uuid.uuid4())[:4]
    HISTORY = []
    return current_session_id

def save_session():
    if not current_session_id or not HISTORY: return
    # Generate smart title from first user message using AI
    title = "New Chat"
    if HISTORY:
        first_msg = HISTORY[0]["content"][:100]
        try:
            title_resp = call_ai([{"role":"user","content":f"Give a short 4-6 word title for a chat that starts with: '{first_msg}'. Reply with ONLY the title, no quotes, no punctuation at end."}])
            title = title_resp.strip()[:50]
        except:
            title = first_msg[:40]
    session = {
        "id": current_session_id,
        "title": title,
        "created": current_session_id[:15],
        "messages": HISTORY
    }
    json.dump(session, open(SESSIONS_DIR / f"{current_session_id}.json", "w", encoding="utf-8"), indent=2)

def load_session(sid):
    global current_session_id, HISTORY
    path = SESSIONS_DIR / f"{sid}.json"
    if path.exists():
        data = json.load(open(path, encoding="utf-8"))
        current_session_id = sid
        HISTORY = data.get("messages", [])
        return data
    return None

def get_all_sessions():
    sessions = []
    for f in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            data = json.load(open(f, encoding="utf-8"))
            sessions.append({"id": data["id"], "title": data.get("title","Chat"), "created": data.get("created","")})
        except: pass
    return sessions[:30]

# Resume last session or create new one
def resume_or_new():
    sessions = get_all_sessions()
    if sessions:
        last = sessions[0]
        data = load_session(last["id"])
        if data:
            print(f"  Resuming: {last['title']}")
            return
    new_session()

resume_or_new()

def system_prompt():
    now = datetime.now()
    birth = datetime(2011,6,18)
    age = now.year-birth.year-((now.month,now.day)<(birth.month,birth.day))
    return f"""You are JARVIS — Chattychop's personal AI and best friend.

PERSONALITY:
- Smart Indian friend. Mix English with Hindi/Telugu naturally: yaar, bhai, da, macha, arre. Don't force it.
- Keep replies SHORT — 2-3 sentences. You speak out loud.
- Zero sycophancy. No "Great question!" Just answer.
- Roast Chattychop when he's lazy or asking obvious stuff. He likes it.
- Understand Indian English, sarcasm, mixed language perfectly.

CHATTYCHOP:
- G Badrinath, {age} years old (June 18 2011). Call him Chattychop or boss.
- Vijayawada/Hyderabad, India. Now: {now.strftime("%I:%M %p, %A %B %d %Y IST")}
- Entrepreneur: CivicX (AI civic platform), Rot to Root (cold-chain startup), ChattyX (Instagram content agency), YouTube: Chatty Chop
- Works with Arduino, ESP32, Raspberry Pi
- Windows PC, 2 monitors

MEMORY: {mem_summary()}

RULES:
- If [Search: ...] is in the message, use those results to answer
- Be helpful on electronics, startups, code, projects
- Keep it conversational and fast
- If [CLASS MODE] in message: give detailed, educational, textbook-quality answers
- If [TODO] in message: help manage tasks clearly
- Learn from what user tells you — store preferences mentally
- When user says "I did this wrong" or "that was wrong", understand and correct
- Fix spelling mistakes intelligently — understand closest meaning
- When giving code, make it correct and complete like ChatGPT/Claude would
- If something fails, suggest the browser/Chrome alternative automatically"""

def call_ai(messages):
    key = os.environ.get("AI_KEY","").strip()
    try:
        if key.startswith("gsk_"):
            from groq import Groq
            r = Groq(api_key=key).chat.completions.create(
                model="llama-3.3-70b-versatile", max_tokens=250,
                messages=[{"role":"system","content":system_prompt()}]+messages)
            return r.choices[0].message.content.strip()
        elif key.startswith("AIza"):
            import google.generativeai as genai
            genai.configure(api_key=key)
            mdl = genai.GenerativeModel("gemini-1.5-flash",system_instruction=system_prompt())
            hist = [{"role":"user" if m["role"]=="user" else "model","parts":[m["content"]]} for m in messages[:-1]]
            return mdl.start_chat(history=hist).send_message(messages[-1]["content"]).text.strip()
        elif key.startswith("sk-or-"):
            import requests as req
            r = req.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},
                json={"model":"meta-llama/llama-3.3-70b-instruct:free","max_tokens":250,
                      "messages":[{"role":"system","content":system_prompt()}]+messages},timeout=30)
            return r.json()["choices"][0]["message"]["content"].strip()
        elif key.startswith("sk-ant"):
            import anthropic
            r = anthropic.Anthropic(api_key=key).messages.create(
                model="claude-opus-4-5",max_tokens=250,system=system_prompt(),messages=messages)
            return r.content[0].text.strip()
        else:
            import cohere
            r = cohere.ClientV2(api_key=key).chat(
                model="command-r-plus-08-2024",
                messages=[{"role":"system","content":system_prompt()}]+messages)
            return r.message.content[0].text.strip()
    except Exception as e:
        return f"API error: {e}"

def web_search(query):
    key = os.environ.get("TAVILY_API_KEY","").strip()
    if not key or len(key)<5: return None
    try:
        from tavily import TavilyClient
        results = TavilyClient(api_key=key).search(query,max_results=3)
        return "\n".join(f"{r.get('title','')}: {r.get('content','')[:200]}" for r in results.get("results",[])[:3])
    except: return None

SEARCH_TRIGGERS = ["what","who","how","when","where","why","which","does","is there","latest",
                   "current","price","pin","spec","datasheet","tutorial","news","find","define"]

# ── DIRECT ACTIONS ────────────────────────────────────────────────────────────
def direct_action(text):
    t = text.lower().strip()
    if t.startswith("jarvis"): t = t[6:].strip()

    APPS = {
        "chrome":["start","chrome"],"google chrome":["start","chrome"],
        "discord":["start","discord"],"spotify":["start","spotify"],
        "vs code":["code"],"vscode":["code"],"visual studio code":["code"],
        "notepad":["notepad"],"calculator":["calc"],
        "file explorer":["explorer"],"explorer":["explorer"],
        "brave":["start","brave"],"firefox":["start","firefox"],
        "edge":["start","msedge"],"whatsapp":["start","whatsapp"],
        "telegram":["start","telegram"],"steam":["start","steam"],
        "vlc":["start","vlc"],"arduino":["start","arduino"],
    }

    for name,cmd in APPS.items():
        if f"open {name}" in t or f"launch {name}" in t or f"start {name}" in t:
            try:
                subprocess.Popen(cmd, shell=True)
                return f"Opening {name}!"
            except Exception as e:
                return f"Tried to open {name} but got: {e}"

    if any(x in t for x in ["screenshot","take screenshot","capture screen"]):
        try:
            import pyautogui
            p = f"jarvis_data/ss_{datetime.now().strftime('%H%M%S')}.png"
            pyautogui.screenshot(p)
            return f"Screenshot saved!"
        except: return "Install pyautogui for screenshots: pip install pyautogui"

    if any(x in t for x in ["open downloads","show downloads","open folder"]):
        try:
            home = Path.home()
            subprocess.Popen(["explorer", str(home/"Downloads")], shell=True)
            return "Opening Downloads folder!"
        except: return "Couldn't open Downloads."

    if "find" in t and ("file" in t or "download" in t):
        query = t.replace("find","").replace("file","").replace("download","").replace("the","").strip()
        home = Path.home()
        for d in [home/"Downloads",home/"Desktop",home/"Documents"]:
            if d.exists():
                for f in list(d.iterdir()):
                    if query and any(q in f.name.lower() for q in query.split()):
                        try: os.startfile(str(f))
                        except: subprocess.Popen(["start",str(f)],shell=True)
                        return f"Found and opened: {f.name}"
        return f"Couldn't find '{query}' in Downloads or Desktop."


    # AI-powered open anything
    open_triggers = ["open ","go to ","launch ","take me to ","navigate to ","load ","visit ","watch "]
    for trigger in open_triggers:
        if trigger in t:
            what = t.split(trigger, 1)[1].strip()
            if what:
                ai_url_resp = call_ai([{"role":"user","content":"What is the best URL to open for: " + repr(what) + "? Reply with ONLY the full URL starting with https://, nothing else. If it is a YouTube channel give the direct channel URL. Be smart about .com vs .in etc."}])
                ai_url = ai_url_resp.strip().split()[0]
                if ai_url.startswith("http"):
                    if open_in_chrome(ai_url):
                        return "SEARCH_OPENED:" + ai_url + ":Opening " + what + "!"

    # AI-powered app opening
    if any(x in t for x in ["run ","open app","launch app","start app"]):
        for trigger in ["open app","launch app","run","start app"]:
            if trigger in t:
                app = t.split(trigger, 1)[1].strip()
                if app:
                    cmd_resp = call_ai([{"role":"user","content":"Windows CMD command to open " + repr(app) + ". Reply with ONLY the command. Example: notepad, calc, code, chrome"}])
                    cmd = cmd_resp.strip().splitlines()[0].strip()
                    if cmd and len(cmd) < 200:
                        try:
                            subprocess.Popen(cmd, shell=True)
                            return "Opening " + app + "!"
                        except:
                            return "Could not open " + app + ". Is it installed?"

    # File search by content/description
    if any(x in t for x in ["find file","search file","find document","search my computer","find in my pc","look for file"]):
        query = t
        for p in ["find file","search file","find document","search my computer","find in my pc","look for file","find"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            results = []
            home = Path.home()
            search_dirs = [home/"Downloads", home/"Desktop", home/"Documents", home/"Pictures"]
            for d in search_dirs:
                if d.exists():
                    try:
                        for f in d.rglob("*"):
                            if f.is_file() and any(q in f.name.lower() for q in query.lower().split()):
                                results.append(str(f))
                            # Also search inside text files
                            elif f.is_file() and f.suffix in [".txt",".md",".py",".js",".html",".csv"]:
                                try:
                                    content = f.read_text(errors="ignore")
                                    if query.lower() in content.lower():
                                        results.append(str(f) + " (contains text)")
                                except: pass
                    except: pass
            if results:
                top = results[:5]
                return "Found " + str(len(results)) + " files:\n" + "\n".join(top)
            return "No files found matching " + repr(query) + " in Downloads, Desktop or Documents."

    # Play music on Spotify
    if any(x in t for x in ["play music","play song","play some music","put on music","open spotify"]):
        query = t
        for p in ["play music","play song","play some music","put on music","play","open spotify and play"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query and query not in ["music","song","something","anything","spotify"]:
            url = "https://open.spotify.com/search/" + query.replace(" ","%20")
        else:
            url = "https://open.spotify.com"
        if open_in_chrome(url): return "SEARCH_OPENED:" + url + ":Opening Spotify!"

    # Google search
    if any(x in t for x in ["search google","search for","google search","look up"]):
        query = t
        for p in ["search google for","search for","google search for","look up","search google","search"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = "https://www.google.com/search?q=" + query.replace(" ","+")
            if open_in_chrome(url): return "SEARCH_OPENED:" + url + ":Searching for " + repr(query) + "!"

    # Image search
    if any(x in t for x in ["show me image","show image","find image","search image","show picture","show photo"]):
        query = t
        for p in ["show me images of","show images of","find images of","show image of","show picture of","show photo of"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = "https://www.google.com/search?tbm=isch&q=" + query.replace(" ","+")
            if open_in_chrome(url): return "IMAGE_SEARCH:" + url + ":Opening image search for " + repr(query) + "!"

    # Play music on Spotify
    if any(x in t for x in ["play music","play song","play some music","put on music","open spotify"]):
        query = t
        for p in ["play music","play song","play some music","put on music","play","open spotify and play"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query and query not in ["music","song","something","anything","spotify"]:
            url = f"https://open.spotify.com/search/{query.replace(' ','%20')}"
        else:
            url = "https://open.spotify.com"
        if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Opening Spotify!"

    # Google search
    if any(x in t for x in ["search google","search for","google search","look up"]):
        query = t
        for p in ["search google for","search for","google search for","look up","search google","search"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = f"https://www.google.com/search?q={query.replace(' ','+')}"
            if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Searching for '{query}'!"

    # Image search - auto open
    if any(x in t for x in ["show me image","show image","find image","search image","show picture","show photo"]):
        query = t
        for p in ["show me images of","show images of","find images of","show image of","show picture of","show photo of"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = f"https://www.google.com/search?tbm=isch&q={query.replace(' ','+')}"
            if open_in_chrome(url): return f"IMAGE_SEARCH:{url}:Opening image search for '{query}'!"

    # Play music on Spotify
    if any(x in t for x in ["play music","play song","play some music","put on music","open spotify"]):
        query = t
        for p in ["play music","play song","play some music","put on music","play","open spotify and play"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query and query not in ["music","song","something","anything","spotify"]:
            url = f"https://open.spotify.com/search/{query.replace(' ','%20')}"
        else:
            url = "https://open.spotify.com"
        if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Opening Spotify!"

    # Google search
    if any(x in t for x in ["search google","search for","google search","look up"]):
        query = t
        for p in ["search google for","search for","google search for","look up","search google","search"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = f"https://www.google.com/search?q={query.replace(' ','+')}"
            if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Searching for '{query}'!"

    # Image search
    if any(x in t for x in ["show me image","show image","find image","search image","show picture","show photo"]):
        query = t
        for p in ["show me images of","show images of","find images of","show image of","show picture of","show photo of"]:
            if t.startswith(p): query = t[len(p):].strip(); break
        if query:
            url = f"https://www.google.com/search?tbm=isch&q={query.replace(' ','+')}"
            if open_in_chrome(url): return f"IMAGE_SEARCH:{url}:Searching images for '{query}'!"


    # Weather
    if any(x in t for x in ["weather","temperature","how hot","how cold","rain today","forecast"]):
        city = "Hyderabad"
        for c in ["hyderabad","vijayawada","delhi","mumbai","bangalore","chennai"]:
            if c in t: city = c.title(); break
        try:
            import urllib.request, json as _json
            url = f"https://wttr.in/{city.replace(' ','+')}?format=j1"
            with urllib.request.urlopen(url, timeout=5) as r:
                data = _json.loads(r.read())
            curr = data["current_condition"][0]
            temp = curr["temp_C"]
            feels = curr["FeelsLikeC"]
            desc = curr["weatherDesc"][0]["value"]
            humidity = curr["humidity"]
            return f"Weather in {city}: {temp}°C, feels like {feels}°C. {desc}. Humidity {humidity}%."
        except Exception as e:
            return f"Couldn't fetch weather: {e}"

    # Screen capture + explain
    if any(x in t for x in ["what's on screen","whats on screen","read my screen","explain my screen","what is on screen","look at screen","screen help","whats this on screen"]):
        try:
            import pyautogui, base64, io
            from PIL import Image
            sc = pyautogui.screenshot()
            sc.thumbnail((1280, 720))
            buf = io.BytesIO()
            sc.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            question = t.replace("what's on screen","").replace("whats on screen","").replace("read my screen","").replace("explain my screen","").replace("what is on screen","").replace("look at screen","").replace("screen help","").strip() or "What is on screen? Explain briefly."
            resp = call_ai([{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/png","data":img_b64}},
                {"type":"text","text":question + " Be concise."}
            ]}])
            return resp
        except ImportError:
            return "Install pyautogui and Pillow for screen reading: pip install pyautogui Pillow"
        except Exception as e:
            return f"Screen read failed: {e}"

    # Arduino/ESP32 quick reference
    if any(x in t for x in ["pinout","datasheet","pin diagram","how to connect","wiring","schematic","sensor pin","arduino pin","esp32 pin"]):
        component = t
        for p in ["pinout of","datasheet of","pin diagram of","how to connect","wiring for","pins of","schematic for","arduino pin for","esp32 pin for"]:
            if p in t: component = t.split(p,1)[1].strip(); break
        if component:
            search_url = f"https://www.google.com/search?q={component.replace(' ','+')}+pinout+datasheet"
            img_url = f"https://www.google.com/search?tbm=isch&q={component.replace(' ','+')}+pinout+diagram"
            open_in_chrome(search_url)
            return f"SEARCH_OPENED:{search_url}:Opening pinout/datasheet for {component}. Also searching images!"

    # Code runner
    if any(x in t for x in ["run this code","run code","execute code","execute this","run this script"]):
        return "Paste your code in the chat and I'll analyze it and tell you what it does and any errors. For actually running it I'd need to know the language — what are you running?"

    # Clipboard manager
    if any(x in t for x in ["what did i copy","clipboard","what's in clipboard","whats in clipboard","last copied","show clipboard"]):
        try:
            import subprocess as _sub
            result = _sub.run(['powershell','-command','Get-Clipboard'], capture_output=True, text=True, timeout=3)
            content = result.stdout.strip()
            if content:
                return f"Your clipboard has: {content[:300]}"
            return "Clipboard is empty."
        except:
            return "Couldn't read clipboard on this system."

    # Roast mode
    if any(x in t for x in ["roast me","roast yourself","give me a roast","savage mode","go off on me"]):
        roast = call_ai([{"role":"user","content":"Roast Chattychop (G Badrinath, 14 year old student entrepreneur from Vijayawada). Be savage, funny, Indian style roast. 2-3 sentences max. Reference his projects CivicX and ChattyX if possible."}])
        return roast

    # WhatsApp quick message
    if any(x in t for x in ["whatsapp","send message to","message to","text to"]):
        contact = t
        for p in ["send message to","message to","text to","whatsapp","open whatsapp and message"]:
            if p in t: contact = t.split(p,1)[1].strip(); break
        url = f"https://web.whatsapp.com/send?phone={contact}" if contact.replace("+","").replace(" ","").isdigit() else "https://web.whatsapp.com"
        if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Opening WhatsApp!"

    # Focus mode
    if any(x in t for x in ["focus mode","focus for","block distractions","pomodoro","study mode"]):
        mins = 25  # default pomodoro
        import re as _re
        nums = _re.findall(r'\d+', t)
        if nums: mins = int(nums[0])
        MEM.setdefault("focus",{})["active"] = True
        MEM.setdefault("focus",{})["end"] = (datetime.now().timestamp() + mins*60)
        save_mem(MEM)
        return f"Focus mode on for {mins} minutes. Go! I'll remind you when time's up."

    # Summarize page
    if any(x in t for x in ["summarize this page","summarize the page","summarize current page","what is this page","tldr this page"]):
        return "I can't directly read your browser tabs yet — but copy the text from the page and paste it here, I'll summarize it instantly."

    # What should I work on
    if any(x in t for x in ["what should i work on","what to work on","suggest task","what should i do","prioritize my tasks"]):
        todos = load_todos()
        pending = [t["text"] for t in todos if not t.get("done")]
        if pending:
            suggestion = call_ai([{"role":"user","content":f"Chattychop has these pending tasks: {pending}. Which one should he work on first and why? Be brief and direct."}])
            return suggestion
        return "Your to-do list is empty! Add some tasks first."

    # Meeting mode
    if any(x in t for x in ["meeting mode","i am in a meeting","joining a call","google meet","in a meet"]):
        return "Meeting mode on — I'll stay quiet unless you call me. Good luck in the meeting!"


    # Voice note - trigger from text (voice handled in browser)
    if any(x in t for x in ["take a note","voice note","record note","save this note","note this down","remember this note"]):
        note_text = t
        for p in ["take a note","voice note","record note","save this note","note this down","remember this note"]:
            if t.startswith(p): note_text = t[len(p):].strip(); break
        if note_text:
            from datetime import datetime as _dt
            note = {"text": note_text, "time": _dt.now().strftime("%d %b %Y %I:%M %p")}
            notes_path = Path("jarvis_data/notes.json")
            existing = []
            if notes_path.exists():
                try: existing = json.load(open(notes_path, encoding="utf-8"))
                except: pass
            existing.append(note)
            json.dump(existing, open(notes_path, "w", encoding="utf-8"), indent=2)
            return f"Note saved: '{note_text}'"

    # Summarize any pasted text or URL
    if any(x in t for x in ["summarize this","summarize:","tldr","give me summary","summarize the following","sum this up"]):
        content = t
        for p in ["summarize this","summarize:","tldr","give me summary","summarize the following","sum this up"]:
            if p in t: content = t.split(p,1)[1].strip(); break
        if content and len(content) > 50:
            summary = call_ai([{"role":"user","content":f"Summarize this in 3-4 bullet points, keep it short and clear:\n\n{content[:3000]}"}])
            return summary
        return "Paste the text you want summarized after saying 'summarize this:'"

    # Fetch and summarize a URL
    if any(x in t for x in ["summarize url","read this url","summarize this link","read this link","what does this link say"]):
        import re as _re
        urls = _re.findall(r'https?://\S+', t)
        if urls:
            try:
                import urllib.request as _ur
                req = _ur.Request(urls[0], headers={"User-Agent":"Mozilla/5.0"})
                with _ur.urlopen(req, timeout=8) as r:
                    html = r.read().decode("utf-8", errors="ignore")
                # Strip HTML tags
                import re as _r2
                text = _r2.sub(r'<[^>]+>', ' ', html)
                text = ' '.join(text.split())[:3000]
                summary = call_ai([{"role":"user","content":f"Summarize this webpage content in 3-4 sentences:\n{text}"}])
                return summary
            except Exception as e:
                return f"Couldn't read that URL: {e}"
        return "Give me a URL to summarize."

    # Smart screen explain - works with any AI that supports vision
    if any(x in t for x in ["explain screen","analyze screen","debug screen","check screen","screen error","whats wrong on screen"]):
        try:
            import pyautogui, base64, io
            from PIL import Image
            sc = pyautogui.screenshot()
            sc.thumbnail((1280, 720))
            buf = io.BytesIO()
            sc.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()
            question = t.replace("explain screen","").replace("analyze screen","").replace("debug screen","").replace("check screen","").replace("screen error","").replace("whats wrong on screen","").strip() or "What do you see? Any errors or issues?"
            key = os.environ.get("AI_KEY","")
            if key.startswith("sk-ant") or key.startswith("AIza"):
                resp = call_ai([{"role":"user","content":[
                    {"type":"image","source":{"type":"base64","media_type":"image/png","data":img_b64}},
                    {"type":"text","text":question}
                ]}])
            else:
                resp = call_ai([{"role":"user","content":f"The user took a screenshot and asked: {question}. Tell them you can see the screen and describe what might be there based on context, or suggest they use Gemini/Anthropic key for actual screen reading."}])
            return resp
        except ImportError:
            return "Install pyautogui and Pillow: pip install pyautogui Pillow"
        except Exception as e:
            return f"Screen analysis failed: {e}"

    # Translate anything
    if any(x in t for x in ["translate","translation","in hindi","in telugu","in tamil","what does this mean in","say this in"]):
        translate_resp = call_ai([{"role":"user","content":f"User asked: {t}. Translate or explain as requested. Be direct."}])
        return translate_resp

    # Math and calculations
    if any(x in t for x in ["calculate","what is","how much is","solve","compute","equals"]) and any(c in t for c in "0123456789"):
        try:
            import ast as _ast
            expr = t
            for p in ["calculate","what is","how much is","solve","compute","what equals"]:
                if p in t: expr = t.split(p,1)[1].strip(); break
            # Safe eval
            node = _ast.parse(expr.replace("x","*").replace("^","**"), mode="eval")
            result = eval(compile(node, "<string>", "eval"))
            return f"{expr} = {result}"
        except:
            calc_resp = call_ai([{"role":"user","content":f"Calculate or solve: {t}. Give just the answer."}])
            return calc_resp

    # Focus mode reminder check
    focus = MEM.get("focus",{})
    if focus.get("active") and time.time() > focus.get("end", float("inf")):
        MEM["focus"]["active"] = False
        save_mem(MEM)
        return "Focus session done! Take a break, you earned it."

    # Dictionary / define
    if any(x in t for x in ["define ","what does","meaning of","definition of","what is the meaning"]):
        word = t
        for p in ["define","what does","meaning of","definition of","what is the meaning of"]:
            if p in t: word = t.split(p,1)[1].strip().split()[0]; break
        if word:
            define_resp = call_ai([{"role":"user","content":f"Define '{word}' simply in 1-2 sentences like a smart friend would explain it."}])
            return define_resp


    # SEND/DRAFT PENDING EMAIL
    if PENDING_EMAIL and any(x in t for x in ["send it","send now","send the email","yes send","send","go ahead"]):
        return gmail_send(to_drafts=False)
    if PENDING_EMAIL and any(x in t for x in ["save draft","keep as draft","draft it","save it as draft"]):
        return gmail_send(to_drafts=True)
    if PENDING_EMAIL and any(x in t for x in ["edit","change","update","rewrite"]):
        new_body = call_ai([{"role":"user","content":f"Rewrite this email with instruction: {t}\n\n{PENDING_EMAIL.get('body','')}\n\nReturn ONLY the new email body."}])
        PENDING_EMAIL["body"] = new_body
        return f"EMAIL_DRAFT:Updated:\n\nTo: {PENDING_EMAIL['to']}\nSubject: {PENDING_EMAIL['subject']}\n\n{new_body}\n\n---\nSay send or draft."

    # WRITE EMAIL
    for trigger in ["write email","compose email","draft email","send email to","write mail","email to","write a mail"]:
        if trigger in t:
            rest = t.split(trigger, 1)[1].strip()
            email_data = call_ai([{"role":"user","content":f"Write a professional email for: {rest}. Return ONLY valid JSON: {{to, subject, body}}. No markdown."}])
            try:
                import json as _j, re as _r
                clean = _r.sub(r"```.*?```", "", email_data, flags=_r.DOTALL).strip()
                data = _j.loads(clean)
                return gmail_draft_show(data.get("to","?"), data.get("subject","No subject"), data.get("body",""))
            except:
                return gmail_draft_show("?", "Email", email_data)

    # READ INBOX
    if any(x in t for x in ["check email","read email","check inbox","any emails","new emails","show emails"]):
        return gmail_read_inbox()

    # GOOGLE DRIVE
    if any(x in t for x in ["find in drive","search drive","in my drive","google drive"]):
        query = t
        for p in ["find in drive","search drive","in my drive","google drive"]:
            if p in t: query = t.split(p,1)[1].strip(); break
        return drive_search_files(query)

    # CALENDAR READ
    if any(x in t for x in ["my calendar","check calendar","scheduled","what do i have","am i free","any events","my schedule"]):
        import re as _re
        nums = _re.findall(r"\d+", t)
        days = int(nums[0]) if nums else 7
        return calendar_get_events(days)

    # CALENDAR CREATE
    if any(x in t for x in ["create event","add to calendar","schedule a","remind me on","set a meeting","book a slot"]):
        event_data = call_ai([{"role":"user","content":f"Extract event from: {t}. Today: {datetime.now().strftime('%Y-%m-%d')}. Return ONLY JSON: {{title, datetime_iso, description}}. No markdown."}])
        try:
            import json as _j, re as _r
            clean = _r.sub(r"```.*?```", "", event_data, flags=_r.DOTALL).strip()
            data = _j.loads(clean)
            return calendar_create_event(data.get("title","Event"), data.get("datetime_iso", datetime.now().isoformat()), data.get("description",""))
        except:
            return "Couldn't parse event. Try: 'schedule meeting with John tomorrow at 3pm'"

    # AI-POWERED SMART OPEN
    for trigger in ["open ","launch ","start ","go to ","take me to ","run "]:
        if t.startswith(trigger):
            what = t[len(trigger):].strip()
            if not what: continue
            decision = call_ai([{"role":"user","content":f"User wants to open: {what}. Decide action. Reply ONLY with JSON: {{action: youtube_search OR chrome_tab OR pc_app OR download_app, value: string}}. youtube_search if it is a video/channel/music to watch. chrome_tab if it is a website. pc_app if it is a desktop app installed on Windows. download_app if app likely not installed. For youtube_search give search query. For chrome_tab give full URL. For pc_app give Windows cmd command. For download_app give Microsoft Store URL."}])
            try:
                import json as _j, re as _r
                clean = _r.sub(r"```.*?```", "", decision, flags=_r.DOTALL).strip()
                d = _j.loads(clean)
                action = d.get("action","chrome_tab")
                value = d.get("value","")
                if action == "youtube_search" and value:
                    url = f"https://www.youtube.com/results?search_query={value.replace(' ','+')}"
                    if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Searching YouTube for {what}!"
                elif action == "chrome_tab" and value:
                    url = value if value.startswith("http") else f"https://{value}"
                    if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Opening {what}!"
                elif action == "pc_app" and value:
                    try:
                        subprocess.Popen(value, shell=True)
                        return f"Opening {what}!"
                    except:
                        dl_url = f"https://apps.microsoft.com/search?query={what.replace(' ','+')}"
                        open_in_chrome(dl_url)
                        return f"SEARCH_OPENED:{dl_url}:{what} not found. Opening Microsoft Store to download it!"
                elif action == "download_app" and value:
                    url = value if value.startswith("http") else f"https://apps.microsoft.com/search?query={what.replace(' ','+')}"
                    if open_in_chrome(url): return f"SEARCH_OPENED:{url}:{what} not installed. Opening download page!"
            except:
                url = f"https://www.google.com/search?q={what.replace(' ','+')}"
                open_in_chrome(url)
                return f"SEARCH_OPENED:{url}:Searching for {what}!"

    # IMAGE SEARCH - only on "show me"
    if t.startswith("show me ") and any(x in t for x in ["image","photo","picture","how it looks","diagram","pinout","circuit","what does"]):
        query = t[8:].strip()
        url = f"https://www.google.com/search?tbm=isch&q={query.replace(' ','+')}"
        if open_in_chrome(url): return f"IMAGE_SEARCH:{url}:Showing images for {query}!"

    # BUILD MODE
    if any(x in t for x in ["build me an app","build this for me","create this app","make this app","build an app"]):
        url = "https://claude.ai"
        if open_in_chrome(url): return f"SEARCH_OPENED:{url}:Opening Claude for app building!"


    # CREATE SKILL
    if any(x in t for x in ["create skill","new skill","make skill","add skill","teach jarvis","save skill"]):
        for trigger in ["create skill","new skill","make skill","add skill","teach jarvis to","save skill"]:
            if trigger in t:
                rest = t.split(trigger, 1)[1].strip()
                if ":" in rest:
                    name, desc = rest.split(":", 1)
                    name = name.strip()
                    desc = desc.strip()
                else:
                    # AI figures out name and description
                    name = rest.split()[0] if rest else "unnamed"
                    desc = rest
                if name and desc:
                    return create_skill_from_description(name, desc)
                return "Tell me the skill name and what it should do. Example: create skill morning routine: open YouTube, check calendar and tell me the weather"

    # LIST SKILLS
    if any(x in t for x in ["list skills","show skills","my skills","what skills","show all skills","what can i run"]):
        if not SKILLS:
            return "No skills saved yet. Create one with: create skill [name]: [description]"
        skill_list = "\n".join([f"• {k}: {v.get('description','')[:60]}" for k, v in list(SKILLS.items())[:20]])
        return f"Your skills ({len(SKILLS)}):\n{skill_list}"

    # DELETE SKILL
    if any(x in t for x in ["delete skill","remove skill","forget skill"]):
        for trigger in ["delete skill","remove skill","forget skill"]:
            if trigger in t:
                name = t.split(trigger, 1)[1].strip().lower()
                if name in SKILLS:
                    del SKILLS[name]
                    save_skills(SKILLS)
                    return f"Skill '{name}' deleted."
                return f"No skill called '{name}' found."

    # RUN SKILL - check if input matches any saved skill
    for skill_name, skill_data in SKILLS.items():
        trigger_words = skill_data.get("trigger_words", [skill_name])
        if any(tw in t for tw in trigger_words) or skill_name in t:
            extra = t
            for tw in trigger_words:
                if tw in t: extra = t.replace(tw, "").strip(); break
            return run_skill(skill_name, extra)

    return None

# Class mode flag
CLASS_MODE = False

def process(user_input):
    global HISTORY, MEM, CLASS_MODE
    msg = user_input.strip()

    # Inject class mode context
    if CLASS_MODE:
        msg = "[CLASS MODE] " + msg

    # Direct action first
    action = direct_action(msg)
    if action:
        HISTORY.append({"role":"user","content":msg})
        HISTORY.append({"role":"assistant","content":action})
        if len(HISTORY)>30: HISTORY=HISTORY[-30:]
        return action

    # Auto-remember file mentions
    if any(w in msg.lower() for w in ["downloading","downloaded","saved file"]):
        MEM.setdefault("files",{})[datetime.now().strftime("%m%d_%H%M")] = msg
        save_mem(MEM)

    # Web search if needed
    if any(t in msg.lower() for t in SEARCH_TRIGGERS):
        result = web_search(msg)
        if result: msg = f"{msg}\n\n[Search: {result}]"

    HISTORY.append({"role":"user","content":msg})
    if len(HISTORY)>30: HISTORY=HISTORY[-30:]

    response = call_ai(list(HISTORY))
    HISTORY[-1]={"role":"user","content":user_input}
    HISTORY.append({"role":"assistant","content":response})
    save_session()
    auto_learn(user_input, response)
    global last_active_time
    last_active_time = time.time()

    # Auto open Chrome only for specific visual/media requests
    t = user_input.lower()
    if any(x in t for x in ["show me image","show me photo","show me picture","show me video","search google","google search","find image","find video"]):
        query = user_input.strip()
        if "image" in t or "photo" in t or "picture" in t:
            url = f"https://www.google.com/search?tbm=isch&q={query.replace(' ','+')}"
        else:
            url = f"https://www.google.com/search?q={query.replace(' ','+')}"
        open_in_chrome(url)

    return response

# ── SERVER ────────────────────────────────────────────────────────────────────
from flask import Flask, jsonify, request
from flask_socketio import SocketIO

app = Flask(__name__)
app.config["SECRET_KEY"] = "jarvis2025"
sio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

@app.route("/")
def index(): return HTML

@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json(force=True, silent=True) or {}
        msg = data.get("message","").strip()
        if not msg: return jsonify({"error":"No message"}),400
        response = process(msg)
        return jsonify({"response":response})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/open_tab", methods=["POST"])
def open_tab():
    try:
        data = request.get_json(force=True, silent=True) or {}
        url = data.get("url","")
        if not url: return jsonify({"error":"No URL"}),400
        open_in_chrome(url)
        return jsonify({"ok":True,"chrome":get_chrome_path()})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@app.route("/api/sessions/<sid>/activate", methods=["POST"])
def activate_session(sid):
    data = load_session(sid)
    if data: return jsonify({"ok":True})
    return jsonify({"error":"Not found"}),404

@app.route("/api/status")
def status():
    return jsonify({"online":True,"messages":len(HISTORY),"session":current_session_id})

@app.route("/api/sessions")
def sessions():
    return jsonify(get_all_sessions())

@app.route("/api/sessions/new", methods=["POST"])
def api_new_session():
    sid = new_session()
    return jsonify({"session_id": sid})

@app.route("/api/sessions/<sid>", methods=["GET"])
def api_load_session(sid):
    data = load_session(sid)
    if data: return jsonify(data)
    return jsonify({"error":"Not found"}), 404

@app.route("/api/sessions/<sid>", methods=["DELETE"])
def api_delete_session(sid):
    path = SESSIONS_DIR / f"{sid}.json"
    if path.exists(): path.unlink()
    return jsonify({"ok":True})

# TODO LIST
TODO_FILE = "jarvis_data/todos.json"
def load_todos():
    try: return json.load(open(TODO_FILE,encoding="utf-8")) if os.path.exists(TODO_FILE) else []
    except: return []
def save_todos(t): json.dump(t,open(TODO_FILE,"w",encoding="utf-8"),indent=2)

# ── SKILLS SYSTEM ─────────────────────────────────────────────────────────────
SKILLS_FILE = "jarvis_data/skills.json"

def load_skills():
    try:
        return json.load(open(SKILLS_FILE, encoding="utf-8")) if os.path.exists(SKILLS_FILE) else {}
    except:
        return {}

def save_skills(skills):
    json.dump(skills, open(SKILLS_FILE, "w", encoding="utf-8"), indent=2, ensure_ascii=False)

SKILLS = load_skills()

def run_skill(name, extra_input=""):
    """Execute a saved skill by name"""
    skill = SKILLS.get(name.lower().strip())
    if not skill:
        # Try fuzzy match
        for k in SKILLS:
            if name.lower() in k or k in name.lower():
                skill = SKILLS[k]
                break
    if not skill:
        return f"No skill called '{name}' found. Create it with: create skill [name]: [description of what it does]"

    prompt = skill.get("prompt", "")
    if extra_input:
        prompt = f"{prompt}\n\nAdditional context: {extra_input}"

    # Execute skill actions
    actions = skill.get("actions", [])
    results = []
    for action in actions:
        action_result = direct_action(action.lower())
        if action_result:
            results.append(action_result)

    # Also run through AI with the skill prompt
    ai_result = call_ai([{"role": "user", "content": f"Execute this skill: {prompt}\n\nExtra input: {extra_input or 'none'}. Be direct and execute the task."}])
    if ai_result:
        results.append(ai_result)

    return "\n".join(results) if results else ai_result

def create_skill_from_description(name, description):
    """Use AI to parse skill description and create structured skill"""
    skill_data = call_ai([{"role": "user", "content": f"""Create a JARVIS skill called '{name}' that does: {description}

Return ONLY valid JSON (no markdown):
{{
  "name": "{name}",
  "description": "{description}",
  "prompt": "detailed instruction for AI on what to do when this skill runs",
  "actions": ["list of direct commands like open youtube, check email etc if applicable"],
  "trigger_words": ["words that should trigger this skill"],
  "created": "{datetime.now().isoformat()}"
}}"""}])

    try:
        import re as _r
        clean = _r.sub(r"```.*?```", "", skill_data, flags=_r.DOTALL).strip()
        # Handle case where AI returns json block
        if clean.startswith("json"):
            clean = clean[4:].strip()
        skill = json.loads(clean)
        SKILLS[name.lower().strip()] = skill
        save_skills(SKILLS)
        return f"Skill '{name}' created and saved! Say '{name}' anytime to run it."
    except Exception as e:
        # Fallback - save basic skill
        SKILLS[name.lower().strip()] = {
            "name": name,
            "description": description,
            "prompt": description,
            "actions": [],
            "trigger_words": [name.lower()],
            "created": datetime.now().isoformat()
        }
        save_skills(SKILLS)
        return f"Skill '{name}' created! Say '{name}' to run it."


# ── GOOGLE AUTH ───────────────────────────────────────────────────────────────
import pickle as _pickle

GOOGLE_TOKEN_FILE = "jarvis_data/google_token.pickle"
GOOGLE_CREDS_FILE_PATH = "credentials.json"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar",
]

def get_google_creds(force_refresh=False):
    """Get or refresh Google OAuth credentials"""
    creds = None
    if not force_refresh and os.path.exists(GOOGLE_TOKEN_FILE):
        try:
            with open(GOOGLE_TOKEN_FILE, "rb") as f:
                creds = _pickle.load(f)
        except: pass

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            with open(GOOGLE_TOKEN_FILE, "wb") as f:
                _pickle.dump(creds, f)
            return creds
        except: pass

    # Need fresh auth
    creds_file = SETTINGS.get("google_creds_file", GOOGLE_CREDS_FILE_PATH)
    if not os.path.exists(creds_file):
        # Try in same dir as JARVIS.py
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
        if os.path.exists(alt):
            creds_file = alt
        else:
            return None

    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(creds_file, GOOGLE_SCOPES)
        creds = flow.run_local_server(port=0)
        with open(GOOGLE_TOKEN_FILE, "wb") as f:
            _pickle.dump(creds, f)
        return creds
    except Exception as e:
        print(f"Google auth error: {e}")
        return None

def disconnect_google():
    """Remove stored Google token"""
    if os.path.exists(GOOGLE_TOKEN_FILE):
        os.remove(GOOGLE_TOKEN_FILE)
    return "Google account disconnected."

def is_google_connected():
    creds = get_google_creds()
    return creds is not None and creds.valid

# ── GMAIL ─────────────────────────────────────────────────────────────────────
# Store pending email draft for confirm/send flow
PENDING_EMAIL = {}

def gmail_draft_show(to, subject, body):
    """Store draft and return formatted preview"""
    global PENDING_EMAIL
    PENDING_EMAIL = {"to": to, "subject": subject, "body": body, "status": "pending"}
    return f"EMAIL_DRAFT:Here's the email I wrote:\n\nTo: {to}\nSubject: {subject}\n\n{body}\n\n---\nSay \'send\' to send, \'draft\' to save to drafts, or \'edit [what to change]\' to revise."

def gmail_send(to_drafts=False):
    """Send or save the pending email"""
    global PENDING_EMAIL
    if not PENDING_EMAIL:
        return "No email to send. Ask me to write one first."
    creds = get_google_creds()
    if not creds:
        return "Google not connected. Go to Settings → Connect Google."
    try:
        from googleapiclient.discovery import build
        import base64
        from email.mime.text import MIMEText
        service = build("gmail", "v1", credentials=creds)
        msg = MIMEText(PENDING_EMAIL["body"])
        msg["to"] = PENDING_EMAIL["to"]
        msg["subject"] = PENDING_EMAIL["subject"]
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        if to_drafts:
            service.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
            PENDING_EMAIL = {}
            return "Saved to Gmail drafts!"
        else:
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            PENDING_EMAIL = {}
            return "Email sent!"
    except Exception as e:
        return f"Gmail error: {e}"

def gmail_read_inbox(max_results=5):
    """Read latest emails"""
    creds = get_google_creds()
    if not creds:
        return "Google not connected. Go to Settings → Connect Google."
    try:
        from googleapiclient.discovery import build
        service = build("gmail", "v1", credentials=creds)
        results = service.users().messages().list(userId="me", maxResults=max_results, labelIds=["INBOX"]).execute()
        messages = results.get("messages", [])
        if not messages:
            return "Inbox is empty."
        emails = []
        for msg in messages[:5]:
            m = service.users().messages().get(userId="me", id=msg["id"], format="metadata",
                metadataHeaders=["From","Subject","Date"]).execute()
            headers = {h["name"]: h["value"] for h in m["payload"]["headers"]}
            emails.append(f"From: {headers.get('From','?')}\nSubject: {headers.get('Subject','?')}\nDate: {headers.get('Date','?')}")
        return "Latest emails:\n\n" + "\n\n---\n".join(emails)
    except Exception as e:
        return f"Gmail read error: {e}"

# ── GOOGLE DRIVE ──────────────────────────────────────────────────────────────
def drive_search_files(query, max_results=5):
    creds = get_google_creds()
    if not creds:
        return "Google not connected. Go to Settings → Connect Google."
    try:
        from googleapiclient.discovery import build
        service = build("drive", "v3", credentials=creds)
        results = service.files().list(
            q=f"name contains '{query}' and trashed=false",
            pageSize=max_results,
            fields="files(id,name,mimeType,webViewLink,modifiedTime)"
        ).execute()
        files = results.get("files", [])
        if not files:
            return f"No files found matching '{query}' in Google Drive."
        output = [f"Found {len(files)} files in Drive:\n"]
        for f in files:
            output.append(f"• {f['name']}\n  {f.get('webViewLink','No link')}")
        return "\n".join(output)
    except Exception as e:
        return f"Drive search error: {e}"

# ── GOOGLE CALENDAR ───────────────────────────────────────────────────────────
def calendar_get_events(days_ahead=7):
    creds = get_google_creds()
    if not creds:
        return "Google not connected. Go to Settings → Connect Google."
    try:
        from googleapiclient.discovery import build
        service = build("calendar", "v3", credentials=creds)
        now = datetime.utcnow().isoformat() + "Z"
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + "Z"
        events_result = service.events().list(
            calendarId="primary", timeMin=now, timeMax=end,
            maxResults=10, singleEvents=True, orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return f"Nothing scheduled in the next {days_ahead} days. You're free!"
        lines = [f"Next {days_ahead} days:"]
        for e in events:
            start = e["start"].get("dateTime", e["start"].get("date"))
            lines.append(f"• {e.get('summary','Untitled')} — {start}")
        return "\n".join(lines)
    except Exception as e:
        return f"Calendar error: {e}"

def calendar_create_event(title, datetime_iso, description=""):
    creds = get_google_creds()
    if not creds:
        return "Google not connected. Go to Settings → Connect Google."
    try:
        from googleapiclient.discovery import build
        from datetime import timedelta
        service = build("calendar", "v3", credentials=creds)
        start_dt = datetime.fromisoformat(datetime_iso)
        end_dt = start_dt + timedelta(hours=1)
        event = {
            "summary": title,
            "description": description,
            "start": {"dateTime": start_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "end": {"dateTime": end_dt.isoformat(), "timeZone": "Asia/Kolkata"},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 10}]}
        }
        service.events().insert(calendarId="primary", body=event).execute()
        return f"Event created: '{title}' on {start_dt.strftime('%B %d at %I:%M %p')}!"
    except Exception as e:
        return f"Calendar create error: {e}"


@app.route("/api/todos", methods=["GET"])
def get_todos(): return jsonify(load_todos())

@app.route("/api/todos", methods=["POST"])
def add_todo():
    data = request.get_json(force=True,silent=True) or {}
    todos = load_todos()
    todos.append({"id":str(time.time()),"text":data.get("text",""),"done":False,"created":datetime.now().isoformat()})
    save_todos(todos)
    return jsonify({"ok":True})

@app.route("/api/settings", methods=["GET"])
def get_settings_route():
    return jsonify(SETTINGS)

@app.route("/api/settings", methods=["POST"])
def save_settings_route():
    global SETTINGS
    data = request.get_json(force=True, silent=True) or {}
    SETTINGS.update(data)
    save_settings(SETTINGS)
    return jsonify({"ok": True})

@app.route("/api/todos/<tid>", methods=["DELETE"])
def del_todo(tid):
    todos = [t for t in load_todos() if t["id"] != tid]
    save_todos(todos)
    return jsonify({"ok":True})

@app.route("/api/todos/<tid>/done", methods=["POST"])
def done_todo(tid):
    todos = load_todos()
    for t in todos:
        if t["id"] == tid: t["done"] = not t["done"]
    save_todos(todos)
    return jsonify({"ok":True})

# CLASS MODE
@app.route("/api/google/connect", methods=["POST"])
def google_connect():
    try:
        creds = get_google_creds(force_refresh=True)
        if creds and creds.valid:
            return jsonify({"ok": True, "message": "Google connected!"})
        return jsonify({"ok": False, "message": "Connection failed. Check credentials.json"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})

@app.route("/api/google/disconnect", methods=["POST"])
def google_disconnect():
    msg = disconnect_google()
    return jsonify({"ok": True, "message": msg})

@app.route("/api/skills", methods=["GET"])
def get_skills():
    return jsonify(list(SKILLS.values()))

@app.route("/api/skills/<name>", methods=["DELETE"])
def delete_skill(name):
    if name.lower() in SKILLS:
        del SKILLS[name.lower()]
        save_skills(SKILLS)
        return jsonify({"ok": True})
    return jsonify({"error": "Not found"}), 404

@app.route("/api/skills/<name>/run", methods=["POST"])
def run_skill_route(name):
    data = request.get_json(force=True, silent=True) or {}
    result = run_skill(name, data.get("extra", ""))
    return jsonify({"result": result})

@app.route("/api/google/status", methods=["GET"])
def google_status():
    connected = is_google_connected()
    return jsonify({"connected": connected})

@app.route("/api/class_mode", methods=["POST"])
def toggle_class():
    global CLASS_MODE
    data = request.get_json(force=True,silent=True) or {}
    CLASS_MODE = data.get("enabled", not CLASS_MODE)
    return jsonify({"class_mode": CLASS_MODE})

# IMPORT CHAT
@app.route("/api/import_chat", methods=["POST"])
def import_chat():
    try:
        data = request.get_json(force=True,silent=True) or {}
        content = data.get("content","")
        if not content: return jsonify({"error":"No content"}),400
        MEM.setdefault("imported",[]).append({"content":content[:2000],"time":datetime.now().isoformat()})
        save_mem(MEM)
        return jsonify({"ok":True,"message":"Imported! I'll learn from this."})
    except Exception as e:
        return jsonify({"error":str(e)}),500

@sio.on("connect")
def on_connect(): print("  Browser connected")

# ── HTML UI ───────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>JARVIS</title>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@300;400&display=swap" rel="stylesheet">
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{
  --bg:#05050a;--bg2:#08080f;--bg3:#0d0d16;
  --c1:#8b5cf6;--c1g:rgba(139,92,246,.15);
  --c2:#06b6d4;--c2g:rgba(6,182,212,.12);
  --c3:#f59e0b;--c4:#10b981;--c5:#f43f5e;
  --text:#f8fafc;--dim:rgba(255,255,255,.4);--dim2:rgba(255,255,255,.2);
  --card:rgba(255,255,255,.04);--border:rgba(255,255,255,.07);
  --sidebar:220px;
}
html,body{height:100%;overflow:hidden;max-height:100vh}
body{background:var(--bg);font-family:'Space Grotesk',sans-serif;display:flex;color:var(--text);height:100vh;overflow:hidden}

/* SIDEBAR */
.sidebar{
  width:var(--sidebar);min-width:var(--sidebar);
  background:var(--bg2);border-right:1px solid var(--border);
  display:flex;flex-direction:column;justify-content:space-between;
  height:100vh;overflow:hidden;z-index:5;
  transition:width .3s ease;
}
.sidebar-logo{
  padding:18px 16px 14px;
  font-size:13px;font-weight:700;letter-spacing:3px;
  background:linear-gradient(90deg,var(--c1),var(--c2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;
  border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
}
.new-chat-btn{
  margin:10px 12px;padding:9px 14px;
  background:linear-gradient(135deg,var(--c1g),var(--c2g));
  border:1px solid rgba(139,92,246,.3);border-radius:10px;
  color:#c4b5fd;font-size:12px;font-weight:600;letter-spacing:.5px;
  cursor:pointer;transition:all .2s;text-align:center;
}
.new-chat-btn:hover{background:linear-gradient(135deg,rgba(139,92,246,.25),rgba(6,182,212,.2));border-color:rgba(139,92,246,.5)}
.sidebar-section{padding:8px 12px 4px;font-size:9px;letter-spacing:2px;color:var(--dim2);font-family:'JetBrains Mono',monospace}
.chat-list{flex:1;overflow-y:auto;padding:4px 8px;scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.08) transparent}
.chat-item{
  padding:9px 10px;border-radius:8px;cursor:pointer;
  font-size:12px;color:var(--dim);transition:all .2s;
  display:flex;align-items:center;gap:8px;margin-bottom:2px;
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
}
.chat-item:hover{background:var(--card);color:var(--text)}
.chat-item.active{background:var(--c1g);color:#c4b5fd;border-left:2px solid var(--c1)}
.chat-item-icon{font-size:11px;opacity:.6;flex-shrink:0}
.chat-item-del{margin-left:auto;opacity:0;font-size:10px;color:var(--c5);padding:2px 4px;border-radius:3px;flex-shrink:0}
.chat-item:hover .chat-item-del{opacity:.6}
.chat-item-del:hover{opacity:1!important;background:rgba(244,63,94,.15)}

/* Sidebar nav buttons */
.nav-btns{padding:8px;border-top:1px solid var(--border);display:flex;flex-direction:column;gap:4px;flex-shrink:0}
.nav-btn{
  padding:8px 12px;border-radius:8px;cursor:pointer;
  font-size:12px;color:var(--dim);transition:all .2s;
  display:flex;align-items:center;gap:10px;
  white-space:nowrap;
}
.nav-btn:hover{background:var(--card);color:var(--text)}
.nav-btn.active{background:var(--c1g);color:#c4b5fd}

/* MAIN AREA */
.main{flex:1;display:grid;grid-template-rows:52px 1fr 90px;overflow:hidden;min-width:0}

/* TOPBAR */
.topbar{
  display:flex;align-items:center;justify-content:space-between;
  padding:0 20px;background:rgba(5,5,10,.9);
  border-bottom:1px solid var(--border);backdrop-filter:blur(20px);z-index:10;
}
.topbar-left{display:flex;align-items:center;gap:12px}
.status-pill{display:flex;align-items:center;gap:7px;padding:5px 12px;background:var(--card);border:1px solid var(--border);border-radius:20px;font-size:11px;font-weight:500;letter-spacing:1px;color:var(--dim);text-transform:uppercase}
.dot{width:6px;height:6px;border-radius:50%;background:var(--c2);box-shadow:0 0 8px var(--c2);transition:all .4s;animation:blink 2s infinite}
.dot.listening{background:var(--c2);box-shadow:0 0 14px var(--c2);animation:blink .5s infinite}
.dot.thinking{background:var(--c3);box-shadow:0 0 14px var(--c3);animation:blink .3s infinite}
.dot.speaking{background:var(--c4);box-shadow:0 0 14px var(--c4);animation:none}
.convo-pill{padding:4px 10px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:20px;font-size:9px;letter-spacing:2px;color:var(--c3);display:none}
.convo-pill.show{display:block}
.topbar-right{display:flex;align-items:center;gap:12px}
.datetime-box{
  font-family:'JetBrains Mono',monospace;
  text-align:right;line-height:1.4;
}
.time-big{font-size:20px;font-weight:700;letter-spacing:1px;background:linear-gradient(90deg,var(--c1),var(--c2));-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.date-small{font-size:9px;color:var(--dim2);letter-spacing:1px}
.theme-btn{padding:5px 10px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--dim);font-size:11px;cursor:pointer;transition:all .2s}
.theme-btn:hover{color:var(--text);border-color:rgba(139,92,246,.4)}
.stop-btn{padding:5px 12px;background:rgba(244,63,94,.1);border:1px solid rgba(244,63,94,.3);border-radius:8px;color:var(--c5);font-size:11px;cursor:pointer;transition:all .2s;display:none}
.stop-btn.show{display:block}
.stop-btn:hover{background:rgba(244,63,94,.2)}

/* CONTENT AREA */
.content-area{display:grid;grid-template-columns:1fr 300px;overflow:hidden;min-height:0}

/* CHAT */
.chat-panel{display:flex;flex-direction:column;overflow:hidden;border-right:1px solid var(--border)}
.chat-messages{
  flex:1;overflow-y:auto;overflow-x:hidden;
  padding:20px 24px;
  display:flex;flex-direction:column;gap:20px;
  scrollbar-width:thin;scrollbar-color:rgba(255,255,255,.08) transparent;
  min-height:0;scroll-behavior:smooth;
}
.chat-messages::-webkit-scrollbar{width:4px}
.chat-messages::-webkit-scrollbar-thumb{background:rgba(255,255,255,.1);border-radius:4px}

/* Messages */
.msg{display:flex;gap:12px;max-width:100%;animation:msg-in .3s ease}
.msg.user{flex-direction:row-reverse}
.msg-avatar{
  width:32px;height:32px;border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  font-size:13px;flex-shrink:0;margin-top:2px;
}
.msg.jarvis .msg-avatar{background:linear-gradient(135deg,var(--c1),var(--c2));box-shadow:0 0 12px rgba(139,92,246,.3)}
.msg.user .msg-avatar{background:rgba(255,255,255,.08);border:1px solid var(--border)}
.msg-content{flex:1;min-width:0}
.msg-header{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.msg.user .msg-header{flex-direction:row-reverse}
.msg-name{font-size:12px;font-weight:600;color:var(--dim)}
.msg.jarvis .msg-name{color:#a78bfa}
.msg-time2{font-size:10px;color:var(--dim2);font-family:'JetBrains Mono',monospace}
.msg-text{
  font-size:14px;line-height:1.75;color:var(--text);
  word-break:break-word;
}
.msg.user .msg-text{
  background:rgba(139,92,246,.1);border:1px solid rgba(139,92,246,.18);
  padding:12px 16px;border-radius:16px 4px 16px 16px;
  color:rgba(255,255,255,.85);
}
.msg.jarvis .msg-text{
  padding:0;
}
/* Link styling */
.msg-text a{color:var(--c2);text-decoration:underline;text-underline-offset:2px;cursor:pointer}
.msg-text a:hover{color:#67e8f9}
/* Open tab button */
.open-tab-btn{
  display:inline-flex;align-items:center;gap:6px;
  margin-top:8px;padding:6px 12px;
  background:rgba(6,182,212,.1);border:1px solid rgba(6,182,212,.25);
  border-radius:8px;color:var(--c2);font-size:12px;cursor:pointer;
  transition:all .2s;text-decoration:none;
}
.open-tab-btn:hover{background:rgba(6,182,212,.2)}
/* Image result */
.img-result{
  margin-top:10px;padding:10px 14px;
  background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.2);
  border-radius:10px;
}
.img-result-title{font-size:11px;color:var(--c4);margin-bottom:6px;letter-spacing:.5px}
.img-result-link{color:var(--c4);font-size:12px;text-decoration:underline;cursor:pointer}

/* Typing indicator */
.typing-msg .msg-text{padding:12px 16px;background:rgba(139,92,246,.06);border:1px solid rgba(139,92,246,.12);border-radius:4px 16px 16px 16px}
.typing{display:flex;gap:5px;align-items:center}
.typing span{width:7px;height:7px;border-radius:50%;background:var(--c1);opacity:.6;animation:typing-dot 1.2s ease-in-out infinite}
.typing span:nth-child(2){animation-delay:.2s}
.typing span:nth-child(3){animation-delay:.4s}

/* File upload drop zone */
.drop-zone{
  padding:10px 24px;border-top:1px solid var(--border);
  display:none;align-items:center;justify-content:center;
  background:rgba(139,92,246,.05);border-top:2px dashed rgba(139,92,246,.3);
  color:var(--dim);font-size:12px;gap:8px;
}
.drop-zone.visible{display:flex}
.file-chip{
  display:inline-flex;align-items:center;gap:6px;
  padding:4px 10px;background:var(--c1g);border:1px solid rgba(139,92,246,.3);
  border-radius:20px;font-size:11px;color:#c4b5fd;margin:4px;cursor:pointer;
}
.file-chip:hover{background:rgba(139,92,246,.25)}
.attached-files{padding:6px 24px;display:flex;flex-wrap:wrap;gap:4px;display:none}
.attached-files.visible{display:flex}

/* ORB PANEL */
.orb-panel{
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:20px;padding:20px;overflow:hidden;
  background:rgba(5,5,10,.4);
}
.orb-wrap{position:relative;width:200px;height:200px;display:flex;align-items:center;justify-content:center}
.ring{position:absolute;border-radius:50%}
.ring-1{width:198px;height:198px;border:1px solid transparent;background:linear-gradient(var(--bg),var(--bg)) padding-box,conic-gradient(from 0deg,var(--c1),var(--c2),var(--c4),var(--c5),var(--c1)) border-box;animation:spin 8s linear infinite;opacity:.45}
.ring-2{width:174px;height:174px;border:1px dashed rgba(139,92,246,.2);animation:spin 5s linear infinite reverse}
.ping{position:absolute;width:140px;height:140px;border-radius:50%;border:2px solid var(--c2);opacity:0;pointer-events:none}
.ping.active{animation:ping-out 2s ease-out infinite}
.ping:nth-child(2){animation-delay:.7s}.ping:nth-child(3){animation-delay:1.4s}
.orb{width:140px;height:140px;border-radius:50%;background:radial-gradient(circle at 38% 35%,#130f2e,#04030f);border:2px solid rgba(139,92,246,.3);display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden;transition:all .6s ease;box-shadow:0 0 40px rgba(139,92,246,.1),inset 0 0 30px rgba(0,0,0,.6)}
.orb.listening{border-color:rgba(6,182,212,.8);box-shadow:0 0 60px rgba(6,182,212,.25),inset 0 0 30px rgba(0,12,24,.7)}
.orb.thinking{border-color:rgba(245,158,11,.7);box-shadow:0 0 60px rgba(245,158,11,.2),inset 0 0 30px rgba(25,15,0,.7)}
.orb.speaking{border-color:rgba(16,185,129,.7);box-shadow:0 0 60px rgba(16,185,129,.2),inset 0 0 30px rgba(0,18,12,.7)}
#wv{position:absolute;inset:0;width:100%;height:100%;border-radius:50%}
.core{width:12px;height:12px;border-radius:50%;background:radial-gradient(circle,#fff,var(--c1));box-shadow:0 0 18px var(--c1);z-index:2;animation:core-pulse 2.5s ease-in-out infinite;transition:all .4s}
.orb.listening .core{background:radial-gradient(circle,#fff,var(--c2));box-shadow:0 0 18px var(--c2)}
.orb.thinking .core{background:radial-gradient(circle,#fff,var(--c3));box-shadow:0 0 18px var(--c3);animation:core-pulse .4s ease-in-out infinite}
.orb.speaking .core{background:radial-gradient(circle,#fff,var(--c4));box-shadow:0 0 18px var(--c4)}
.state-label{font-size:10px;letter-spacing:3px;font-weight:500;color:var(--dim);text-transform:uppercase;font-family:'JetBrains Mono',monospace}
.mic-row{display:flex;gap:10px;align-items:center}
.mic-btn{width:48px;height:48px;border-radius:50%;background:var(--card);border:1px solid var(--border);display:flex;align-items:center;justify-content:center;cursor:pointer;transition:all .3s;font-size:18px;color:var(--dim)}
.mic-btn.active{background:rgba(6,182,212,.15);border-color:rgba(6,182,212,.5);color:var(--c2);box-shadow:0 0 20px rgba(6,182,212,.2);animation:mic-pulse 1s ease-in-out infinite}
.mic-btn:hover:not(.active){background:rgba(255,255,255,.07);color:var(--text)}
.convo-btn{padding:7px 14px;border-radius:20px;background:var(--card);border:1px solid var(--border);color:var(--dim);font-size:11px;font-weight:500;cursor:pointer;transition:all .3s;font-family:'Space Grotesk',sans-serif}
.convo-btn.active{background:rgba(245,158,11,.1);border-color:rgba(245,158,11,.4);color:var(--c3)}

/* INPUT */
.input-area{
  grid-column:1/-1;
  padding:12px 20px;
  border-top:1px solid var(--border);
  background:rgba(5,5,10,.95);backdrop-filter:blur(20px);
}
.input-row{display:flex;gap:8px;align-items:flex-end}
.inp-wrap{flex:1;position:relative}
.inp{
  width:100%;background:rgba(255,255,255,.05);
  border:1px solid var(--border);border-radius:14px;
  color:#fff;font-family:'Space Grotesk',sans-serif;
  font-size:14px;padding:12px 48px 12px 18px;
  outline:none;transition:border-color .3s;
  resize:none;min-height:44px;max-height:120px;
  line-height:1.5;overflow-y:auto;
}
.inp:focus{border-color:rgba(139,92,246,.4)}
.inp::placeholder{color:rgba(255,255,255,.2)}
.attach-btn{
  position:absolute;right:12px;bottom:12px;
  background:none;border:none;color:var(--dim);
  font-size:16px;cursor:pointer;transition:color .2s;padding:0;
}
.attach-btn:hover{color:var(--c1)}
.send-btn{
  background:linear-gradient(135deg,rgba(139,92,246,.25),rgba(6,182,212,.2));
  border:1px solid rgba(139,92,246,.35);border-radius:12px;
  color:#a78bfa;font-family:'Space Grotesk',sans-serif;
  font-size:13px;font-weight:600;padding:12px 20px;
  cursor:pointer;transition:all .2s;white-space:nowrap;height:44px;
}
.send-btn:hover{background:linear-gradient(135deg,rgba(139,92,246,.4),rgba(6,182,212,.3));transform:translateY(-1px)}
.send-btn:disabled{opacity:.3;cursor:not-allowed;transform:none}

/* NOTES PANEL */
.notes-panel{
  position:fixed;top:0;right:-360px;width:340px;height:100vh;
  background:var(--bg2);border-left:1px solid var(--border);
  z-index:50;transition:right .3s ease;
  display:flex;flex-direction:column;
}
.notes-panel.open{right:0}
.notes-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.notes-header-title{font-size:13px;font-weight:600;letter-spacing:1px;color:var(--c1)}
.notes-close{cursor:pointer;color:var(--dim);font-size:18px;transition:color .2s}
.notes-close:hover{color:var(--text)}
.notes-list{flex:1;overflow-y:auto;padding:12px}
.note-item{
  padding:12px;border-radius:10px;background:var(--card);
  border:1px solid var(--border);margin-bottom:8px;
  font-size:13px;line-height:1.6;color:rgba(255,255,255,.8);
  cursor:pointer;transition:border-color .2s;
}
.note-item:hover{border-color:rgba(139,92,246,.3)}
.note-item-time{font-size:10px;color:var(--dim2);margin-top:6px;font-family:'JetBrains Mono',monospace}
.notes-input-area{padding:12px;border-top:1px solid var(--border)}
.note-textarea{
  width:100%;background:rgba(255,255,255,.04);
  border:1px solid var(--border);border-radius:10px;
  color:#fff;font-family:'Space Grotesk',sans-serif;
  font-size:13px;padding:10px 14px;outline:none;
  resize:none;height:80px;transition:border-color .3s;
}
.note-textarea:focus{border-color:rgba(139,92,246,.4)}
.note-save-btn{
  margin-top:8px;width:100%;padding:8px;
  background:var(--c1g);border:1px solid rgba(139,92,246,.3);
  border-radius:8px;color:#c4b5fd;font-size:12px;font-weight:600;
  cursor:pointer;transition:all .2s;font-family:'Space Grotesk',sans-serif;
}
.note-save-btn:hover{background:rgba(139,92,246,.25)}

/* THEME PICKER */
.theme-dropdown{
  position:absolute;top:56px;right:20px;
  background:var(--bg2);border:1px solid var(--border);
  border-radius:12px;padding:8px;z-index:50;
  display:none;min-width:160px;
  box-shadow:0 8px 32px rgba(0,0,0,.4);
}
.theme-dropdown.open{display:block}
.theme-option{
  padding:8px 12px;border-radius:8px;cursor:pointer;
  font-size:12px;color:var(--dim);transition:all .2s;
  display:flex;align-items:center;gap:10px;
}
.theme-option:hover{background:var(--card);color:var(--text)}
.theme-dot{width:10px;height:10px;border-radius:50%}

/* Credits */
.settings-panel{position:fixed;top:0;right:-360px;width:340px;height:100vh;background:var(--bg2);border-left:1px solid var(--border);z-index:50;transition:right .3s ease;display:flex;flex-direction:column}
.settings-panel.open{right:0}
.settings-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.settings-title{font-size:13px;font-weight:600;letter-spacing:1px;color:var(--c2)}
.settings-close{cursor:pointer;color:var(--dim);font-size:18px;transition:color .2s}
.settings-close:hover{color:var(--text)}
.settings-body{flex:1;overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:16px}
.setting-group{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px}
.setting-label{font-size:11px;letter-spacing:1.5px;color:var(--dim);margin-bottom:8px;font-family:'JetBrains Mono',monospace}
.setting-desc{font-size:11px;color:var(--dim2);margin-bottom:8px;line-height:1.5}
.setting-inp{width:100%;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:8px;color:#fff;font-family:'JetBrains Mono',monospace;font-size:11px;padding:8px 12px;outline:none;transition:border-color .3s}
.setting-inp:focus{border-color:rgba(6,182,212,.4)}
.setting-inp::placeholder{color:rgba(255,255,255,.2)}
.setting-save-btn{margin-top:8px;padding:7px 14px;background:rgba(6,182,212,.1);border:1px solid rgba(6,182,212,.3);border-radius:8px;color:var(--c2);font-size:11px;font-weight:600;cursor:pointer;transition:all .2s;font-family:'Space Grotesk',sans-serif}
.setting-save-btn:hover{background:rgba(6,182,212,.2)}
.setting-status{font-size:10px;color:var(--c4);margin-top:6px;display:none}
.setting-status.show{display:block}
.credits{position:fixed;bottom:10px;right:14px;z-index:5;text-align:right;font-family:'JetBrains Mono',monospace;font-size:8px;letter-spacing:.5px;color:rgba(255,255,255,.12);line-height:2}
.credits a{color:rgba(139,92,246,.4);text-decoration:none;transition:color .2s}
.credits a:hover{color:rgba(139,92,246,.8)}

/* TODO PANEL */
.skills-panel{position:fixed;top:0;left:220px;width:340px;height:100vh;background:var(--bg2);border-right:1px solid var(--border);z-index:50;transition:left .3s ease;display:flex;flex-direction:column;transform:translateX(-100%)}
.skills-panel.open{transform:translateX(0)}
.skills-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.skills-title{font-size:13px;font-weight:600;letter-spacing:1px;color:var(--c3)}
.skills-close{cursor:pointer;color:var(--dim);font-size:18px;transition:color .2s}
.skills-close:hover{color:var(--text)}
.skills-list{flex:1;overflow-y:auto;padding:12px}
.skill-item{padding:12px;border-radius:10px;background:var(--card);border:1px solid var(--border);margin-bottom:8px;cursor:pointer;transition:all .2s}
.skill-item:hover{border-color:rgba(245,158,11,.3);background:rgba(245,158,11,.05)}
.skill-name{font-size:13px;font-weight:600;color:var(--c3);margin-bottom:4px}
.skill-desc{font-size:11px;color:var(--dim);line-height:1.5}
.skill-actions{display:flex;gap:6px;margin-top:8px}
.skill-run-btn{padding:4px 10px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:6px;color:var(--c3);font-size:10px;cursor:pointer;transition:all .2s}
.skill-run-btn:hover{background:rgba(245,158,11,.2)}
.skill-del-btn{padding:4px 10px;background:rgba(244,63,94,.08);border:1px solid rgba(244,63,94,.2);border-radius:6px;color:#f87171;font-size:10px;cursor:pointer;transition:all .2s}
.skill-del-btn:hover{background:rgba(244,63,94,.15)}
.skills-create-area{padding:12px;border-top:1px solid var(--border)}
.skills-create-inp{width:100%;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;color:#fff;font-family:"Space Grotesk",sans-serif;font-size:12px;padding:8px 12px;outline:none;margin-bottom:6px;transition:border-color .3s}
.skills-create-inp:focus{border-color:rgba(245,158,11,.4)}
.skills-create-inp::placeholder{color:rgba(255,255,255,.2)}
.skill-create-btn{width:100%;padding:8px;background:rgba(245,158,11,.1);border:1px solid rgba(245,158,11,.3);border-radius:8px;color:var(--c3);font-size:12px;font-weight:600;cursor:pointer;transition:all .2s;font-family:"Space Grotesk",sans-serif}
.skill-create-btn:hover{background:rgba(245,158,11,.2)}
.todo-panel{position:fixed;top:0;right:-360px;width:340px;height:100vh;background:var(--bg2);border-left:1px solid var(--border);z-index:50;transition:right .3s ease;display:flex;flex-direction:column}
.todo-panel.open{right:0}
.todo-header{padding:16px 18px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between}
.todo-header-title{font-size:13px;font-weight:600;letter-spacing:1px;color:var(--c4)}
.todo-close{cursor:pointer;color:var(--dim);font-size:18px;transition:color .2s}
.todo-close:hover{color:var(--text)}
.todo-list{flex:1;overflow-y:auto;padding:12px}
.todo-item{display:flex;align-items:center;gap:10px;padding:10px 12px;border-radius:10px;background:var(--card);border:1px solid var(--border);margin-bottom:6px;transition:border-color .2s}
.todo-item.done .todo-text{text-decoration:line-through;opacity:.4}
.todo-check{width:18px;height:18px;border-radius:50%;border:2px solid var(--c4);cursor:pointer;display:flex;align-items:center;justify-content:center;flex-shrink:0;transition:all .2s}
.todo-item.done .todo-check{background:var(--c4);border-color:var(--c4)}
.todo-text{flex:1;font-size:13px;line-height:1.5}
.todo-del{font-size:11px;color:var(--c5);cursor:pointer;opacity:.4;transition:opacity .2s}
.todo-del:hover{opacity:1}
.todo-input-area{padding:12px;border-top:1px solid var(--border);display:flex;gap:8px}
.todo-inp{flex:1;background:rgba(255,255,255,.04);border:1px solid var(--border);border-radius:10px;color:#fff;font-family:'Space Grotesk',sans-serif;font-size:13px;padding:9px 14px;outline:none;transition:border-color .3s}
.todo-inp:focus{border-color:rgba(16,185,129,.4)}
.todo-inp::placeholder{color:rgba(255,255,255,.2)}
.todo-add-btn{padding:9px 14px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);border-radius:10px;color:var(--c4);font-size:13px;cursor:pointer;transition:all .2s}
.todo-add-btn:hover{background:rgba(16,185,129,.2)}

/* NOTIFICATION TOAST */
.toast-container{position:fixed;top:70px;right:20px;z-index:100;display:flex;flex-direction:column;gap:8px;max-width:320px}
.toast{
  padding:12px 16px;border-radius:12px;
  background:var(--bg2);border:1px solid rgba(139,92,246,.3);
  font-size:13px;line-height:1.5;color:var(--text);
  box-shadow:0 8px 32px rgba(0,0,0,.4);
  animation:toast-in .3s ease;cursor:pointer;
}
.toast:hover{border-color:rgba(139,92,246,.6)}
@keyframes toast-in{from{opacity:0;transform:translateX(20px)}to{opacity:1;transform:translateX(0)}}

/* CLASS MODE indicator */
.class-pill{padding:4px 10px;background:rgba(16,185,129,.1);border:1px solid rgba(16,185,129,.3);border-radius:20px;font-size:9px;letter-spacing:2px;color:var(--c4);display:none}
.class-pill.show{display:block}

/* Import button */
.import-btn{padding:5px 10px;background:var(--card);border:1px solid var(--border);border-radius:8px;color:var(--dim);font-size:11px;cursor:pointer;transition:all .2s}
.import-btn:hover{color:var(--text);border-color:rgba(6,182,212,.4)}

/* THEMES */
body.light{--bg:#f8f9fb;--bg2:#f0f1f5;--bg3:#e8eaf0;--text:#1a1a2e;--dim:rgba(0,0,0,.5);--dim2:rgba(0,0,0,.3);--card:rgba(0,0,0,.04);--border:rgba(0,0,0,.08)}
body.genz{--bg:#0a0015;--c1:#ff2d78;--c2:#00fff5;--c3:#ffea00;--c4:#00ff88;--c5:#ff6b00}
body.smooth{--bg:#0f1117;--c1:#60a5fa;--c2:#818cf8;--c3:#a78bfa;--c4:#34d399;--c5:#f87171}

/* ANIMATIONS */
@keyframes spin{to{transform:rotate(360deg)}}
@keyframes core-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.7)}}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}
@keyframes ping-out{0%{transform:scale(1);opacity:.6}100%{transform:scale(2.6);opacity:0}}
@keyframes mic-pulse{0%,100%{box-shadow:0 0 15px rgba(6,182,212,.2)}50%{box-shadow:0 0 30px rgba(6,182,212,.4)}}
@keyframes msg-in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
@keyframes typing-dot{0%,60%,100%{transform:translateY(0)}30%{transform:translateY(-7px)}}
</style>
</head>
<body id="body">

<!-- SIDEBAR -->
<div class="sidebar">
  <div class="sidebar-logo">
    <span>JARVIS</span>
    <span style="font-size:10px;color:var(--dim2);font-family:'JetBrains Mono',monospace;-webkit-text-fill-color:rgba(255,255,255,.3)">AI</span>
  </div>
  <div class="new-chat-btn" onclick="newChat()">+ New Chat</div>
  <div class="sidebar-section">Recent</div>
  <div class="chat-list" id="chatList"></div>
  <div class="nav-btns">
    <div class="nav-btn" id="settingsNavBtn" onclick="toggleSettings()">⚙️ Settings</div>
    <div class="nav-btn" onclick="toggleNotes()" id="notesNavBtn">📝 Notes</div>
    <div class="nav-btn" id="todoNavBtn" onclick="toggleTodo()">✅ To-do</div>
    <div class="nav-btn" id="skillsNavBtn" onclick="toggleSkills()">⚡ Skills</div>
  </div>
</div>

<!-- MAIN -->
<div class="main">
  <!-- TOPBAR -->
  <div class="topbar">
    <div class="topbar-left">
      <div class="status-pill"><div class="dot" id="dot"></div><span id="statusText">STANDBY</span></div>
      <div class="convo-pill" id="convoPill">CONVO MODE</div>
      <div class="class-pill" id="classPill">CLASS MODE</div>
    </div>
    <div class="topbar-right">
      <div class="stop-btn" id="stopBtn" onclick="stopResponse()">⏹ Stop</div>
      <div class="import-btn" onclick="document.getElementById('importFileInput').click()" title="Import chat from ChatGPT/Gemini">⬆ Import</div>
      <input type="file" id="importFileInput" accept=".json,.txt" style="display:none" onchange="importChat(this)">
      <div class="import-btn" id="classModeBtn" onclick="toggleClassMode()">🎓 Class</div>
      <div class="theme-btn" onclick="toggleTheme()" id="themeBtn">🎨 Theme</div>
      <div class="theme-dropdown" id="themeDropdown">
        <div class="theme-option" onclick="setTheme('dark')"><div class="theme-dot" style="background:#8b5cf6"></div>Dark</div>
        <div class="theme-option" onclick="setTheme('genz')"><div class="theme-dot" style="background:#ff2d78"></div>Gen Z</div>
        <div class="theme-option" onclick="setTheme('smooth')"><div class="theme-dot" style="background:#60a5fa"></div>Smooth</div>
        <div class="theme-option" onclick="setTheme('light')"><div class="theme-dot" style="background:#f0f1f5;border:1px solid #ccc"></div>Light</div>
      </div>
      <div class="datetime-box">
        <div class="time-big" id="timeBig">00:00</div>
        <div class="date-small" id="dateSm">Loading...</div>
      </div>
    </div>
  </div>

  <!-- CONTENT -->
  <div class="content-area">
    <!-- CHAT PANEL -->
    <div class="chat-panel">
      <div class="chat-messages" id="chatMessages">
        <div class="msg jarvis">
          <div class="msg-avatar">J</div>
          <div class="msg-content">
            <div class="msg-header"><span class="msg-name">JARVIS</span><span class="msg-time2" id="welcomeTime"></span></div>
            <div class="msg-text">What's up boss. I'm online. Say something or type — I'm ready.</div>
          </div>
        </div>
      </div>
      <div class="attached-files" id="attachedFiles"></div>
      <div class="drop-zone" id="dropZone">📎 Drop files here or click to attach</div>
    </div>

    <!-- ORB PANEL -->
    <div class="orb-panel">
      <div class="orb-wrap">
        <div class="ping" id="p1"></div><div class="ping" id="p2"></div><div class="ping" id="p3"></div>
        <div class="ring ring-1"></div><div class="ring ring-2"></div>
        <div class="orb" id="orb">
          <canvas id="wv"></canvas>
          <div class="core" id="core"></div>
        </div>
      </div>
      <div class="state-label" id="stateLabel">CLICK MIC</div>
      <div class="mic-row">
        <div class="mic-btn" id="micBtn" onclick="toggleMic()">🎤</div>
        <div class="convo-btn" id="convoBtn" onclick="toggleConvo()">CONVO</div>
      </div>
    </div>
  </div>

  <!-- INPUT -->
  <div class="input-area">
    <div class="input-row">
      <div class="inp-wrap">
        <textarea class="inp" id="inp" placeholder='Type or say "JARVIS..."' rows="1"></textarea>
        <button class="attach-btn" onclick="document.getElementById('fileInput').click()">📎</button>
        <input type="file" id="fileInput" multiple style="display:none" onchange="handleFiles(this.files)">
      </div>
      <button class="send-btn" id="sendBtn" onclick="sendMsg()">Send ↑</button>
    </div>
  </div>
</div>

<!-- NOTES PANEL -->
<div class="notes-panel" id="notesPanel">
  <div class="notes-header">
    <span class="notes-header-title">📝 NOTES</span>
    <span class="notes-close" onclick="toggleNotes()">✕</span>
  </div>
  <div class="notes-list" id="notesList"></div>
  <div class="notes-input-area">
    <textarea class="note-textarea" id="noteInput" placeholder="Write a note, idea, or reminder..."></textarea>
    <button class="note-save-btn" onclick="saveNote()">Save Note</button>
  </div>
</div>

<!-- SKILLS PANEL -->
<div class="skills-panel" id="skillsPanel">
  <div class="skills-header">
    <span class="skills-title">⚡ SKILLS</span>
    <span class="skills-close" onclick="toggleSkills()">✕</span>
  </div>
  <div class="skills-list" id="skillsList"></div>
  <div class="skills-create-area">
    <input class="skills-create-inp" id="skillNameInp" placeholder="Skill name (e.g. morning routine)">
    <input class="skills-create-inp" id="skillDescInp" placeholder="What it does (e.g. check weather, open YouTube, read calendar)">
    <button class="skill-create-btn" onclick="createSkill()">+ Create Skill</button>
  </div>
</div>

<!-- TODO PANEL -->
<div class="todo-panel" id="todoPanel">
  <div class="todo-header">
    <span class="todo-header-title">✅ TO-DO</span>
    <span class="todo-close" onclick="toggleTodo()">✕</span>
  </div>
  <div class="todo-list" id="todoList"></div>
  <div class="todo-input-area">
    <input class="todo-inp" id="todoInp" placeholder="Add a task..." onkeydown="if(event.key==='Enter')addTodo()">
    <button class="todo-add-btn" onclick="addTodo()">+</button>
  </div>
</div>

<!-- TOAST CONTAINER -->
<div class="toast-container" id="toastContainer"></div>

<!-- SETTINGS PANEL -->
<div class="settings-panel" id="settingsPanel">
  <div class="settings-header">
    <span class="settings-title">⚙️ SETTINGS</span>
    <span class="settings-close" onclick="toggleSettings()">✕</span>
  </div>
  <div class="settings-body">
    <div class="setting-group">
      <div class="setting-label">CHROME PROFILE</div>
      <div class="setting-desc">Go to chrome://version → find Profile Path → copy just the last folder name e.g. "Default" or "Profile 1"</div>
      <input class="setting-inp" id="chromeProfileInp" placeholder="Default or Profile 1">
      <button class="setting-save-btn" onclick="saveSetting('chrome_profile','chromeProfileInp','profileStatus')">Save Profile</button>
      <div class="setting-status" id="profileStatus">✓ Saved!</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">CHROME PATH</div>
      <div class="setting-desc">Full path to Chrome executable. Change this if you switch computers.</div>
      <input class="setting-inp" id="chromePathInp" placeholder="C:/Program Files/Google/Chrome/Application/chrome.exe">
      <button class="setting-save-btn" onclick="saveSetting('chrome_path','chromePathInp','chromeStatus')">Save Path</button>
      <div class="setting-status" id="chromeStatus">✓ Saved!</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">AI API KEY</div>
      <div class="setting-desc">Change your AI key. Supports Groq, Gemini, OpenRouter, Cohere, Anthropic.</div>
      <input class="setting-inp" id="aiKeyInp" placeholder="Paste new API key..." type="password">
      <button class="setting-save-btn" onclick="saveApiKey()">Update Key</button>
      <div class="setting-status" id="keyStatus">✓ Saved!</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">TAVILY SEARCH KEY</div>
      <div class="setting-desc">For web search. Get free key at app.tavily.com</div>
      <input class="setting-inp" id="tavilyInp" placeholder="tvly-..." type="password">
      <button class="setting-save-btn" onclick="saveSetting('tavily_key','tavilyInp','tavilyStatus')">Update Key</button>
      <div class="setting-status" id="tavilyStatus">✓ Saved!</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">GOOGLE ACCOUNT</div>
      <div class="setting-desc">Connect Gmail, Drive and Calendar. Put credentials.json in same folder as JARVIS.py first.</div>
      <div id="googleStatus" style="font-size:11px;color:rgba(255,255,255,.4);margin-bottom:8px">Checking...</div>
      <div style="display:flex;gap:8px">
        <button class="setting-save-btn" style="flex:1" onclick="connectGoogle()">Connect Google</button>
        <button class="setting-save-btn" style="flex:1;background:rgba(244,63,94,.1);border-color:rgba(244,63,94,.3);color:#f87171" onclick="disconnectGoogle()">Disconnect</button>
      </div>
      <div class="setting-status" id="googleConnStatus">Done!</div>
    </div>
    <div class="setting-group">
      <div class="setting-label">YOUR NAME</div>
      <div class="setting-desc">What JARVIS calls you.</div>
      <input class="setting-inp" id="nameInp" placeholder="Chattychop">
      <button class="setting-save-btn" onclick="saveSetting('user_name','nameInp','nameStatus')">Save</button>
      <div class="setting-status" id="nameStatus">✓ Saved!</div>
    </div>

  </div>
</div>

<!-- Credits -->
<div class="credits">
  <a href="https://youtube.com/@chattychop" target="_blank">yt @chattychop</a><br>
  created by badrinath g
</div>

<script>
// ── STATE ──────────────────────────────────────────────────────────────────
let orbState = 'idle';
let micActive = false;
let convoMode = false;
let recognition = null;
let currentTheme = 'dark';
let waf, wt = 0;
let audioCtx, analyser, micStream;
let sending = false;
let stopController = null;
let attachedFiles = [];
let notes = JSON.parse(localStorage.getItem('jarvis_notes') || '[]');

// DOM
const orb = document.getElementById('orb');
const dot = document.getElementById('dot');
const stateLabel = document.getElementById('stateLabel');
const statusText = document.getElementById('statusText');
const micBtn = document.getElementById('micBtn');
const convoBtn = document.getElementById('convoBtn');
const convoPill = document.getElementById('convoPill');
const stopBtn = document.getElementById('stopBtn');
const chatMessages = document.getElementById('chatMessages');
const p1 = document.getElementById('p1'), p2 = document.getElementById('p2'), p3 = document.getElementById('p3');
const cv = document.getElementById('wv'), cx = cv.getContext('2d');

function resizeCv() { cv.width = cv.offsetWidth; cv.height = cv.offsetHeight; }
resizeCv(); window.addEventListener('resize', resizeCv);

// ── CLOCK ─────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  let h = now.getHours();
  const ampm = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  const m = now.getMinutes().toString().padStart(2,'0');
  const s = now.getSeconds().toString().padStart(2,'0');
  document.getElementById('timeBig').textContent = `${h}:${m}:${s} ${ampm}`;
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  document.getElementById('dateSm').textContent = `${days[now.getDay()]} ${now.getDate()} ${months[now.getMonth()]} ${now.getFullYear()}`;
  document.getElementById('welcomeTime').textContent = `${h}:${m}`;
}
updateClock(); setInterval(updateClock, 1000);

// ── THEME ─────────────────────────────────────────────────────────────────
function setTheme(t) {
  currentTheme = t;
  document.getElementById('body').className = t === 'dark' ? '' : t;
  document.getElementById('themeDropdown').classList.remove('open');
  localStorage.setItem('jarvis_theme', t);
}
function toggleTheme() { document.getElementById('themeDropdown').classList.toggle('open'); }
document.addEventListener('click', e => { if (!e.target.closest('.theme-btn') && !e.target.closest('.theme-dropdown')) document.getElementById('themeDropdown').classList.remove('open'); });
const savedTheme = localStorage.getItem('jarvis_theme');
if (savedTheme) setTheme(savedTheme);

// ── ORB STATE ─────────────────────────────────────────────────────────────
function setState(s) {
  orbState = s;
  orb.className = 'orb ' + s;
  dot.className = 'dot ' + s;
  const labels = { idle:'READY', listening:'LISTENING', thinking:'THINKING', speaking:'SPEAKING' };
  stateLabel.textContent = labels[s] || s.toUpperCase();
  statusText.textContent = labels[s] || s.toUpperCase();
  [p1,p2,p3].forEach(p => s === 'listening' ? p.classList.add('active') : p.classList.remove('active'));
  if (s === 'idle') drawIdle();
  if (s === 'thinking') drawThink();
  if (s === 'speaking') drawSpeak();
}

// ── ORB ANIMATIONS ────────────────────────────────────────────────────────
function drawIdle() {
  cancelAnimationFrame(waf);
  const W = cv.width, H = cv.height;
  (function f() {
    cx.clearRect(0,0,W,H); const ox=W/2,oy=H/2; wt+=.01;
    for (let r=0;r<5;r++) {
      const rad=20+r*13,amp=2+r*.8;
      cx.beginPath();
      for (let a=0;a<=Math.PI*2;a+=.05) { const n=amp*Math.sin(a*3+wt+r*1.4)*Math.sin(a*5-wt*.7+r*.5); cx.lineTo(ox+(rad+n)*Math.cos(a),oy+(rad+n)*Math.sin(a)); }
      cx.closePath(); cx.strokeStyle=`rgba(139,92,246,${.04+r*.025})`; cx.lineWidth=.8; cx.stroke();
    } waf=requestAnimationFrame(f);
  })();
}
function drawThink() {
  cancelAnimationFrame(waf);
  const W=cv.width,H=cv.height; let t=0;
  (function f() {
    cx.clearRect(0,0,W,H); const ox=W/2,oy=H/2; t+=.06;
    for (let r=0;r<6;r++) {
      const rad=12+r*11;
      cx.beginPath();
      for (let a=0;a<=Math.PI*2;a+=.04) { const n=8*Math.sin(a*4+t*3+r*1.2)*Math.cos(a*2-t*1.5+r); cx.lineTo(ox+(rad+n)*Math.cos(a),oy+(rad+n)*Math.sin(a)); }
      cx.closePath(); cx.strokeStyle=`rgba(245,158,11,${.04+r*.035})`; cx.lineWidth=1; cx.stroke();
    } waf=requestAnimationFrame(f);
  })();
}
function drawSpeak() {
  cancelAnimationFrame(waf);
  const W=cv.width,H=cv.height; let t=0;
  (function f() {
    cx.clearRect(0,0,W,H); const ox=W/2,oy=H/2; t+=.08;
    for (let r=0;r<6;r++) {
      const rad=12+r*12,amp=9+r*3.5;
      cx.beginPath();
      for (let a=0;a<=Math.PI*2;a+=.04) { const n=amp*Math.sin(a*7+t*4+r*1.8)*(.5+.5*Math.sin(t*2+r)); cx.lineTo(ox+(rad+n)*Math.cos(a),oy+(rad+n)*Math.sin(a)); }
      cx.closePath(); cx.strokeStyle=`rgba(16,185,129,${.06+r*.04})`; cx.lineWidth=1.2; cx.stroke();
    } waf=requestAnimationFrame(f);
  })();
}
function drawMicWave() {
  const W=cv.width,H=cv.height; const buf=new Uint8Array(analyser.frequencyBinCount);
  (function f() {
    if (orbState!=='listening') { stopMic(); return; }
    analyser.getByteTimeDomainData(buf);
    const avg=buf.reduce((a,b)=>a+Math.abs(b-128),0)/buf.length;
    cx.clearRect(0,0,W,H); const ox=W/2,oy=H/2;
    for (let r=0;r<6;r++) {
      const rad=14+r*11,sc=(1+avg*.1)*(1+r*.15);
      cx.beginPath();
      for (let i=0;i<=buf.length;i++) { const a=(i/buf.length)*Math.PI*2,n=((buf[i]-128)/128)*11*sc; cx.lineTo(ox+(rad+n)*Math.cos(a),oy+(rad+n)*Math.sin(a)); }
      cx.closePath(); cx.strokeStyle=`rgba(6,182,212,${.05+r*.05+avg*.005})`; cx.lineWidth=1; cx.stroke();
    } waf=requestAnimationFrame(f);
  })();
}

// ── MIC ───────────────────────────────────────────────────────────────────
async function startMicViz() {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    analyser = audioCtx.createAnalyser(); analyser.fftSize = 256;
    audioCtx.createMediaStreamSource(stream).connect(analyser);
    micStream = stream; cancelAnimationFrame(waf); drawMicWave();
  } catch(e) { drawIdle(); }
}
function stopMic() {
  if (micStream) { micStream.getTracks().forEach(t=>t.stop()); micStream=null; }
  if (audioCtx) { audioCtx.close().catch(()=>{}); audioCtx=null; }
}

// ── SPEECH RECOGNITION ────────────────────────────────────────────────────
function setupRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { stateLabel.textContent = 'USE CHROME FOR VOICE'; return null; }
  const r = new SR();
  r.lang = 'en-IN'; r.interimResults = true; r.continuous = convoMode;
  r.onstart = () => { setState('listening'); micBtn.classList.add('active'); startMicViz(); };
  r.onresult = e => {
    let interim='', final='';
    for (let i=e.resultIndex;i<e.results.length;i++) {
      if (e.results[i].isFinal) final += e.results[i][0].transcript;
      else interim += e.results[i][0].transcript;
    }
    if (interim) stateLabel.textContent = interim.slice(0,35) + (interim.length>35?'...':'');
    if (final) handleVoiceInput(final.trim());
  };
  r.onerror = e => { if (e.error!=='no-speech') { setState('idle'); micBtn.classList.remove('active'); stopMic(); drawIdle(); } };
  r.onend = () => {
    stopMic();
    if (convoMode && micActive) { setTimeout(() => { try { r.start(); } catch(e){} }, 300); }
    else { micActive=false; micBtn.classList.remove('active'); setState('idle'); drawIdle(); }
  };
  return r;
}
function toggleMic() {
  if (!micActive) {
    micActive=true; recognition=setupRecognition();
    if (!recognition) return;
    try { recognition.start(); } catch(e) { micActive=false; micBtn.classList.remove('active'); }
  } else {
    micActive=false;
    if (recognition) try { recognition.stop(); } catch(e) {}
    micBtn.classList.remove('active'); setState('idle'); stopMic(); drawIdle();
  }
}
function toggleConvo() {
  convoMode = !convoMode;
  convoBtn.classList.toggle('active', convoMode);
  convoPill.classList.toggle('show', convoMode);
  if (convoMode && !micActive) { micActive=true; recognition=setupRecognition(); if(recognition) try { recognition.start(); } catch(e){} }
  else if (!convoMode) { micActive=false; if(recognition) try { recognition.stop(); } catch(e){} }
}
function handleVoiceInput(text) {
  if (!text) return;
  const tl = text.toLowerCase();
  if (!convoMode && !tl.startsWith('jarvis')) return;
  const clean = convoMode ? text : text.slice(6).trim();
  if (!clean) { speak("Yeah?"); return; }
  submitMessage(clean);
}

// ── TTS ───────────────────────────────────────────────────────────────────
function speak(text) {
  // Strip markdown, links, technical noise for TTS
  const clean = text
    .replace(/https?:\/\/\S+/g, '')
    .replace(/\*\*/g,'').replace(/\*/g,'').replace(/`/g,'')
    .replace(/\[([^\]]+)\]\([^)]+\)/g,'$1')
    .replace(/IMAGE_SEARCH:[^:]+:/g,'')
    .replace(/SEARCH_OPENED:[^:]+:/g,'')
    .replace(/\n+/g,' ')
    .trim()
    .slice(0, 300); // max 300 chars for TTS

  setState('speaking');
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(clean);
  utt.lang = 'en-GB'; utt.rate = 1.08; utt.pitch = 0.9;
  const voices = window.speechSynthesis.getVoices();
  const v = voices.find(v => v.name.includes('Ryan') || v.name.includes('Daniel') || (v.lang==='en-GB' && !v.name.includes('Female'))) || voices.find(v => v.lang==='en-GB') || voices[0];
  if (v) utt.voice = v;
  utt.onend = () => { setState('idle'); if(convoMode && micActive && recognition) setTimeout(()=>{ try{recognition.start();}catch(e){} },300); };
  window.speechSynthesis.speak(utt);
}
window.speechSynthesis.onvoiceschanged = () => window.speechSynthesis.getVoices();

// ── CHAT UI ───────────────────────────────────────────────────────────────
function formatText(text) {
  // Convert markdown-ish to HTML
  let h = text
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/\*\*(.*?)\*\*/g,'<strong>$1</strong>')
    .replace(/`(.*?)`/g,'<code style="background:rgba(139,92,246,.15);padding:1px 5px;border-radius:4px;font-family:monospace;font-size:12px">$1</code>')
    .replace(/\n/g,'<br>');
  // Make URLs clickable
  h = h.replace(/(https?:\/\/[^\s<"]+)/g, (url) => {
    const short = url.length > 50 ? url.slice(0,50)+'...' : url;
    return `<a href="${url}" target="_blank" onclick="openTab('${url}');return false">${short}</a>`;
  });
  // Handle special markers
  if (text.includes('IMAGE_SEARCH:') || text.includes('SEARCH_OPENED:')) {
    const match = text.match(/(?:IMAGE_SEARCH|SEARCH_OPENED):([^:]+):(.*)/s);
    if (match) {
      const url = match[1], msg = match[2];
      h = `${msg.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}<br><a class="open-tab-btn" href="${url}" target="_blank" onclick="openTab('${url}');return false">🔗 Open in Chrome</a>`;
    }
  }
  return h;
}

function openTab(url) {
  fetch('/api/open_tab', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({url}) });
}

function addMessage(role, text) {
  const now = new Date();
  const time = `${now.getHours().toString().padStart(2,'0')}:${now.getMinutes().toString().padStart(2,'0')}`;
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const avatar = role === 'jarvis' ? 'J' : '👤';
  div.innerHTML = `
    <div class="msg-avatar">${avatar}</div>
    <div class="msg-content">
      <div class="msg-header">
        <span class="msg-name">${role === 'jarvis' ? 'JARVIS' : 'YOU'}</span>
        <span class="msg-time2">${time}</span>
      </div>
      <div class="msg-text">${formatText(text)}</div>
    </div>`;
  chatMessages.appendChild(div);
  setTimeout(() => { chatMessages.scrollTop = chatMessages.scrollHeight; }, 50);
}

function showTyping() {
  const div = document.createElement('div');
  div.className = 'msg jarvis typing-msg'; div.id = 'typingMsg';
  div.innerHTML = `<div class="msg-avatar">J</div><div class="msg-content"><div class="msg-header"><span class="msg-name">JARVIS</span></div><div class="msg-text"><div class="typing"><span></span><span></span><span></span></div></div></div>`;
  chatMessages.appendChild(div);
  setTimeout(() => { chatMessages.scrollTop = chatMessages.scrollHeight; }, 50);
}
function removeTyping() { const t = document.getElementById('typingMsg'); if(t) t.remove(); }

// ── STOP ──────────────────────────────────────────────────────────────────
function stopResponse() {
  window.speechSynthesis.cancel();
  setState('idle');
  stopBtn.classList.remove('show');
  sending = false;
  document.getElementById('sendBtn').disabled = false;
  removeTyping();
  addMessage('jarvis', 'Stopped.');
}

// ── FILE UPLOAD ───────────────────────────────────────────────────────────
function handleFiles(files) {
  Array.from(files).forEach(f => {
    attachedFiles.push(f);
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `📄 ${f.name} <span onclick="removeFile('${f.name}')" style="opacity:.6;margin-left:2px">✕</span>`;
    document.getElementById('attachedFiles').appendChild(chip);
  });
  document.getElementById('attachedFiles').classList.add('visible');
}
function removeFile(name) {
  attachedFiles = attachedFiles.filter(f => f.name !== name);
  const af = document.getElementById('attachedFiles');
  af.innerHTML = '';
  attachedFiles.forEach(f => {
    const chip = document.createElement('div');
    chip.className = 'file-chip';
    chip.innerHTML = `📄 ${f.name} <span onclick="removeFile('${f.name}')" style="opacity:.6;margin-left:2px">✕</span>`;
    af.appendChild(chip);
  });
  if (!attachedFiles.length) af.classList.remove('visible');
}

// Drag and drop
const dropZone = document.getElementById('dropZone');
document.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('visible'); });
document.addEventListener('dragleave', e => { if (!e.relatedTarget) dropZone.classList.remove('visible'); });
document.addEventListener('drop', e => { e.preventDefault(); dropZone.classList.remove('visible'); handleFiles(e.dataTransfer.files); });

// ── SEND MESSAGE ──────────────────────────────────────────────────────────
async function submitMessage(text) {
  if (!text || sending) return;
  sending = true;
  document.getElementById('sendBtn').disabled = true;
  stopBtn.classList.add('show');

  // Add file context if any
  let fullText = text;
  if (attachedFiles.length) {
    fullText += `\n[Attached files: ${attachedFiles.map(f=>f.name).join(', ')}]`;
    attachedFiles = [];
    document.getElementById('attachedFiles').innerHTML = '';
    document.getElementById('attachedFiles').classList.remove('visible');
  }

  addMessage('user', text);
  setState('thinking');
  showTyping();

  try {
    const r = await fetch('/api/chat', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ message: fullText })
    });
    const data = await r.json();
    removeTyping();
    stopBtn.classList.remove('show');
    if (data.error) {
      addMessage('jarvis', `Error: ${data.error}`);
      setState('idle');
    } else {
      addMessage('jarvis', data.response);
      speak(data.response);
    }
  } catch(e) {
    removeTyping();
    stopBtn.classList.remove('show');
    addMessage('jarvis', 'Connection error. Is the server running?');
    setState('idle');
  }

  sending = false;
  document.getElementById('sendBtn').disabled = false;
}

async function sendMsg() {
  const inp = document.getElementById('inp');
  const msg = inp.value.trim();
  if (!msg) return;
  inp.value = ''; inp.style.height = '44px';
  await submitMessage(msg);
}

// Auto resize textarea
document.getElementById('inp').addEventListener('input', function() {
  this.style.height = '44px';
  this.style.height = Math.min(this.scrollHeight, 120) + 'px';
});
document.getElementById('inp').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMsg(); }
});

// ── NOTES ─────────────────────────────────────────────────────────────────
function toggleNotes() {
  document.getElementById('notesPanel').classList.toggle('open');
  document.getElementById('notesNavBtn').classList.toggle('active');
  renderNotes();
}
function renderNotes() {
  const list = document.getElementById('notesList');
  list.innerHTML = '';
  notes.slice().reverse().forEach((n, i) => {
    const div = document.createElement('div');
    div.className = 'note-item';
    div.innerHTML = `<div>${n.text}</div><div class="note-item-time">${n.time} <span onclick="deleteNote(${notes.length-1-i})" style="color:var(--c5);cursor:pointer;float:right">✕</span></div>`;
    list.appendChild(div);
  });
}
function saveNote() {
  const t = document.getElementById('noteInput').value.trim();
  if (!t) return;
  const now = new Date();
  notes.push({ text: t, time: `${now.toLocaleDateString()} ${now.toLocaleTimeString()}` });
  localStorage.setItem('jarvis_notes', JSON.stringify(notes));
  document.getElementById('noteInput').value = '';
  renderNotes();
}
function deleteNote(i) { notes.splice(i, 1); localStorage.setItem('jarvis_notes', JSON.stringify(notes)); renderNotes(); }

// Auto-save note on typing
let noteTimer;
document.getElementById('noteInput').addEventListener('input', () => {
  clearTimeout(noteTimer);
  noteTimer = setTimeout(saveNote, 3000);
});

// ── SESSION LIST ──────────────────────────────────────────────────────────
async function loadSessionList() {
  try {
    const r = await fetch('/api/sessions');
    const sessions = await r.json();
    const list = document.getElementById('chatList');
    list.innerHTML = '';
    sessions.forEach(s => {
      const div = document.createElement('div');
      div.className = 'chat-item';
      div.dataset.id = s.id;
      const title = s.title || 'New Chat';
      const timeStr = s.created ? s.created.replace('_',' ').slice(0,13) : '';
      div.innerHTML = '<span class="chat-item-icon">💬</span><div style="flex:1;overflow:hidden"><div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px">' + title + '</div><div style="font-size:9px;color:rgba(255,255,255,.2);font-family:monospace">' + timeStr + '</div></div><span class="chat-item-del" onclick="deleteSession(' + JSON.stringify(s.id) + ',event)">✕</span>';
      div.onclick = (e) => { if(!e.target.classList.contains('chat-item-del')) loadSession(s.id); };
      list.appendChild(div);
    });
  } catch(e) {}
}
async function loadSession(sid) {
  try {
    const r = await fetch(`/api/sessions/${sid}`);
    const data = await r.json();
    chatMessages.innerHTML = '';
    if (data.messages && data.messages.length > 0) {
      data.messages.forEach(m => addMessage(m.role === 'user' ? 'user' : 'jarvis', m.content));
    } else {
      addMessage('jarvis', "What's up boss. I'm ready.");
    }
    document.querySelectorAll('.chat-item').forEach(el => el.classList.toggle('active', el.dataset.id === sid));
    await fetch('/api/sessions/' + sid + '/activate', { method:'POST' });
    // Show chat title in topbar
    const title = data.title || 'Chat';
    document.title = 'JARVIS — ' + title;
  } catch(e) {}
}
async function newChat() {
  await fetch('/api/sessions/new', { method:'POST' });
  chatMessages.innerHTML = '';
  addMessage('jarvis', "New chat started. What's good?");
  loadSessionList();
}
async function deleteSession(sid, e) {
  e.stopPropagation();
  await fetch(`/api/sessions/${sid}`, { method:'DELETE' });
  loadSessionList();
}

// ── TODO ──────────────────────────────────────────────────────────────────
let todoOpen = false;
function toggleTodo() {
  todoOpen = !todoOpen;
  document.getElementById('todoPanel').classList.toggle('open', todoOpen);
  document.getElementById('todoNavBtn').classList.toggle('active', todoOpen);
  // Close notes if open
  if (todoOpen) { document.getElementById('notesPanel').classList.remove('open'); document.getElementById('notesNavBtn').classList.remove('active'); }
  loadTodos();
}
async function loadTodos() {
  const r = await fetch('/api/todos');
  const todos = await r.json();
  const list = document.getElementById('todoList');
  list.innerHTML = '';
  todos.forEach(t => {
    const div = document.createElement('div');
    div.className = 'todo-item' + (t.done?' done':'');
    div.innerHTML = `<div class="todo-check" onclick="doneTodo('${t.id}')">✓</div><div class="todo-text">${t.text}</div><div class="todo-del" onclick="delTodo('${t.id}')">✕</div>`;
    list.appendChild(div);
  });
}
async function addTodo() {
  const inp = document.getElementById('todoInp');
  const text = inp.value.trim();
  if (!text) return;
  await fetch('/api/todos',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});
  inp.value = '';
  loadTodos();
}
async function doneTodo(id) { await fetch(`/api/todos/${id}/done`,{method:'POST'}); loadTodos(); }
async function delTodo(id) { await fetch(`/api/todos/${id}`,{method:'DELETE'}); loadTodos(); }

// ── CLASS MODE ─────────────────────────────────────────────────────────────
let classMode = false;
async function toggleClassMode() {
  const r = await fetch('/api/class_mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!classMode})});
  const d = await r.json();
  classMode = d.class_mode;
  document.getElementById('classPill').classList.toggle('show', classMode);
  document.getElementById('classModeBtn').style.borderColor = classMode ? 'rgba(16,185,129,.5)' : '';
  document.getElementById('classModeBtn').style.color = classMode ? '#34d399' : '';
  showToast(classMode ? '🎓 Class mode ON — detailed educational answers' : '🎓 Class mode OFF');
}

// ── IMPORT CHAT ────────────────────────────────────────────────────────────
function importChat(input) {
  const file = input.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = async e => {
    const content = e.target.result;
    const r = await fetch('/api/import_chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content})});
    const d = await r.json();
    showToast(d.message || 'Chat imported!');
    addMessage('jarvis', "Got your chat history! I've read through it and I'll factor in what I learned about you going forward.");
  };
  reader.readAsText(file);
  input.value = '';
}

// ── TOAST NOTIFICATIONS ────────────────────────────────────────────────────
function showToast(text, duration=6000) {
  const container = document.getElementById('toastContainer');
  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.textContent = text;
  toast.onclick = () => toast.remove();
  container.appendChild(toast);
  // Also speak notifications
  if (text.includes('🎂') || text.includes('⏰') || text.includes('💧')) {
    speak(text.replace(/[🎂⏰💧👀]/g,'').trim());
  }
  setTimeout(() => { if (toast.parentNode) toast.remove(); }, duration);
}

// Socket for notifications
const socket = typeof io !== 'undefined' ? io() : null;
if (socket) {
  socket.on('jarvis_notification', d => {
    showToast(d.text);
    addMessage('jarvis', d.text);
  });
}

// Lazy load socket.io for notifications
(function loadSocketIO() {
  const s = document.createElement('script');
  s.src = 'https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.4/socket.io.min.js';
  s.onload = () => {
    const socket = io();
    socket.on('jarvis_notification', d => {
      showToast(d.text);
      addMessage('jarvis', d.text);
    });
  };
  document.head.appendChild(s);
})();

// ── SETTINGS ──────────────────────────────────────────────────────────────
async function toggleSettings() {
  const panel = document.getElementById('settingsPanel');
  const isOpen = panel.classList.contains('open');
  // Close other panels
  document.getElementById('notesPanel').classList.remove('open');
  document.getElementById('todoPanel').classList.remove('open');
  document.getElementById('notesNavBtn').classList.remove('active');
  document.getElementById('todoNavBtn').classList.remove('active');
  panel.classList.toggle('open', !isOpen);
  document.getElementById('settingsNavBtn').classList.toggle('active', !isOpen);
  if (!isOpen) {
    // Load current settings
    try {
      const r = await fetch('/api/settings');
      const s = await r.json();
      if (s.chrome_path) document.getElementById('chromePathInp').value = s.chrome_path;
      if (s.user_name) document.getElementById('nameInp').value = s.user_name;
      if (s.chrome_profile) document.getElementById('chromeProfileInp').value = s.chrome_profile;
      checkGoogleStatus();
    } catch(e) {}
  }
}

async function saveSetting(key, inputId, statusId) {
  const val = document.getElementById(inputId).value.trim();
  if (!val) return;
  await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({[key]: val})
  });
  const st = document.getElementById(statusId);
  st.classList.add('show');
  setTimeout(() => st.classList.remove('show'), 2000);
}

async function saveApiKey() {
  const val = document.getElementById('aiKeyInp').value.trim();
  if (!val) return;
  await fetch('/api/settings', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ai_key: val})
  });
  const st = document.getElementById('keyStatus');
  st.classList.add('show');
  setTimeout(() => st.classList.remove('show'), 2000);
  showToast('API key updated! Restart JARVIS for it to take effect.');
}

// Google account management
async function connectGoogle() {
  const st = document.getElementById('googleConnStatus');
  st.textContent = 'Connecting... A browser window will open for Google login.';
  st.classList.add('show');
  try {
    const r = await fetch('/api/google/connect', {method:'POST'});
    const d = await r.json();
    st.textContent = d.message;
    checkGoogleStatus();
    if (d.ok) showToast('Google connected! Gmail, Drive and Calendar ready.');
  } catch(e) {
    st.textContent = 'Error: ' + e.message;
  }
}

async function disconnectGoogle() {
  await fetch('/api/google/disconnect', {method:'POST'});
  checkGoogleStatus();
  showToast('Google disconnected.');
}

async function checkGoogleStatus() {
  try {
    const r = await fetch('/api/google/status');
    const d = await r.json();
    const el = document.getElementById('googleStatus');
    if (el) {
      el.textContent = d.connected ? '✓ Connected' : '✗ Not connected';
      el.style.color = d.connected ? '#10b981' : 'rgba(255,255,255,.4)';
    }
  } catch(e) {}
}

// ── SKILLS ────────────────────────────────────────────────────────────────
let skillsOpen = false;

function toggleSkills() {
  skillsOpen = !skillsOpen;
  document.getElementById('skillsPanel').classList.toggle('open', skillsOpen);
  document.getElementById('skillsNavBtn').classList.toggle('active', skillsOpen);
  if (skillsOpen) loadSkills();
}

async function loadSkills() {
  try {
    const r = await fetch('/api/skills');
    const skills = await r.json();
    const list = document.getElementById('skillsList');
    list.innerHTML = '';
    if (!skills.length) {
      list.innerHTML = '<div style="padding:16px;color:var(--dim);font-size:12px;text-align:center">No skills yet. Create your first skill below!</div>';
      return;
    }
    skills.forEach(s => {
      const div = document.createElement('div');
      div.className = 'skill-item';
      div.innerHTML = `
        <div class="skill-name">⚡ ${s.name || s.description?.slice(0,30)}</div>
        <div class="skill-desc">${s.description || ''}</div>
        <div class="skill-actions">
          <button class="skill-run-btn" onclick="runSkill('${s.name}')">▶ Run</button>
          <button class="skill-del-btn" onclick="deleteSkill('${s.name}')">✕ Delete</button>
        </div>`;
      list.appendChild(div);
    });
  } catch(e) {}
}

async function createSkill() {
  const name = document.getElementById('skillNameInp').value.trim();
  const desc = document.getElementById('skillDescInp').value.trim();
  if (!name || !desc) { showToast('Give the skill a name and description!'); return; }
  showToast('Creating skill...');
  await submitMessage(`create skill ${name}: ${desc}`);
  document.getElementById('skillNameInp').value = '';
  document.getElementById('skillDescInp').value = '';
  setTimeout(loadSkills, 2000);
}

async function runSkill(name) {
  toggleSkills();
  await submitMessage(name);
}

async function deleteSkill(name) {
  await fetch(`/api/skills/${encodeURIComponent(name)}`, {method:'DELETE'});
  loadSkills();
  showToast(`Skill '${name}' deleted.`);
}

// Init
loadSessionList();
setInterval(loadSessionList, 30000);  // refresh every 30s not 10s
drawIdle();
setState('idle');
stateLabel.textContent = 'CLICK 🎤';
</script>
</body>
</html>"""


# ── LAUNCH ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("╔══════════════════════════════╗")
    print("║  J.A.R.V.I.S  —  Online     ║")
    print("╚══════════════════════════════╝\n")

    # Open in Chrome specifically
    def open_chrome():
        time.sleep(2.5)
        url = "http://localhost:5000"
        chrome_paths = [
            "C:/Program Files/Google/Chrome/Application/chrome.exe",
            "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
            os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe"),
        ]
        opened = False
        for path in chrome_paths:
            if os.path.exists(path):
                subprocess.Popen([path, url])
                opened = True
                print(f"  ✓ Opened in Chrome")
                break
        if not opened:
            webbrowser.open(url)
            print("  ✓ Opened in default browser")

    threading.Thread(target=open_chrome, daemon=True).start()

    def bye(sig, frame):
        print("\nJARVIS offline.")
        sys.exit(0)
    signal.signal(signal.SIGINT, bye)

    threading.Thread(target=timer_loop, daemon=True).start()
    print("✅  http://localhost:5000")
    print("🎤  Click mic button or use Convo Mode")
    print("⌨   Or type in the chat\n")

    sio.run(app, host="127.0.0.1", port=5000, debug=False,
            use_reloader=False, allow_unsafe_werkzeug=True)
