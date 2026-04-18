import requests
import time
import re
import os
from datetime import datetime
from dotenv import load_dotenv 
from countries import COUNTRY_PREFIX

# .env file load
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

# Updated Base IP from your request
BASE = "http://2.59.169.96/ints"
LOGIN_PAGE = f"{BASE}/login"
SIGNIN_URL = f"{BASE}/signin"
DASHBOARD = f"{BASE}/agent/" # 302 Location onujayi
REPORT_PAGE = f"{BASE}/agent/SMSCDRStats" # Updated Referer onujayi
API = f"{BASE}/agent/res/data_smscdr.php"

session = requests.Session()
sesskey = None
sent_ids = set()

def get_headers(referer=None, is_json=False):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01" if is_json else "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-BD,en;q=0.9,ru-KZ;q=0.8",
        "Connection": "keep-alive",
        "Referer": referer if referer else LOGIN_PAGE,
    }
    if is_json:
        headers["X-Requested-With"] = "XMLHttpRequest"
    return headers

def solve_captcha(text):
    m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", text)
    if not m: return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    r = a + b if op == "+" else a - b if op == "-" else a * b
    print(f"✅ Captcha solved: {a}{op}{b} = {r}")
    return str(r)

def get_sesskey(html):
    # Apnar request-e sesskey chilo 'Q05RR0FSUElCUA=='
    m = re.search(r"sesskey[\"':=\s]+([A-Za-z0-9+/=]{10,})", html)
    return m.group(1) if m else None

def login():
    global sesskey
    print("🔄 Logging in to 2.59.169.96...")
    try:
        r = session.get(LOGIN_PAGE, headers=get_headers())
        captcha = solve_captcha(r.text)
        if not captcha: captcha = input("Manual Captcha: ")
        
        # Form Data based on 302 request
        data = {"username": USERNAME, "password": PASSWORD, "capt": captcha}
        
        login_res = session.post(SIGNIN_URL, data=data, headers=get_headers(LOGIN_PAGE))
        
        if "PHPSESSID" not in session.cookies:
            print("❌ Login failed: No Session ID")
            return False
        
        print("✅ Login successful")
        
        # Dashboard visit to stabilize session
        r_dash = session.get(DASHBOARD, headers=get_headers(LOGIN_PAGE))
        
        # Report page visit to grab Sesskey
        r_report = session.get(REPORT_PAGE, headers=get_headers(DASHBOARD))
        sesskey = get_sesskey(r_report.text)
        
        print(f"🔑 Sesskey Found: {sesskey}")
        return bool(sesskey)
    except Exception as e:
        print(f"❌ Login Error: {e}")
        return False

def extract_otp(text):
    m = re.search(r"\b(\d{2,4}[\s-]?\d{2,4})\b", str(text))
    if m:
        return m.group(0).replace("-", "").replace(" ", "")
    return ""

def detect_country(number):
    number = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if number.startswith(prefix): return flag
    return "🌍 Unknown"

def format_message(row):
    timestamp, number, service_name, message = row[0], str(row[2]), str(row[3]), str(row[5])
    otp = extract_otp(message)
    masked = f"{number[:3]}****{number[-4:]}"
    otp_display = f"<code>{otp}</code>" if otp else "Not found"

    return f"""
📍 <b>Country:</b> {detect_country(number)}
⏰ <b>Time:</b> {timestamp}
📱 <b>Service:</b> {service_name}
📞 <b>Number:</b> {masked}
🔑 <b>OTP:</b> {otp_display}

💬 <b>Message:</b>
{message}
"""

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Keyboard-e Number Bot button add kora hoyeche
    keyboard = {
        "inline_keyboard": [
            [{"text": "Update Channel", "url": "https://t.me/dynamo_otp"}],
            [{"text": "Number Bot", "url": "https://t.me/dynamo_otp_bot"}]
        ]
    }
    try:
        # Using parse_mode="HTML" to allow stars (*) to show normally
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text.strip(),
            "reply_markup": keyboard,
            "parse_mode": "HTML" 
        }, timeout=10)
    except:
        pass


def fetch():
    today = datetime.now().strftime("%Y-%m-%d")
    # Updated Params matching your browser GET request precisely
    params = {
        "fdate1": f"{today} 00:00:00",
        "fdate2": f"{today} 23:59:59",
        "frange": "",
        "fclient": "",
        "fnum": "",
        "fcli": "",
        "fg": "0",
        "sesskey": sesskey,
        "sEcho": "1",
        "iColumns": "9",
        "iDisplayStart": "0",
        "iDisplayLength": "25",
        "iSortCol_0": "0",
        "sSortDir_0": "desc",
        "_": str(int(time.time() * 1000))
    }
    return session.get(API, params=params, headers=get_headers(REPORT_PAGE, is_json=True), timeout=30)

# ================= Main Loop =================
print("🚀 Smart OTP Forwarder [IP: 2.59.169.96] Started")

if not login():
    print("❌ Login process failed. Exiting.")
    exit()

while True:
    try:
        r = fetch()
        
        if r.status_code != 200 or "aaData" not in r.text:
            print("⚠️ Session Expired. Re-logging...")
            if not login(): 
                time.sleep(10)
            continue
        
        rows = r.json().get("aaData", [])
        for row in rows:
            if not isinstance(row, list) or len(row) < 6: continue
            
            # Timestamp check to skip non-data rows
            if not re.match(r"\d{4}-\d{2}-\d{2}", str(row[0])): continue

            unique_id = f"{row[0]}_{row[2]}_{str(row[5])[:30]}"
            if unique_id in sent_ids: continue

            sent_ids.add(unique_id)
            send_telegram(format_message(row))
            print(f"📩 Forwarded OTP for: {row[2]}")

        # Keep memory clean
        if len(sent_ids) > 1000: sent_ids.clear()
        
        time.sleep(5)
    except Exception as e:
        print(f"Error: {e}")
        time.sleep(10)
