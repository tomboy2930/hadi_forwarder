import requests
import time
import re
from datetime import datetime
from countries import COUNTRY_PREFIX

BOT_TOKEN = "8707782067:AAHxMcYn0rxUqf7h9MmyRWCAgBXvG24pQKM"
CHAT_ID = "-1003762705250"

USERNAME = "Showrav39"
PASSWORD = "Showrav39"

BASE = "http://185.2.83.39/ints"

LOGIN_PAGE = f"{BASE}/login"
SIGNIN_URL = f"{BASE}/signin"
DASHBOARD = f"{BASE}/agent/SMSDashboard"
REPORT_PAGE = f"{BASE}/agent/SMSCDRReports"
API = f"{BASE}/agent/res/data_smscdr.php"

session = requests.Session()
sesskey = None

# Already forwarded messages (more reliable unique key)
sent_ids = set()

# ================= Headers (Updated to match your browser request) =================
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

# ================= Captcha =================
def solve_captcha(text):
    m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", text)
    if not m:
        return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    r = a + b if op == "+" else a - b if op == "-" else a * b
    print(f"Captcha solved: {a}{op}{b} = {r}")
    return str(r)

# ================= Sesskey =================
def get_sesskey(html):
    m = re.search(r"sesskey[\"':=\s]+([A-Za-z0-9+/=]{10,})", html)
    return m.group(1) if m else None

# ================= Login =================
def login():
    global sesskey
    print("🔄 Logging in...")

    r = session.get(LOGIN_PAGE, headers=get_headers(LOGIN_PAGE))
    captcha = solve_captcha(r.text)
    if not captcha:
        captcha = input("Manual Captcha: ")

    data = {"username": USERNAME, "password": PASSWORD, "capt": captcha}

    session.post(SIGNIN_URL, data=data, headers=get_headers(LOGIN_PAGE))

    if "PHPSESSID" not in session.cookies:
        print("❌ Login failed")
        return False

    print("✅ Login successful")

    session.get(DASHBOARD, headers=get_headers(DASHBOARD))
    r = session.get(REPORT_PAGE, headers=get_headers(REPORT_PAGE))
    sesskey = get_sesskey(r.text)
    print("Sesskey:", sesskey)

    return bool(sesskey)

# ================= OTP Extract =================
def extract_otp(text):
    m = re.search(r"\b\d{4,8}\b", str(text))
    return m.group(0) if m else ""

# ================= Country & Service =================
def detect_country(number):
    number = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if number.startswith(prefix):
            return flag
    return "🌍 Unknown"

def detect_service(text):
    t = str(text).lower()
    if "facebook" in t: return "📘 Facebook"
    if "whatsapp" in t: return "📱 WhatsApp"
    if "telegram" in t: return "✈️ Telegram"
    if "google" in t: return "🔵 Google"
    if "instagram" in t: return "📸 Instagram"
    return "📩 SMS"

# ================= Format Message =================
def format_message(row):
    timestamp = row[0]
    number = str(row[2])
    service_name = row[3]
    message = str(row[5])

    otp = extract_otp(message)
    masked = number[:3] + "****" + number[-4:]

    return f"""
📍 Country: {detect_country(number)}
⏰ Time: {timestamp}
📱 Service: {detect_service(service_name)}
📞 Number: {masked}
🔑 OTP: {otp if otp else 'Not found'}

💬 Message:
{message}
"""

# ================= Telegram Send =================
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    keyboard = {
        "inline_keyboard": [
            [{"text": "OTP GROUP", "url": "https://t.me/dynamo_otp"}],
            [{"text": "Number Bot", "url": "https://t.me/dynamo_otp_bot"}]
        ]
    }

    try:
        requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text.strip(),
            "reply_markup": keyboard
        }, timeout=10)
    except:
        pass

# ================= Fetch Latest Records =================
def fetch():
    today = datetime.now().strftime("%Y-%m-%d")

    params = {
        "fdate1": f"{today} 00:00:00",
        "fdate2": f"{today} 23:59:59",
        "frange": "",
        "fclient": "",
        "fnum": "",
        "fcli": "",
        "fg": "0",
        "sesskey": sesskey,
        "sEcho": "1",                    # Important for DataTables
        "iColumns": "9",
        "iDisplayStart": "0",
        "iDisplayLength": "100",         # Increased to catch more records
        "iSortCol_0": "0",
        "sSortDir_0": "desc",            # Latest first
        "_": str(int(time.time() * 1000))
    }

    return session.get(API, params=params, headers=get_headers(REPORT_PAGE), timeout=30)

# ================= MAIN LOOP =================
print("🚀 Smart OTP Forwarder Started - Latest + Missed messages supported")

if not login():
    print("Login failed. Exiting.")
    exit()

while True:
    try:
        r = fetch()

        if r.status_code != 200 or "aaData" not in r.text:
            print("⚠️ Session expired or error → Re-login")
            login()
            time.sleep(5)
            continue

        data = r.json()
        rows = data.get("aaData", [])

        new_count = 0
        for row in rows:
            if not isinstance(row, list) or len(row) < 6:
                continue

            # Skip summary rows
            if not re.match(r"\d{4}-\d{2}-\d{2}", str(row[0])):
                continue

            timestamp = str(row[0])
            number = str(row[2])
            msg_preview = str(row[5])[:30] if len(str(row[5])) > 30 else str(row[5])

            # More reliable unique ID to avoid duplicates
            unique_id = f"{timestamp}_{number}_{msg_preview}"

            if unique_id in sent_ids:
                continue

            sent_ids.add(unique_id)
            new_count += 1

            msg = format_message(row)
            print(f"📥 New/Missed OTP → {timestamp} | {number}")
            send_telegram(msg)

        if new_count == 0:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] No new OTPs")
        else:
            print(f"✅ Forwarded {new_count} new message(s)")

        time.sleep(3)   # Check every 3 seconds

    except Exception as e:
        print(f"Error: {e}")
        time.sleep(5)
