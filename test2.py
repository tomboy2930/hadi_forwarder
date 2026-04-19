import os
import requests
import time
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from countries import COUNTRY_PREFIX

# Logging setup for production
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SENT_IDS = set()
LAST_CLEANUP = datetime.now().date()

class SMSPanel:
    def __init__(self, name, base_url, username, password, panel_type="login"):
        self.name = name
        self.base_url = base_url
        self.username = username
        self.password = password
        self.panel_type = panel_type
        self.session = requests.Session()
        self.sesskey = ""
        self.is_active = False
        
        self.login_page = f"{base_url}/login" if base_url else ""
        self.signin_url = f"{base_url}/signin" if base_url else ""
        self.report_page = f"{base_url}/agent/SMSCDRReports" if base_url else ""
        self.api_url = f"{base_url}/agent/res/data_smscdr.php" if base_url else ""

    def get_headers(self, referer=None):
        return {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer if referer else self.report_page
        }

    def solve_captcha(self, html):
        m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", html)
        if not m: return None
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        res = a + b if op == "+" else a - b if op == "-" else a * b
        return str(res)

    def login(self):
        if self.panel_type == "api": 
            self.is_active = True
            return True
        try:
            logging.info(f"🔄 [{self.name}] Connecting...")
            r = self.session.get(self.login_page, headers=self.get_headers(), timeout=15)
            captcha = self.solve_captcha(r.text)
            if not captcha: return False

            payload = {"username": self.username, "password": self.password, "capt": captcha}
            self.session.post(self.signin_url, data=payload, headers=self.get_headers(self.login_page), timeout=15)

            if "PHPSESSID" in self.session.cookies:
                r_rep = self.session.get(self.report_page, headers=self.get_headers(), timeout=15)
                m = re.search(r"sesskey['\" \s:=]+([A-Za-z0-9+/=]{10,})", r_rep.text)
                self.sesskey = m.group(1) if m else ""
                self.is_active = True
                logging.info(f"✅ [{self.name}] Login Successful.")
                return True
            return False
        except Exception as e:
            logging.error(f"❌ [{self.name}] Login Error: {e}")
            return False

    def fetch_records(self):
        if self.panel_type == "api":
            try:
                headers = {"User-Agent": "Mozilla/5.0", "Referer": "http://pscall.net/"}
                r = requests.get(self.base_url, headers=headers, timeout=15)
                return r
            except: return None
        else:
            today = datetime.now().strftime("%Y-%m-%d")
            params = {
                "fdate1": f"{today} 00:00:00", "fdate2": f"{today} 23:59:59",
                "fg": "0", "sEcho": "1", "iDisplayLength": "50",
                "iSortCol_0": "0", "sSortDir_0": "desc", "sesskey": self.sesskey
            }
            try:
                return self.session.get(self.api_url, params=params, headers=self.get_headers(), timeout=20)
            except: return None

# ================= Utilities =================

def extract_otp(text):
    # Standard 4-8 digit codes OR 3+3 digit space separated codes
    match = re.search(r"\b\d{3}\s\d{3}\b|\b\d{4,8}\b", str(text))
    if match:
        return match.group(0).replace(" ", "")
    return None

def get_country_info(number):
    num_str = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if num_str.startswith(str(prefix)):
            # রিটার্ন করবে ফ্ল্যাগ এবং কান্ট্রি কোড (e.g., 🇵🇪 PE)
            return f"{flag} {prefix[:2].upper()}"
    return "🌍 Unknown"

def escape_md(text):
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))

def send_telegram(number, service, message):
    global SENT_IDS
    try:
        otp = extract_otp(message)
        country_info = get_country_info(number)
        # Masking logic
        num_str = str(number)
        masked = f"{num_str[:3]}****{num_str[-4:]}"
        
        otp_display = f"`{otp}`" if otp else "N/A"
        
        # UI Card Formatting
        caption = (
            f"📍 *Country:* {country_info}\n"
            f"📱 *Service:* {escape_md(str(service).upper())}\n"
            f"📞 *Number:* `{escape_md(masked)}`\n"
            f"🔑 *OTP:* {otp_display}\n\n"
            f"💬 *Message:*\n{escape_md(message)}"
        )
        
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "📢 Channel", "url": "https://t.me/dynamo_otp"},
                    {"text": "🤖 Number Bot", "url": "https://t.me/dynamo_otp_bot"}
                ]
            ]
        }
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": CHAT_ID, 
            "text": caption, 
            "parse_mode": "MarkdownV2",
            "reply_markup": keyboard
        }, timeout=10)
        
        if r.status_code == 200:
            logging.info(f"🚀 Forwarded: {masked} | Service: {service}")
        else:
            logging.error(f"❌ Telegram API Error: {r.text}")
            
    except Exception as e:
        logging.error(f"❌ Processing Error: {e}")

def daily_cleanup():
    global SENT_IDS, LAST_CLEANUP
    current_date = datetime.now().date()
    if current_date > LAST_CLEANUP:
        logging.info("🧹 Performing daily cleanup of SENT_IDS...")
        SENT_IDS.clear()
        LAST_CLEANUP = current_date

# ================= Execution =================
panels = [
    SMSPanel(os.getenv("P1_NAME"), os.getenv("P1_BASE"), os.getenv("P1_USER"), os.getenv("P1_PASS")),
    SMSPanel(os.getenv("P2_NAME"), os.getenv("P2_BASE"), os.getenv("P2_USER"), os.getenv("P2_PASS")),
    SMSPanel("PS-CALL", "http://pscall.net/restapi/smsreport?key=SFFVQT1SS3WKjIB-gFBYREE=&start=0&length=10", "", "", panel_type="api")
]

logging.info("🚀 Production Bot Started...")

while True:
    daily_cleanup()
    
    for p in panels:
        if not p.is_active:
            p.login()

        r = p.fetch_records()
        if r and r.status_code == 200:
            try:
                raw_data = r.json()
                
                # Handling API type panels (Panel 3)
                if p.panel_type == "api":
                    items = raw_data.get("data", [])
                    for item in items:
                        num, cli, sms = item.get("num"), item.get("cli"), item.get("sms")
                        # Unique ID for API items
                        uid = f"P3_{item.get('dateadded')}_{num}_{sms[:15]}"
                        if uid not in SENT_IDS:
                            SENT_IDS.add(uid)
                            send_telegram(num, cli, sms)
                
                # Handling Login type panels (Panel 1 & 2)
                else:
                    data = raw_data.get("aaData", [])
                    for row in data:
                        if len(row) < 6: continue
                        # Filter junk rows
                        if not re.match(r"\d{4}-\d{2}-\d{2}", str(row[0])): continue
                        if "." in str(row[2]) or str(row[2]) == "0": continue

                        uid = f"{p.name}_{row[0]}_{row[2]}_{str(row[5])[:20]}"
                        if uid not in SENT_IDS:
                            SENT_IDS.add(uid)
                            send_telegram(row[2], row[3], row[5])
            except Exception as e:
                logging.debug(f"⚠️ Data parse error in {p.name}: {e}")
        else:
            # If request fails, mark panel as inactive to trigger re-login
            if p.panel_type != "api":
                p.is_active = False

    time.sleep(5)

