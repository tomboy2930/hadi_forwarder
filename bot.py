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
last_id = None
sesskey = None

# ================= Headers =================
def headers(referer=None):
    return {
        "User-Agent":"Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36 Chrome/137 Mobile Safari/537.36",
        "Accept":"application/json, text/javascript, */*; q=0.01",
        "X-Requested-With":"XMLHttpRequest",
        "Connection":"keep-alive",
        "Referer": referer if referer else BASE
    }

# ================= Captcha =================
def solve_captcha(text):
    m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", text)
    if not m: return None
    a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
    r = a+b if op=="+" else a-b if op=="-" else a*b
    print(f"Captcha solved: {a}{op}{b}={r}")
    return str(r)

# ================= Sesskey =================
def get_sesskey(html):
    m = re.search(r"sesskey[\"':=\s]+([A-Za-z0-9+/=]{10,})", html)
    if m:
        key = m.group(1)
        if "width" not in key.lower(): return key
    return None

# ================= Login =================
def login():
    global sesskey
    print("🔄 Logging in...")
    try:
        r = session.get(LOGIN_PAGE, headers=headers(LOGIN_PAGE))
        captcha = solve_captcha(r.text)
        if not captcha:
            captcha = input("Captcha: ")
        data = {"username":USERNAME,"password":PASSWORD,"capt":captcha}
        r = session.post(SIGNIN_URL, data=data, headers=headers(LOGIN_PAGE))
        if "PHPSESSID" not in session.cookies:
            print("❌ Login failed"); return False
        print("✅ Login success")
        session.get(DASHBOARD, headers=headers(DASHBOARD))
        time.sleep(1)
        r = session.get(REPORT_PAGE, headers=headers(REPORT_PAGE))
        time.sleep(1)
        sesskey = get_sesskey(r.text)
        if not sesskey:
            print("Sesskey not found → retry report page")
            r = session.get(REPORT_PAGE, headers=headers(REPORT_PAGE))
            sesskey = get_sesskey(r.text)
        print("Sesskey:", sesskey)
        return True
    except Exception as e:
        print("Login error:", e)
        return False

# ================= OTP =================
def extract_otp(text):
    m = re.search(r"\b\d{4,8}\b", str(text))
    return m.group() if m else ""

# ================= Country =================
def detect_country(number):
    number = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if number.startswith(prefix): return flag
    return "🌍 Unknown"

# ================= Service =================
def detect_service(text):
    t = str(text).lower()
    if "facebook" in t: return "📘 Facebook"
    if "whatsapp" in t: return "📱 WhatsApp"
    if "telegram" in t: return "✈️ Telegram"
    if "google" in t: return "🔵 Google"
    if "instagram" in t: return "📸 Instagram"
    return "📩 SMS"

# ================= Format =================
def format_message(row):
    timestamp = row[0]
    number = str(row[2])
    message = str(row[5])
    service_name = str(row[3]) if row[3] else "SMS"

    otp = extract_otp(message)
    masked = number[:3] + "****" + number[-4:]
    country = detect_country(number)
    service = detect_service(service_name)

    return f"""
📍 Country: {country}
⏰ Time: {timestamp}
📱 Service: {service}
📞 Number: {masked}
🔑 OTP: {otp if otp else 'Not found'}

💬 Full message:
{message}
"""

# ================= Telegram =================
def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    keyboard = {"inline_keyboard":[
        [{"text":"OTP GROUP","url":"https://t.me/dynamo_otp"}],
        [{"text":"Number Bot","url":"https://t.me/dynamo_otp_bot"}]
    ]}
    try:
        requests.post(url,json={"chat_id":CHAT_ID,"text":text,"reply_markup":keyboard},timeout=10)
    except: pass

# ================= Fetch =================
def fetch():
    today = datetime.now().strftime("%Y-%m-%d")
    params = {
        "fdate1": f"{today} 00:00:00",
        "fdate2": f"{today} 23:59:59",
        "frange":"","fclient":"","fnum":"","fcli":"","fg":"0",
        "sesskey":sesskey,
        "sEcho":"1","iColumns":"9","sColumns":",,,,,,,,",
        "iDisplayStart":"0","iDisplayLength":"25",
        "mDataProp_0":"0","mDataProp_1":"1","mDataProp_2":"2","mDataProp_3":"3",
        "mDataProp_4":"4","mDataProp_5":"5","mDataProp_6":"6","mDataProp_7":"7","mDataProp_8":"8",
        "sSearch":"","bRegex":"false",
        "iSortCol_0":"0","sSortDir_0":"desc","iSortingCols":"1",
        "_": str(int(time.time()*1000))
    }
    return session.get(API, params=params, headers=headers(REPORT_PAGE), timeout=30)

# ================= MAIN =================
print("🚀 Bot Started (Instant OTP)")

if not login(): exit()

while True:
    try:
        r = fetch()
        if r.status_code == 503:
            wait = 30
            print("503 detected → wait", wait)
            time.sleep(wait)
            continue
        if r.status_code != 200:
            print("Session expired → re-login")
            login()
            continue
        try:
            data = r.json()
        except:
            print("JSON parse error"); time.sleep(2); continue
        rows = data.get("aaData", [])
        if rows:
            latest = rows[0]
            cid = latest[0]
            if cid != last_id:
                msg = format_message(latest)
                send_telegram(msg)
                last_id = cid
                print("✅ OTP forwarded (instant)")
        time.sleep(2)
    except Exception as e:
        print("Error:", e)
        time.sleep(2)
