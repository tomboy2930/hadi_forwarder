import requests
import time
import re
import os
from datetime import datetime
from dotenv import load_dotenv # .env load korar jonno
from countries import COUNTRY_PREFIX

# .env file load kora hocche
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")

BASE = "http://185.2.83.39/ints"

# ... (baki URL variables eki thakbe)
LOGIN_PAGE = f"{BASE}/login"
SIGNIN_URL = f"{BASE}/signin"
DASHBOARD = f"{BASE}/agent/SMSDashboard"
REPORT_PAGE = f"{BASE}/agent/SMSCDRReports"
API = f"{BASE}/agent/res/data_smscdr.php"

session = requests.Session()
sesskey = None
sent_ids = set()

def get_headers(referer=None):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "X-Requested-With": "XMLHttpRequest",
        "Connection": "keep-alive",
        "Referer": referer if referer else REPORT_PAGE,
        "Accept-Language": "en-BD,en;q=0.9",
        "Accept-Encoding": "gzip, deflate"
    }

def solve_captcha(text):
    m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", text)
    if not m: return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    r = a + b if op == "+" else a - b if op == "-" else a * b
    return str(r)

def get_sesskey(html):
    m = re.search(r"sesskey[\"':=\s]+([A-Za-z0-9+/=]{10,})", html)
    return m.group(1) if m else None

def login():
    global sesskey
    print("🔄 Logging in...")
    try:
        r = session.get(LOGIN_PAGE, headers=get_headers(LOGIN_PAGE))
        captcha = solve_captcha(r.text)
        if not captcha: captcha = input("Manual Captcha: ")
        data = {"username": USERNAME, "password": PASSWORD, "capt": captcha}
        session.post(SIGNIN_URL, data=data, headers=get_headers(LOGIN_PAGE))
        if "PHPSESSID" not in session.cookies:
            print("❌ Login failed")
            return False
        print("✅ Login successful")
        session.get(DASHBOARD, headers=get_headers(DASHBOARD))
        r = session.get(REPORT_PAGE, headers=get_headers(REPORT_PAGE))
        sesskey = get_sesskey(r.text)
        return bool(sesskey)
    except: return False

# ================= Updated OTP Extract Regex =================
def extract_otp(text):
    # Regex updated to catch: 123456, 123-456, 123 456
    # It looks for 4 to 8 digits that might have a space or dash in middle
    m = re.search(r"\b(\d{2,4}[\s-]?\d{2,4})\b", str(text))
    if m:
        otp = m.group(0)
        # Dash ba space thakle seta bad diye sudhu number tuku nibe
        clean_otp = otp.replace("-", "").replace(" ", "")
        return clean_otp
    return ""

def detect_country(number):
    number = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if number.startswith(prefix): return flag
    return "🌍 Unknown"

def detect_service(text):
    t = str(text).lower()
    if "facebook" in t: return "📘 Facebook"
    if "whatsapp" in t: return "📱 WhatsApp"
    if "telegram" in t: return "✈️ Telegram"
    if "google" in t: return "🔵 Google"
    if "instagram" in t: return "📸 Instagram"
    return "📩 SMS"

# ================= Format Message with Monospace (Click to Copy) =================
def format_message(row):
    timestamp = row[0]
    number = str(row[2])
    service_name = row[3]
    message = str(row[5])

    otp = extract_otp(message)
    masked = number[:3] + "****" + number[-4:]

    # OTP ke ` ` (backtick) diye ghire deya hoyeche jate click korle copy hoy
    otp_display = f"`{otp}`" if otp else "Not found"

    return f"""
📍 Country: {detect_country(number)}
⏰ Time: {timestamp}
📱 Service: {detect_service(service_name)}
📞 Number: {masked}
🔑 OTP: {otp_display}

💬 Message:
{message}
"""

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [{"text": "OTP GROUP", "url": "https://t.me/dynamo_otp"}],
            [{"text": "Number Bot", "url": "https://t.me/dynamo_otp_bot"}]
        ]
    }
    try:
        # parse_mode="MarkdownV2" or "HTML" can be used. 
        # Using simple markdown-style backticks for the OTP.
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text.strip(),
            "reply_markup": keyboard,
            "parse_mode": "Markdown" 
        }, timeout=10)
    except:
        pass

# ... (fetch function and while loop will remain exactly the same as your code)
def fetch():
    today = datetime.now().strftime("%Y-%m-%d")
    params = {
        "fdate1": f"{today} 00:00:00",
        "fdate2": f"{today} 23:59:59",
        "sesskey": sesskey,
        "sEcho": "1",
        "iDisplayStart": "0",
        "iDisplayLength": "100",
        "iSortCol_0": "0",
        "sSortDir_0": "desc",
        "_": str(int(time.time() * 1000))
    }
    return session.get(API, params=params, headers=get_headers(REPORT_PAGE), timeout=30)

print("🚀 Smart OTP Forwarder Started")
if not login():
    print("Login failed. Exiting.")
    exit()

while True:
    try:
        r = fetch()
        if r.status_code != 200 or "aaData" not in r.text:
            login()
            continue
        
        rows = r.json().get("aaData", [])
        for row in rows:
            if not isinstance(row, list) or len(row) < 6: continue
            if not re.match(r"\d{4}-\d{2}-\d{2}", str(row[0])): continue

            unique_id = f"{row[0]}_{row[2]}_{str(row[5])[:30]}"
            if unique_id in sent_ids: continue

            sent_ids.add(unique_id)
            send_telegram(format_message(row))

        time.sleep(3)
    except Exception as e:
        time.sleep(5)
