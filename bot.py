# bot.py — Jio Recharge Telegram Bot
# Deploy on Sevalalla / any VPS with Python 3.9+
# pip install -r requirements.txt

import re, time, random, sys, json as _json, logging, asyncio, os
from curl_cffi import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters, ContextTypes
)
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# ═══════════════ CONVERSATION STATES ═══════════════
MOBILE, CARD, PLAN_CHOOSE, PLAN_CUSTOM, CONFIRM = range(5)

# ═══════════════ JIO CORE ═══════════════
PROFILES=[
    {"imp":"chrome131","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36","ch":'"Google Chrome";v="131", "Not_A Brand";v="8", "Chromium";v="131"',"plat":'"Windows"',"mob":"?0"},
    {"imp":"chrome124","ua":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36","ch":'"Google Chrome";v="124", "Not_A Brand";v="8", "Chromium";v="124"',"plat":'"macOS"',"mob":"?0"},
    {"imp":"chrome123","ua":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36","ch":'"Google Chrome";v="123", "Not_A Brand";v="8", "Chromium";v="123"',"plat":'"Linux"',"mob":"?0"},
    {"imp":"edge101","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/101.0.0.0 Safari/537.36 Edg/101.0.0.0","ch":'"Microsoft Edge";v="101", "Not_A Brand";v="8", "Chromium";v="101"',"plat":'"Windows"',"mob":"?0"},
    {"imp":"chrome120","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36","ch":'"Google Chrome";v="120", "Not_A Brand";v="8", "Chromium";v="120"',"plat":'"Windows"',"mob":"?0"},
    {"imp":"firefox135","ua":"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0","ch":'"Firefox";v="135", "Not_A Brand";v="8"',"plat":'"Windows"',"mob":"?0"},
]
SCREENS=[
    {"h":1080,"w":1920,"depth":24},{"h":900,"w":1440,"depth":30},
    {"h":768,"w":1366,"depth":24},{"h":1200,"w":1920,"depth":24},
    {"h":864,"w":1536,"depth":30},
]
LANGS=["en-US,en;q=0.9","en-GB,en;q=0.9,en-US;q=0.8","en-IN,en;q=0.9,en-US;q=0.8","en-US,en;q=0.9,hi;q=0.8"]

def ts(): return str(int(time.time()*1000))

def jh(ref,ct=None,origin=None,extra=None,cfg=None):
    h={"Accept-Language":cfg["lg"],"Cache-Control":"no-cache","Connection":"keep-alive","Pragma":"no-cache",
       "Referer":ref,"User-Agent":cfg["UA"],"sec-ch-ua":cfg["SEC"],"sec-ch-ua-mobile":cfg["MOB"],"sec-ch-ua-platform":cfg["PLAT"]}
    if ct: h["Content-Type"]=ct
    if origin: h["Origin"]=origin
    if extra: h.update(extra)
    return h

def ph(ref,ct=None,origin=None,extra=None,cfg=None):
    h={"Accept":"application/json, text/plain, */*","Accept-Language":cfg["lg"],"Cache-Control":"no-cache",
       "Pragma":"no-cache","Referer":ref,"User-Agent":cfg["UA"],"sec-ch-ua":cfg["SEC"],"sec-ch-ua-mobile":cfg["MOB"],
       "sec-ch-ua-platform":cfg["PLAT"],"Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors",
       "Sec-Fetch-Site":"same-origin","x-request-time":ts()}
    if ct: h["Content-Type"]=ct
    if origin: h["Origin"]=origin
    if extra: h.update(extra)
    return h

def iter_plans(pj):
    for cat in pj.get("planCategories") or []:
        for sub in cat.get("subCategories") or []:
            for plan in sub.get("plans") or []:
                if plan.get("key"):
                    yield {"key":plan["key"],"amount":float(plan.get("amount") or 0),
                           "name":plan.get("name") or plan.get("planName") or "",
                           "category":cat.get("type") or "","validity":plan.get("validity") or ""}

def plan_by_amount(pj,amount):
    for p in iter_plans(pj):
        if p["amount"]==float(amount): return p
    return None

def cheapest_plan(pj):
    plans=list(iter_plans(pj))
    return min(plans,key=lambda p:p["amount"]) if plans else None

# ═══════════════ RECHARGE FLOW ═══════════════
def do_recharge(recharge_number, card_num, card_mm, card_yy, card_cvv, plan_key, progress_cb=None):
    def cb(lbl):
        if progress_cb:
            try: progress_cb(lbl)
            except: pass

    pf=random.choice(PROFILES); sc=random.choice(SCREENS); lg=random.choice(LANGS)
    cfg={"UA":pf["ua"],"SEC":pf["ch"],"PLAT":pf["plat"],"MOB":pf["mob"],"IMP":pf["imp"],"lg":lg}

    CARD_NUM=card_num; CARD_MM=card_mm; CARD_YY=card_yy; CARD_CVV=card_cvv
    CARD_NAME="matt henry"; CARD_PREFIX=CARD_NUM[:6]
    flow_start=time.time()

    session=requests.Session(impersonate=cfg["IMP"])

    cb("Session start")
    session.get("https://www.jio.com/",headers={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Accept-Language":lg,"Upgrade-Insecure-Requests":"1","User-Agent":cfg["UA"],"sec-ch-ua":cfg["SEC"],"sec-ch-ua-mobile":cfg["MOB"],"sec-ch-ua-platform":cfg["PLAT"]},verify=False)

    cb("Number lookup")
    r=session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{recharge_number}",
        headers=jh("https://www.jio.com/",extra={"Accept":"application/json, text/plain, */*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},cfg=cfg))
    d=r.json()
    if d.get("errorMessage")=="NOT_SUBSCRIBED_USER":
        return {"status":"FAILED","message":"Not a Jio number","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":d,"elapsed":time.time()-flow_start}
    lookup=d

    primary=lookup.get("primaryService") or {}
    billing_type=lookup.get("billingType") or primary.get("billingType") or "PREPAID"
    next_value=lookup.get("nextPage") or billing_type
    plans_ref=(f"https://www.jio.com/selfcare/recharge/mobility/plans/"
               f"?serviceType=mobility&serviceId={recharge_number}&next={next_value}&billingType={billing_type}&entrysource=Widget")

    cb("Load plans")
    session.get("https://www.jio.com/selfcare/recharge/mobility/plans/",
        params={"serviceType":"mobility","serviceId":recharge_number,"next":next_value,"billingType":billing_type,"entrysource":"Widget"},
        headers=jh("https://www.jio.com/",extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"same-origin","Sec-Fetch-User":"?1","Upgrade-Insecure-Requests":"1"},cfg=cfg))

    r4=session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/plans/serviceId/{recharge_number}",
        headers=jh(plans_ref,extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},cfg=cfg))
    plans_json=r4.json()

    cb("Checkout")
    r=session.post("https://www.jio.com/api/jio-recharge-service/recharge/buy",
        headers=jh(plans_ref,ct="application/json",origin="https://www.jio.com",extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},cfg=cfg),
        json={"planKey":plan_key,"selectedService":recharge_number})
    if r.status_code!=200:
        return {"status":"FAILED","message":f"buy {r.status_code}","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":{"buy":r.text[:300]},"elapsed":time.time()-flow_start}

    cb("Payment gateway")
    r=session.post("https://www.jio.com/api/jio-recharge-service/recharge/pay",
        headers=jh(plans_ref,ct="application/json",origin="https://www.jio.com",extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},cfg=cfg),
        json={"addonPlanKeys":[],"flexiTopupFlow":False,"servicePlanList":[{"planKey":plan_key,"quantity":1,"serviceId":recharge_number}]})
    payment_url=r.json().get("paymentURL","https://www.jio.com/api/jio-common-servlet/jiocommon/redirect")

    cb("Redirect")
    r=session.get(payment_url,headers=jh(plans_ref,extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"same-origin","Sec-Fetch-User":"?1","Upgrade-Insecure-Requests":"1"},cfg=cfg),allow_redirects=True)
    fa=re.search(r"action='([^']+)'",r.text); fi=re.findall(r"name='([^']+)'\s+value='([^']*)'",r.text)
    pay_form_url=fa.group(1) if fa else "https://pay.jio.com/jiopg/v1/payment-options"
    pay_form_data={k:v for k,v in fi}

    cb("Pay portal")
    r=session.post(pay_form_url,
        headers=jh("https://www.jio.com/",ct="application/x-www-form-urlencoded",origin="https://www.jio.com",extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document","Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"cross-site","Sec-Fetch-User":"?1","Upgrade-Insecure-Requests":"1"},cfg=cfg),
        data=pay_form_data,allow_redirects=True)
    pay_jio_ref=r.url

    cb("Authorization")
    r=session.post("https://pay.jio.com/jiopg/v1/authorize-card-operation",
        headers=jh(pay_jio_ref,ct="application/json",origin="https://pay.jio.com",extra={"Accept":"application/json","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},cfg=cfg),
        json={"paymentMode":"CCDC","cardPrefix":CARD_PREFIX,"isEMISelected":False,"viewOffer":False,"skuCode":None,"copco":None,"isStoreCreditSelected":None})
    x_token=r.json().get("token","")
    if not x_token:
        return {"status":"FAILED","message":"No x-token received","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":r.json(),"elapsed":time.time()-flow_start}

    cb("Card confirm")
    r=session.post("https://pay.jio.com/jpgpciapp/v1/on-ccdc-confirmation",
        headers=jh(pay_jio_ref,ct="application/json",origin="https://pay.jio.com",extra={"Accept":"application/json","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin","x-token":x_token},cfg=cfg),
        json={"cvvNumber":CARD_CVV,"cashBackApplied":"N","isTrxnStatusCheckEnable":"N","seqId":"","ccRoutePg":"",
              "customerCardTypeValue":"mastercard","paymentMode":"CCDC","offerAppliedByCust":False,"viewOffer":False,
              "cardType":"ic_mastercard","cardNumber":CARD_NUM,"cardTypeText":"MASTERCARD_CARD",
              "expiryMonth":CARD_MM,"expiryYear":CARD_YY,"cardHolderName":CARD_NAME,"userCardSaveConsent":False,
              "browserDetails":{"browserHeader":"application/json","browserJavaEnabled":False,"browserJavascriptEnabled":True,
                  "browserLanguage":lg.split(",")[0],"browserColorDepth":sc["depth"],
                  "browserScreenHeight":sc["h"],"browserScreenWidth":sc["w"],"browserTz":-330,"browserUserAgent":cfg["UA"]}})
    dj=r.json()
    if not dj.get("status"):
        return {"status":"FAILED","message":dj.get("message","Card confirmation failed"),"reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":dj,"elapsed":time.time()-flow_start}
    html_form=dj.get("htmlForm","")

    cb("Bank connect")
    ea=re.search(r"action='([^']+)'",html_form)
    ei=re.findall(r"name='([^']+)'\s+value='([^']*)'",html_form)
    eu=ea.group(1) if ea else ""
    ed={k:v for k,v in ei}
    r=session.post(eu,headers=jh(pay_jio_ref,ct="application/x-www-form-urlencoded",origin="https://pay.jio.com",
        extra={"Accept":"text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8","Sec-Fetch-Dest":"document",
               "Sec-Fetch-Mode":"navigate","Sec-Fetch-Site":"cross-site","Sec-Fetch-User":"?1","Upgrade-Insecure-Requests":"1"},cfg=cfg),
        data=ed,allow_redirects=True)
    m=re.search(r'x-gl-token=([^&\s"\'\\]+)',r.url+r.text)
    if not m:
        return {"status":"FAILED","message":"gl_token not found","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":{"url":r.url[:200]},"elapsed":time.time()-flow_start}
    gl_token=m.group(1)
    gl_ref=f"https://api.payglocal.com/gl/payflow-ui/?x-gl-token={gl_token}"

    cb("PG init")
    r=session.get("https://api.payglocal.com/gl/v2/payments/redirect/dc",
        params={"x-gl-token":gl_token},
        headers=ph(gl_ref,extra={"x-gl-current-host":"api.payglocal.com","x-gl-gid":"gl_payflow-ui","x-gl-pb-tag-id":"",
            "x-gl-previous-host":"https://pay.easebuzz.in/","x-gl-referrer-mismatch":"false","x-gl-trusted-referrer":"https://pay.easebuzz.in"},cfg=cfg))
    if r.status_code!=200:
        return {"status":"FAILED","message":f"PG redirect {r.status_code}","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":{},"elapsed":time.time()-flow_start}

    cb("Payment init")
    r=session.post("https://api.payglocal.com/gl/v2/payments/pd/paynow",
        params={"x-gl-token":gl_token},
        headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com",cfg=cfg),
        json={"isEnc":"false","payload":{"customerCurrency":"INR","saveCurrencyPreference":False,
            "browserDetails":{"colorDepth":sc["depth"],"javaEnabled":False,"javaScripEnabled":True,
                "language":lg.split(",")[0],"screenHeight":sc["h"],"screenWidth":sc["w"],"timeZone":-330},
            "billingData":{"addressCountry":"FR"},"shippingData":{},"agreedOnTnCs":True}})
    if r.status_code!=200:
        return {"status":"FAILED","message":f"paynow {r.status_code}","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":{},"elapsed":time.time()-flow_start}

    cb("Risk check")
    r=session.post("https://api.payglocal.com/gl/v1/payments/risk/fp",
        params={"x-gl-token":gl_token},
        headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com",cfg=cfg),
        json={"requestId":f"{ts()}.{random.randint(100000,999999)}","visitorId":"Y8c4sEunqz0opl0b6YAd","visitorFound":True,"confidenceScore":1})
    kid=r.json().get("data",{}).get("kid","")
    if not kid:
        return {"status":"FAILED","message":"kid not received","reason":"","plan_name":"","amount":0,"number":recharge_number,"raw":r.json(),"elapsed":time.time()-flow_start}

    cb("Charge")
    time.sleep(random.uniform(0.5,1.2))
    r=session.post("https://api.payglocal.com/gl/v2/payments/dc/ipay",
        params={"x-gl-token":gl_token},
        headers=ph(gl_ref,ct="application/json",origin="https://api.payglocal.com",cfg=cfg),
        json={"isEnc":"false","kid":kid,"payload":{
            "cardNumber":CARD_NUM,"expiryMonth":CARD_MM,"expiryYear":CARD_YY,"cvv":CARD_CVV,
            "cardHolderName":CARD_NAME,"saveCard":False,
            "browserDetails":{"colorDepth":sc["depth"],"javaEnabled":False,"javaScriptEnabled":True,
                "language":lg.split(",")[0],"screenHeight":sc["h"],"screenWidth":sc["w"],
                "timeZone":-330,"userAgent":cfg["UA"]}}})
    result=r.json()

    return {
        "status": result.get("status",""),
        "message": result.get("message",""),
        "reason": result.get("reasonCode",""),
        "plan_name": "",
        "amount": 0,
        "number": recharge_number,
        "raw": result,
        "elapsed": time.time()-flow_start,
        "plans_json": plans_json
    }

# ═══════════════ TELEGRAM HANDLERS ═══════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Jio Recharge Bot*\n\n"
        "Main aapka Jio number card se recharge karunga.\n\n"
        "📱 Apna *10-digit Jio number* bhejo:",
        parse_mode="Markdown"
    )
    return MOBILE

async def get_mobile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    num = update.message.text.strip()
    if not re.fullmatch(r"\d{10}", num):
        await update.message.reply_text("❌ Invalid. 10-digit Jio number bhejo:")
        return MOBILE
    context.user_data["mobile"] = num
    await update.message.reply_text(
        "💳 *Card details bhejo* (format):\n\n"
        "`NUMBER|MM|YY|CVV`\n\n"
        "Example: `5131123456789012|03|30|086`",
        parse_mode="Markdown"
    )
    return CARD

async def get_card(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip()
    try:
        parts = raw.split("|")
        if len(parts) != 4:
            raise ValueError
        cn, cm, cy, cv = [p.strip() for p in parts]
        if len(cy) == 2:
            cy = "20" + cy
        if not (cn.isdigit() and cm.isdigit() and cy.isdigit() and cv.isdigit()):
            raise ValueError
        context.user_data["card"] = (cn, cm, cy, cv)
    except Exception:
        await update.message.reply_text("❌ Invalid format. Use: `5131...|03|30|086`", parse_mode="Markdown")
        return CARD

    try:
        await update.message.delete()
    except Exception:
        pass

    await update.message.reply_text("⏳ Fetching plans...")
    cfg = random.choice(PROFILES); lg = random.choice(LANGS)
    mobile = context.user_data["mobile"]
    session = requests.Session(impersonate=cfg["imp"])
    try:
        session.get("https://www.jio.com/", headers={"User-Agent": cfg["ua"],"Accept-Language":lg,"Upgrade-Insecure-Requests":"1"}, verify=False)
        r = session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/mobility/number/{mobile}",
            headers=jh("https://www.jio.com/", extra={"Accept":"application/json, text/plain, */*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"}, cfg={"UA":cfg["ua"],"SEC":cfg["ch"],"PLAT":cfg["plat"],"MOB":cfg["mob"],"IMP":cfg["imp"],"lg":lg}))
        lookup = r.json()
        if lookup.get("errorMessage") == "NOT_SUBSCRIBED_USER":
            await update.message.reply_text("❌ Yeh Jio number nahi hai.")
            return ConversationHandler.END
        primary = lookup.get("primaryService") or {}
        billing_type = lookup.get("billingType") or primary.get("billingType") or "PREPAID"
        next_value = lookup.get("nextPage") or billing_type
        r4 = session.get(f"https://www.jio.com/api/jio-recharge-service/recharge/plans/serviceId/{mobile}",
            headers=jh(f"https://www.jio.com/selfcare/recharge/mobility/plans/?serviceType=mobility&serviceId={mobile}&next={next_value}&billingType={billing_type}&entrysource=Widget",
                extra={"Accept":"*/*","Sec-Fetch-Dest":"empty","Sec-Fetch-Mode":"cors","Sec-Fetch-Site":"same-origin"},
                cfg={"UA":cfg["ua"],"SEC":cfg["ch"],"PLAT":cfg["plat"],"MOB":cfg["mob"],"IMP":cfg["imp"],"lg":lg}))
        plans_json = r4.json()
    except Exception as e:
        await update.message.reply_text(f"❌ Plans fetch fail: {e}")
        return ConversationHandler.END

    context.user_data["plans_json"] = plans_json

    popular = [11, 149, 239, 349, 599, 666, 719, 2999]
    avail = {}
    for p in iter_plans(plans_json):
        amt = int(p["amount"])
        if amt not in avail:
            avail[amt] = p

    keyboard = []
    for amt in popular:
        if amt in avail:
            p = avail[amt]
            keyboard.append([InlineKeyboardButton(
                f"₹{amt} — {(p['name'] or p['category'])[:30]}",
                callback_data=f"plan_{p['key']}"
            )])
    keyboard.append([InlineKeyboardButton("✏️ Custom Amount", callback_data="custom")])
    keyboard.append([InlineKeyboardButton("📋 List All Plans", callback_data="listall")])
    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])

    await update.message.reply_text(
        f"📱 *{mobile}*\n\n*Select Recharge Plan:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return PLAN_CHOOSE

async def plan_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "cancel":
        await q.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    if data == "custom":
        await q.edit_message_text("✏️ Custom amount bhejo (e.g. `239`):", parse_mode="Markdown")
        return PLAN_CUSTOM

    if data == "listall":
        plans = sorted(iter_plans(context.user_data["plans_json"]), key=lambda p: p["amount"])
        lines = []
        for i, p in enumerate(plans[:40], 1):
            lines.append(f"{i}. ₹{p['amount']:.0f} — {(p['name'] or p['category'])[:35]}")
        txt = "*All Plans:*\n\n" + "\n".join(lines) + "\n\nPlan ka number bhejo:"
        await q.edit_message_text(txt, parse_mode="Markdown")
        return PLAN_CUSTOM

    plan_key = data.replace("plan_", "")
    plans_json = context.user_data["plans_json"]
    picked = None
    for p in iter_plans(plans_json):
        if p["key"] == plan_key:
            picked = p
            break
    if not picked:
        await q.edit_message_text("❌ Plan not found.")
        return ConversationHandler.END

    context.user_data["picked"] = picked
    return await show_confirm(q, context)

async def plan_custom(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    plans_json = context.user_data["plans_json"]

    if txt.isdigit() and int(txt) <= 100:
        plans = sorted(iter_plans(plans_json), key=lambda p: p["amount"])
        idx = int(txt) - 1
        if 0 <= idx < len(plans):
            context.user_data["picked"] = plans[idx]
            return await show_confirm(update.message, context)

    try:
        amt = float(txt)
        p = plan_by_amount(plans_json, amt)
        if p:
            context.user_data["picked"] = p
            return await show_confirm(update.message, context)
    except Exception:
        pass

    await update.message.reply_text("❌ Invalid. Amount ya plan number bhejo:")
    return PLAN_CUSTOM

async def show_confirm(msg_or_query, context):
    picked = context.user_data["picked"]
    mobile = context.user_data["mobile"]
    cn, cm, cy, cv = context.user_data["card"]
    masked = f"{cn[:4]} {cn[4:8]} {cn[8:12]} {cn[12:]}"

    text = (
        f"*Confirm Recharge*\n\n"
        f"📱 Number: `{mobile}`\n"
        f"💳 Card: `{masked}`\n"
        f"📅 Expiry: `{cm}/{cy[2:]}`\n"
        f"📦 Plan: `{(picked['name'] or picked['category'])[:35]}`\n"
        f"💰 Amount: `₹{picked['amount']:.0f}`\n\n"
        f"Confirm karo?"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirm & Pay", callback_data="confirm_pay")],
        [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
    ])

    if hasattr(msg_or_query, "edit_message_text"):
        await msg_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await msg_or_query.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return CONFIRM

async def confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancel":
        await q.edit_message_text("❌ Cancelled.")
        return ConversationHandler.END

    mobile = context.user_data["mobile"]
    cn, cm, cy, cv = context.user_data["card"]
    picked = context.user_data["picked"]

    status_msg = await q.edit_message_text("⏳ *Starting...*", parse_mode="Markdown")

    loop = asyncio.get_event_loop()
    last_label = [""]
    def progress_cb(lbl):
        last_label[0] = lbl

    async def run():
        return await loop.run_in_executor(None, lambda: do_recharge(
            mobile, cn, cm, cy, cv, picked["key"], progress_cb=progress_cb
        ))

    task = asyncio.create_task(run())
    while not task.done():
        await asyncio.sleep(0.8)
        if last_label[0]:
            try:
                await status_msg.edit_text(f"⏳ *{last_label[0]}...*", parse_mode="Markdown")
            except Exception:
                pass

    try:
        result = task.result()
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: `{e}`", parse_mode="Markdown")
        return ConversationHandler.END

    plan_name = (picked["name"] or picked["category"] or "")[:35]
    amount = picked["amount"]

    st = result.get("status", "")
    if st in ("SUCCESS", "APPROVED"):
        text = (
            f"✅ *RECHARGE SUCCESSFUL*\n\n"
            f"📱 Number: `{mobile}`\n"
            f"📦 Plan: `{plan_name}`\n"
            f"💰 Amount: `₹{amount:.0f}`\n"
            f"⏱ Time: `{result['elapsed']:.1f}s`"
        )
    else:
        text = (
            f"❌ *RECHARGE FAILED*\n\n"
            f"📱 Number: `{mobile}`\n"
            f"📦 Plan: `{plan_name}`\n"
            f"💰 Amount: `₹{amount:.0f}`\n"
            f"⚠️ Status: `{st or 'FAILED'}`\n"
            f"💬 Message: `{result.get('message','')[:100]}`\n"
        )
        if result.get("reason"):
            text += f"🔍 Reason: `{result['reason'][:60]}`\n"

    raw = _json.dumps(result.get("raw", {}), indent=2)[:1500]
    text += f"\n\n*Raw Response:*\n```\n{raw}\n```"

    await status_msg.edit_text(text, parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END

# ═══════════════ MAIN ═══════════════
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MOBILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_mobile)],
            CARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_card)],
            PLAN_CHOOSE: [CallbackQueryHandler(plan_choose)],
            PLAN_CUSTOM: [MessageHandler(filters.TEXT & ~filters.COMMAND, plan_custom)],
            CONFIRM: [CallbackQueryHandler(confirm)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )
    app.add_handler(conv)
    print("🤖 Bot started...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
