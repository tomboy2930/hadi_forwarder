import os
import requests
import time
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from countries import COUNTRY_PREFIX

# Logging setup
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
        self.stats_page = f"{base_url}/agent/SMSCDRStats"
        self.api_url = f"{base_url}/agent/res/data_smscdr.php" if base_url else ""

    def get_headers(self):
        ref = self.stats_page if "2.59.169.96" in self.base_url else self.report_page
        return {
            "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Mobile Safari/537.36",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": ref
        }

    def solve_captcha(self, html):
        m = re.search(r"(\d+)\s*([+\-*xX])\s*(\d+)", html)
        if not m: return None
        a, op, b = int(m.group(1)), m.group(2), int(m.group(3))
        return str(a + b if op == "+" else a - b if op == "-" else a * b)

    def login(self):
        if self.panel_type == "api": 
            self.is_active = True
            return True
        try:
            logging.info(f"🔄 [{self.name}] Connecting...")
            r = self.session.get(self.login_page, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            captcha = self.solve_captcha(r.text)
            if not captcha: return False

            payload = {"username": self.username, "password": self.password, "capt": captcha}
            self.session.post(self.signin_url, data=payload, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)

            if "PHPSESSID" in self.session.cookies:
                target = self.stats_page if "2.59.169.96" in self.base_url else self.report_page
                r_rep = self.session.get(target, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
                m = re.search(r"sesskey['\" \s:=]+([A-Za-z0-9+/=]{10,})", r_rep.text)
                self.sesskey = m.group(1) if m else ""
                self.is_active = True
                logging.info(f"✅ [{self.name}] Login Successful.")
                return True
            return False
        except Exception:
            logging.warning(f"⚠️ [{self.name}] Login failed. Server or Network down.")
            return False

    def fetch_records(self):
        if self.panel_type == "api":
            try:
                h = {"User-Agent": "Mozilla/5.0", "Referer": "http://pscall.net/"}
                return requests.get(self.base_url, headers=h, timeout=20)
            except: return None
        
        today = datetime.now().strftime("%Y-%m-%d")
        params = {
            "fdate1": f"{today} 00:00:00", "fdate2": f"{today} 23:59:59",
            "fg": "0", "sEcho": "1", "iDisplayLength": "50",
            "iSortCol_0": "0", "sSortDir_0": "desc", "sesskey": self.sesskey,
            "_": str(int(time.time() * 1000))
        }
        try:
            return self.session.get(self.api_url, params=params, headers=self.get_headers(), timeout=25)
        except Exception:
            self.is_active = False
            return None

# ================= Utilities =================

def extract_otp(text):
    match = re.search(r"\b\d{3}\s\d{3}\b|\b\d{4,8}\b", str(text))
    return match.group(0).replace(" ", "") if match else None

def get_country_info(number):
    num_str = str(number)
    for prefix, flag in COUNTRY_PREFIX.items():
        if num_str.startswith(str(prefix)):
            return f"{flag} {prefix[:2].upper()}"
    return "🌍 Unknown"

def send_telegram(number, service, message):
    global SENT_IDS
    max_retries = 3
    for attempt in range(max_retries):
        try:
            otp = extract_otp(message)
            country_info = get_country_info(number)
            masked = f"{str(number)[:3]}****{str(number)[-4:]}"
            otp_display = f"<code>{otp}</code>" if otp else "N/A"
            
            caption = (
                f"📍 <b>Country:</b> {country_info}\n"
                f"📱 <b>Service:</b> {str(service).upper()}\n"
                f"📞 <b>Number:</b> <code>{masked}</code>\n"
                f"🔑 <b>OTP:</b> {otp_display}\n\n"
                f"💬 <b>Message:</b>\n{message}"
            )
            
            keyboard = {"inline_keyboard": [[
                {"text": "📢 Channel", "url": "https://t.me/dynamo_otp"},
                {"text": "🤖 Number Bot", "url": "https://t.me/dynamo_otp_bot"}
            ]]}
            
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
            r = requests.post(url, json={
                "chat_id": CHAT_ID, "text": caption, 
                "parse_mode": "HTML", "reply_markup": keyboard
            }, timeout=15)
            
            if r.status_code == 200:
                logging.info(f"🚀 Forwarded: {masked} | Service: {service}")
                return True
            elif r.status_code == 429: # Too many requests
                wait = r.json().get('parameters', {}).get('retry_after', 5)
                time.sleep(wait)
            else:
                break
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
    return False

def daily_cleanup():
    global SENT_IDS, LAST_CLEANUP
    current_date = datetime.now().date()
    if current_date > LAST_CLEANUP:
        SENT_IDS.clear()
        LAST_CLEANUP = current_date

# ================= Execution =================
panels = [
    SMSPanel(os.getenv("P1_NAME"), os.getenv("P1_BASE"), os.getenv("P1_USER"), os.getenv("P1_PASS")),
    SMSPanel(os.getenv("P2_NAME"), os.getenv("P2_BASE"), os.getenv("P2_USER"), os.getenv("P2_PASS")),
    SMSPanel(os.getenv("P4_NAME"), os.getenv("P4_BASE"), os.getenv("P4_USER"), os.getenv("P4_PASS")),
    SMSPanel("PS-CALL", "http://pscall.net/restapi/smsreport?key=SFFVQT1SS3WKjIB-gFBYREE=&start=0&length=10", "", "", panel_type="api")
]

logging.info("🚀 MONITORING STARTED (ULTRA STABLE MODE)...")

while True:
    daily_cleanup()
    try:
        for p in panels:
            if not p.is_active:
                p.login()

            r = p.fetch_records()
            if r and r.status_code == 200:
                try:
                    if 'json' in r.headers.get('Content-Type', '').lower() or r.text.strip().startswith('{'):
                        raw_data = r.json()
                        items = raw_data.get("data", []) if p.panel_type == "api" else raw_data.get("aaData", [])
                        
                        for row in items:
                            if p.panel_type == "api":
                                num, cli, sms, date = row.get("num"), row.get("cli"), row.get("sms"), row.get("dateadded")
                            else:
                                if len(row) < 6: continue
                                date, num, cli, sms = row[0], row[2], row[3], row[5]

                            if not str(num).replace('.','').isdigit() or str(num) == "0": continue

                            uid = f"{p.name}_{num}_{str(sms)[:20]}"
                            if uid not in SENT_IDS:
                                if send_telegram(num, cli, sms):
                                    SENT_IDS.add(uid)
                except Exception: pass
            else:
                if p.panel_type != "api": p.is_active = False
    except Exception as e:
        logging.error(f"😴 Main Loop Pause: Network Issue ({e})")
        time.sleep(10) # Network issue hole 10 sec wait korbe
    
    time.sleep(5)
