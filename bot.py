# Jio Recharge Bot — Playwright-based (browser automation)
import telebot, re, time, os, sys, json, threading, random, datetime
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

# ================= CONFIG =================
BOT_TOKEN = '8854376849:AAEk1bQAx_KbzpWsRxdyilL6qILYRqxj4dc'
ADMIN_ID = 8752143085
bot = telebot.TeleBot(BOT_TOKEN)

# ================= FILES =================
os.makedirs('JioData', exist_ok=True)
PREMIUM_FILE = 'JioData/premium.txt'
USERS_FILE = 'JioData/users.txt'
BANNED_FILE = 'JioData/banned.txt'
HITS_FILE = 'JioData/hits.txt'
PROXY_FILE = 'JioData/proxies.txt'

ADMIN_LIMIT = 50
PREMIUM_LIMIT = 15
FREE_LIMIT = 0
WORKERS = 3

ACTIVE_JOBS = {}
ACTIVE_USERS_MPP = {}

for f in [USERS_FILE, PREMIUM_FILE, BANNED_FILE, HITS_FILE, PROXY_FILE]:
    if not os.path.exists(f): open(f, 'w').close()

# ================= HELPERS =================
def is_admin(uid): return int(uid) == ADMIN_ID

def is_premium(uid):
    try:
        with open(PREMIUM_FILE, 'r') as f:
            for p in f.read().splitlines():
                parts = p.split('|')
                if len(parts) < 2: continue
                if str(uid) == parts[0].strip():
                    exp = float(parts[1])
                    if exp == 0 or time.time() < exp: return True
    except: pass
    return False

def is_banned(uid):
    try:
        with open(BANNED_FILE, 'r') as f:
            for b in f.read().splitlines():
                parts = b.split('|')
                if len(parts) < 2: continue
                if str(uid) == parts[0].strip():
                    exp = float(parts[1])
                    if exp == 0 or time.time() < exp: return True
    except: pass
    return False

def add_user(uid):
    try:
        with open(USERS_FILE, 'r') as f: users = f.read().splitlines()
        if str(uid) not in users:
            with open(USERS_FILE, 'a') as f: f.write(str(uid) + '\n')
    except: pass

def parse_duration(dur):
    dur = dur.lower().strip()
    now = time.time()
    if dur in ('lifetime', 'life', 'forever', 'inf', '0'):
        return 0
    try:
        if dur.endswith('mo'): return now + int(dur[:-2]) * 86400 * 30
        if dur.endswith('s'): return now + int(dur[:-1])
        if dur.endswith('m'): return now + int(dur[:-1]) * 60
        if dur.endswith('h'): return now + int(dur[:-1]) * 3600
        if dur.endswith('d'): return now + int(dur[:-1]) * 86400
        if dur.endswith('w'): return now + int(dur[:-1]) * 86400 * 7
        if dur.endswith('y'): return now + int(dur[:-1]) * 86400 * 365
        return now + int(dur) * 86400
    except:
        return None

def add_premium(tid, exp):
    tid = str(tid).strip()
    try:
        with open(PREMIUM_FILE, 'r') as f: lines = f.readlines()
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        with open(PREMIUM_FILE, 'a') as f:
            f.write(f"{tid}|{exp}\n")
        return True
    except Exception as e:
        print(f"add_premium error: {e}")
        return False

def remove_premium(tid):
    tid = str(tid).strip()
    try:
        with open(PREMIUM_FILE, 'r') as f: lines = f.readlines()
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        return True
    except: return False

# ================= PROXY =================
proxy_list = []

def load_proxies():
    global proxy_list
    proxy_list = []
    if os.path.exists(PROXY_FILE):
        with open(PROXY_FILE, 'r') as f:
            proxy_list = [l.strip() for l in f if l.strip()]
    return len(proxy_list)

def save_proxies(proxies):
    with open(PROXY_FILE, 'w') as f:
        for p in proxies: f.write(p + '\n')
    load_proxies()

def get_random_proxy():
    if not proxy_list: return None
    return random.choice(proxy_list)

def proxy_dict(entry):
    if not entry: return None
    try:
        host, port, user, pw = entry.split(":")
        return {"server": f"http://{host}:{port}", "username": user, "password": pw}
    except Exception:
        return None

load_proxies()

# ================= JIO CORE =================
from jio import (
    jio_checkout, generate_cards, parse_card_line, card_label
)

def status_head(status):
    heads = {
        "success": "✅ <b>HIT SUCCESSFUL</b>",
        "3ds": "🔥 <b>3DS REQUIRED</b>",
        "insufficient": "💸 <b>INSUFFICIENT FUNDS</b>",
        "expired": "📅 <b>CARD EXPIRED</b>",
        "invalid_cvv": "🔒 <b>INVALID CVV</b>",
        "invalid_card": "❌ <b>INVALID CARD</b>",
        "issuer_decline": "🚫 <b>CARD ISSUER DECLINED</b>",
        "blocked": "🔴 <b>CARD BLOCKED</b>",
        "not_permitted": "⛔ <b>NOT PERMITTED</b>",
        "limit_exceeded": "📊 <b>LIMIT EXCEEDED</b>",
        "velocity": "⚠️ <b>VELOCITY LIMIT</b>",
        "processor_error": "🔧 <b>PROCESSOR ERROR</b>",
        "failed": "❌ <b>DECLINED</b>",
        "unknown": "❓ <b>UNKNOWN</b>",
        "error": "⚠️ <b>ERROR</b>",
    }
    return heads.get(status, "⚠️ <b>UNKNOWN</b>")


def run_check(phone, amount, card, proxy_str=None):
    proxy = proxy_dict(proxy_str) if proxy_str else None
    try:
        st, dt, url, meta = jio_checkout(phone, amount, card, proxy=proxy, headless=True)
    except Exception as e:
        return "error", f"Check failed: {str(e)[:120]}"

    if st == "requires_action":
        st = "3ds"

    low = (dt or "").lower()
    if st == "failed":
        if "insufficient" in low:
            st = "insufficient"
        elif "expired" in low:
            st = "expired"
        elif "cvv" in low or "cvc" in low:
            st = "invalid_cvv"
        elif "do not honor" in low or "issuer" in low:
            st = "issuer_decline"
        elif "blocked" in low or "stolen" in low or "lost" in low:
            st = "blocked"
        elif "not permitted" in low or "international" in low:
            st = "not_permitted"
        elif "limit" in low:
            st = "limit_exceeded"
        elif "processor" in low or "network" in low or "try again" in low or "timeout" in low:
            st = "processor_error"

    return st, dt


# ================= COMMANDS =================
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, "❌ <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    bot.reply_to(message,
        f"👋 <b>Welcome to Jio Recharge Bot</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 User ➤ <b>{message.from_user.first_name}</b>\n"
        f"🆔 ID ➤ <code>{uid}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"⚡ /jio — Single check\n"
        f"📦 /mjio — Mass check\n"
        f"🌐 /proxy — Manage proxies\n"
        f"👤 /info — Account info",
        parse_mode="HTML")

@bot.message_handler(commands=['jio'])
def jio_single(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, "❌ <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    args = message.text.split()
    if len(args) < 4:
        bot.reply_to(message,
            "📝 <b>Usage:</b> <code>/jio &lt;phone&gt; &lt;amount&gt; &lt;pan|mm|yy|cvv&gt;</code>\n"
            "Example: <code>/jio 9876543210 239 5131112233445566|03|30|086</code>",
            parse_mode="HTML"); return
    phone, amount, cc = args[1], args[2], args[3]
    card = parse_card_line(cc)
    if not card:
        bot.reply_to(message, "❌ <b>Invalid card format.</b>", parse_mode="HTML"); return

    msg = bot.reply_to(message,
        f"⏳ <b>Processing Jio recharge (browser)...</b>\n"
        f"👤 Phone: <code>{phone}</code>\n"
        f"💰 Amount: ₹{amount}\n"
        f"💳 Card: <code>{card_label(card)}</code>\n"
        f"⏱️ This takes 30–120s",
        parse_mode="HTML")

    proxy = get_random_proxy()
    try:
        status, response = run_check(phone, amount, card, proxy_str=proxy)
    except Exception as e:
        status, response = "error", f"Failed: {e}"

    if is_admin(uid): rk = " [ADMIN]"
    elif is_premium(uid): rk = " [PREMIUM]"
    else: rk = " [FREE]"

    safe = str(response).replace("<","").replace(">","").replace("&","")
    safe_name = str(message.from_user.first_name).replace("<","").replace(">","").replace("&","")

    if status == "success":
        with open(HITS_FILE, 'a', encoding="utf-8") as f:
            f.write(f"{phone} Rs{amount} {card_label(card)} - {response}\n")

    head = status_head(status)
    res = (
        f"{head}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Phone</b> ━ <code>{phone}</code>\n"
        f"💰 <b>Amount</b> ━ ₹{amount}\n"
        f"💳 <b>Card</b> ━ <code>{card_label(card)}</code>\n"
        f"📩 <b>Response</b> ━ {safe}\n"
        f"🌐 <b>Gateway</b> ━ Jio Recharge (Playwright)\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>User:</b> {safe_name}{rk}"
    )
    try: bot.delete_message(message.chat.id, msg.message_id)
    except: pass
    try: bot.reply_to(message, res, parse_mode="HTML")
    except:
        try: bot.reply_to(message, res.replace("<code>","").replace("</code>",""))
        except: pass

@bot.message_handler(commands=['mjio'])
def mjio_mass(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, "❌ <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)

    limit = ADMIN_LIMIT if is_admin(uid) else (PREMIUM_LIMIT if is_premium(uid) else FREE_LIMIT)
    if limit == 0:
        bot.reply_to(message, "⚠️ <b>Free users cannot use mass check.</b>\nAsk admin for premium.", parse_mode="HTML"); return
    if ACTIVE_USERS_MPP.get(uid):
        bot.reply_to(message, "⚠️ <b>Mass check already running.</b>", parse_mode="HTML"); return

    args = message.text.split()
    cards = []
    phone = amount = None

    if len(args) >= 5:
        phone, amount, bin_str = args[1], args[2], args[3]
        try: count = int(args[4])
        except: count = 5
        count = min(count, limit)
        cards = generate_cards(bin_str, "12", "2029", count)
    elif len(args) >= 3 and message.reply_to_message and message.reply_to_message.document:
        phone, amount = args[1], args[2]
        fi = bot.get_file(message.reply_to_message.document.file_id)
        raw = bot.download_file(fi.file_path)
        for l in raw.decode('utf-8', errors='ignore').splitlines():
            c = parse_card_line(l)
            if c: cards.append(c)
        if not cards:
            bot.reply_to(message, "❌ <b>No valid cards in file.</b>", parse_mode="HTML"); return
        cards = cards[:limit]
    else:
        bot.reply_to(message,
            "📝 <b>Usage:</b>\n"
            "<code>/mjio &lt;phone&gt; &lt;amount&gt; &lt;bin&gt; &lt;count&gt;</code>\n"
            "OR reply .txt with: <code>/mjio &lt;phone&gt; &lt;amount&gt;</code>",
            parse_mode="HTML"); return

    job_id = f"{int(time.time())}{random.randint(100,999)}"
    ACTIVE_JOBS[job_id] = True
    ACTIVE_USERS_MPP[uid] = True
    total = len(cards)

    results = {"hits":0,"hits_list":[],"declined":0,"declined_list":[],
               "3ds":0,"3ds_list":[],"error":0,"error_list":[],"checked":0,
               "insufficient":0,"insufficient_list":[]}
    start_time = time.time()
    last_update = [0]
    ulock = threading.Lock()
    rk = " [ADMIN]" if is_admin(uid) else (" [PREMIUM]" if is_premium(uid) else " [FREE]")

    def cap(done=False):
        el = int(time.time() - start_time); m, s = divmod(el, 60)
        st = "✅ Completed\n" if done else ""
        return (f"📊 <b>Mass Jio Recharge (Browser)</b>\n━━━━━━━━━━━━━━━━━━━━\n{st}"
                f"┣ 📦 Progress ➜ {results['checked']}/{total}\n"
                f"┣ ✅ Hits ➜ {results['hits']}\n"
                f"┣ 🔥 3DS ➜ {results['3ds']}\n"
                f"┣ 💸 Insufficient ➜ {results['insufficient']}\n"
                f"┣ ❌ Declined ➜ {results['declined']}\n"
                f"┣ ⚠️ Errors ➜ {results['error']}\n"
                f"┗ ⏱️ Time ➜ {m:02d}:{s:02d}\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"👤 User: {message.from_user.first_name}{rk}")

    def mkup(done=False):
        m = telebot.types.InlineKeyboardMarkup()
        if not done:
            m.add(telebot.types.InlineKeyboardButton("🛑 STOP", callback_data=f"stop_{job_id}"))
        return m

    prog = bot.reply_to(message, cap(), parse_mode="HTML", reply_markup=mkup())

    def worker(card):
        if not ACTIVE_JOBS.get(job_id): return
        proxy = get_random_proxy()
        try:
            status, response = run_check(phone, amount, card, proxy_str=proxy)
        except Exception as e:
            status, response = "error", f"Failed: {e}"
        entry = f"{card_label(card)} - {response}"

        if status == "success":
            results["hits"] += 1; results["hits_list"].append(entry)
            with open(HITS_FILE, 'a', encoding="utf-8") as f:
                f.write(f"{phone} Rs{amount} {card_label(card)} - {response}\n")
        elif status == "3ds":
            results["3ds"] += 1; results["3ds_list"].append(entry)
        elif status == "insufficient":
            results["insufficient"] += 1; results["insufficient_list"].append(entry)
        elif status in ("expired","invalid_cvv","invalid_card","issuer_decline","blocked",
                        "not_permitted","limit_exceeded","velocity","processor_error","failed"):
            results["declined"] += 1; results["declined_list"].append(entry)
        else:
            results["error"] += 1; results["error_list"].append(entry)
        results["checked"] += 1

        if status in ("success", "3ds", "insufficient"):
            safe = str(response).replace("<","").replace(">","").replace("&","")
            safe_name = str(message.from_user.first_name).replace("<","").replace(">","").replace("&","")
            single = (
                f"{status_head(status)}\n━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>Phone</b> ━ <code>{phone}</code>\n"
                f"💰 <b>Amount</b> ━ ₹{amount}\n"
                f"💳 <b>Card</b> ━ <code>{card_label(card)}</code>\n"
                f"📩 <b>Response</b> ━ {safe}\n"
                f"🌐 <b>Gateway</b> ━ Jio Recharge (Playwright)\n━━━━━━━━━━━━━━━━━\n"
                f"👤 <b>User:</b> {safe_name}{rk}"
            )
            try:
                bot.send_message(message.chat.id, single, parse_mode="HTML")
                time.sleep(random.uniform(1.0, 2.0))
            except Exception as e:
                err = str(e)
                if '429' in err:
                    m = re.search(r'retry after (\d+)', err)
                    time.sleep(int(m.group(1))+2 if m else 30)
                else: time.sleep(3)

        with ulock:
            do = results["checked"] >= last_update[0] + 1 or results["checked"] == total
            if do: last_update[0] = results["checked"]
        if do:
            try: bot.edit_message_text(cap(), message.chat.id, prog.message_id,
                                       parse_mode="HTML", reply_markup=mkup())
            except: pass

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as ex:
            for c in cards:
                if not ACTIVE_JOBS.get(job_id): break
                ex.submit(worker, c)
        ACTIVE_JOBS.pop(job_id, None)
        ACTIVE_USERS_MPP[uid] = False
        try: bot.edit_message_text(cap(done=True), message.chat.id, prog.message_id,
                                   parse_mode="HTML", reply_markup=mkup(done=True))
        except: pass

        lines = []
        for sec, lbl in [("hits_list","HITS"),("3ds_list","3DS"),
                         ("insufficient_list","INSUFFICIENT FUNDS"),
                         ("declined_list","DECLINED"),("error_list","ERRORS")]:
            if results.get(sec):
                lines.append(f"{lbl}:"); lines.extend(results[sec]); lines.append("")
        if lines:
            content = "\n".join(lines)
            fcap = (f"📊 <b>Results</b>\n━━━━━━━━━━━━━━━━━━━━\n"
                    f"┣ ✅ Hits ➜ {results['hits']}\n"
                    f"┣ 🔥 3DS ➜ {results['3ds']}\n"
                    f"┣ 💸 Insufficient ➜ {results['insufficient']}\n"
                    f"┣ ❌ Declined ➜ {results['declined']}\n"
                    f"┣ ⚠️ Errors ➜ {results['error']}\n"
                    f"┗ 📦 Total ➜ {results['checked']}")
            path = "JioResults.txt"
            with open(path, "w", encoding="utf-8") as f: f.write(content)
            with open(path, "rb") as f:
                bot.send_document(message.chat.id, f, caption=fcap, parse_mode="HTML")
            try: os.remove(path)
            except: pass
    except Exception as e:
        ACTIVE_JOBS.pop(job_id, None)
        ACTIVE_USERS_MPP[uid] = False

@bot.callback_query_handler(func=lambda c: c.data.startswith("stop_"))
def cb_stop(call):
    try: bot.answer_callback_query(call.id, "Stopping...")
    except: pass
    jid = call.data[5:]
    if jid in ACTIVE_JOBS:
        ACTIVE_JOBS[jid] = False

@bot.message_handler(commands=['info'])
def user_info(message):
    uid = str(message.from_user.id)
    role, limit, exp = "[FREE]", FREE_LIMIT, "NEVER"
    if is_admin(int(uid)):
        role, limit, exp = "[ADMIN]", ADMIN_LIMIT, "Lifetime"
    elif is_premium(int(uid)):
        role, limit = "[PREMIUM]", PREMIUM_LIMIT
        with open(PREMIUM_FILE, 'r') as f:
            for line in f:
                if line.startswith(uid + "|"):
                    e = float(line.strip().split('|')[1])
                    exp = "Lifetime" if e == 0 else datetime.datetime.fromtimestamp(e).strftime('%Y-%m-%d %H:%M:%S')
                    break
    bot.reply_to(message,
        f"👤 <b>Account Info</b>\n━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> {uid}\n"
        f"👑 <b>Rank:</b> {role}\n"
        f"📅 <b>Expires:</b> {exp}\n"
        f"🔢 <b>Mass Limit:</b> {limit}",
        parse_mode="HTML")

# ================= ADMIN =================
@bot.message_handler(commands=['addpremium', 'premium'])
def add_prem(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        p = message.text.split()
        if len(p) < 3:
            bot.reply_to(message, "📝 <code>/addpremium &lt;id&gt; &lt;duration&gt;</code>", parse_mode="HTML"); return
        tid, dur = p[1], p[2]
        exp = parse_duration(dur)
        if exp is None:
            bot.reply_to(message, f"❌ <b>Invalid duration:</b> {dur}", parse_mode="HTML"); return
        if add_premium(tid, exp):
            dur_str = "Lifetime" if exp == 0 else dur
            bot.reply_to(message, f"✅ <b>Premium added</b> ➜ <code>{tid}</code> ({dur_str})", parse_mode="HTML")
            try: bot.send_message(int(tid), f"👑 <b>Premium added!</b>\nDuration: {dur_str}", parse_mode="HTML")
            except: pass
        else:
            bot.reply_to(message, "❌ <b>Failed.</b>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"❌ <b>Error:</b> {str(e)[:100]}", parse_mode="HTML")

@bot.message_handler(commands=['rmpremium', 'unpremium'])
def rm_prem(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        tid = message.text.split()[1]
        if remove_premium(tid):
            bot.reply_to(message, f"✅ <b>Premium removed</b> ➜ <code>{tid}</code>", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ <b>Failed.</b>", parse_mode="HTML")
    except: bot.reply_to(message, "📝 <code>/rmpremium &lt;id&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        p = message.text.split()
        tid = p[1]
        dur = p[2] if len(p) > 2 else 'lifetime'
        exp = parse_duration(dur)
        if exp is None:
            bot.reply_to(message, "❌ <b>Invalid duration.</b>", parse_mode="HTML"); return
        with open(BANNED_FILE, 'a') as f: f.write(f"{tid}|{exp}\n")
        bot.reply_to(message, f"✅ <b>Banned</b> ➜ <code>{tid}</code> ({dur})", parse_mode="HTML")
    except: bot.reply_to(message, "📝 <code>/ban &lt;id&gt; &lt;duration&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        tid = message.text.split()[1]
        with open(BANNED_FILE, 'r') as f: lines = f.readlines()
        with open(BANNED_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        bot.reply_to(message, f"✅ <b>Unbanned</b> ➜ <code>{tid}</code>", parse_mode="HTML")
    except: bot.reply_to(message, "📝 <code>/unban &lt;id&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def bot_stats(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ <b>Admin only.</b>", parse_mode="HTML"); return
    with open(USERS_FILE, 'r') as f: uc = len(f.read().splitlines())
    with open(PREMIUM_FILE, 'r') as f: pc = len(f.read().splitlines())
    with open(BANNED_FILE, 'r') as f: bc = len(f.read().splitlines())
    with open(HITS_FILE, 'r') as f: hc = len(f.read().splitlines())
    bot.reply_to(message,
        f"📊 <b>Bot Stats</b>\n━━━━━━━━━━━━━\n"
        f"✅ <b>Total Hits:</b> {hc}\n"
        f"👤 <b>Users:</b> {uc}\n"
        f"👑 <b>Premium:</b> {pc}\n"
        f"❌ <b>Banned:</b> {bc}",
        parse_mode="HTML")

# ================= MAIN =================
if __name__ == "__main__":
    print("JIO PLAYWRIGHT BOT IS RUNNING...\n")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
