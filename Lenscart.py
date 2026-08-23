#!/usr/bin/env python3
"""
Lenskart "Run For Frame" - Telegram Bot
Har account ke liye alag device aur unique voucher
Token: 8600716140:AAHJD07OkUOy2XtGk9tXsdOh_BvQWqdwltI
"""
import json
import random
import sys
import time
import uuid
import hashlib
import base64
import requests
from datetime import datetime
import io
import contextlib
import logging

from telegram import Update
from telegram.ext import (
Application,
CommandHandler,
MessageHandler,
filters,
ConversationHandler,
ContextTypes,
)

---------- Configuration ----------

BOT_TOKEN = ""8600716140:AAHJD07OkUOy2XtGk9tXsdOh_BvQWqdwltI
BASE = "https://api-gateway.juno.lenskart.com"
PHONE, OTP = range(2)

---------- Logging ----------

logging.basicConfig(
format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(name)

---------- Device pools ----------

BRANDS = ["xiaomi", "realme", "samsung", "oneplus", "oppo", "vivo"]
MODELS = {
"xiaomi": ["Mi 11X", "Redmi Note 10", "Mi 10", "Poco X3"],
"realme": ["RMX3031", "RMX3370", "RMX3360", "RMX3263"],
"samsung": ["SM-G998B", "SM-G991B", "SM-A526B", "SM-M515F"],
"oneplus": ["LE2115", "LE2125", "KB2001", "IN2015"],
"oppo": ["CPH2207", "CPH2249", "CPH2217"],
"vivo": ["V2024", "V2036", "V2041", "V2115"],
}
ANDROID_VERSIONS = ["13", "14"]

---------- Core Lenskart Device Class (with better error printing) ----------

class LenskartFakeDevice:
def init(self, phone: str, phone_code: str = "+91"):
self.phone = phone  # local number without country code
self.phone_code = phone_code
self.brand = random.choice(BRANDS)
self.model = random.choice(MODELS.get(self.brand, ["RMX3031"]))
self.android_version = random.choice(ANDROID_VERSIONS)
self.udid = self.generate_udid()
self.advertising_id = str(uuid.uuid4())
self.build_version = f"TP1A.220905.00{random.randint(1,9)}"
self.session_token = None
self.auth_token = None
self.user_id = None
self.customer_type = "EXISTING"
self.s = requests.Session()
self.x_assertion = self.generate_x_assertion()

def generate_udid(self):  
    return uuid.uuid4().hex[:16]  

def generate_x_assertion(self):  
    device_data = f"{self.udid}:{self.advertising_id}:{self.brand}:{self.model}:{self.phone}"  
    hash_obj = hashlib.sha256(device_data.encode())  
    hash_bytes = hash_obj.digest()  
    assertion = base64.b64encode(hash_bytes).decode('utf-8')  
    assertion = assertion.replace('+', '-').replace('/', '_')  
    while len(assertion) < 100:  
        assertion += random.choice("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")  
    return assertion[:100]  

def base_headers(self, extra: dict | None = None) -> dict:  
    h = {  
        "Content-Type": "application/json; charset=UTF-8",  
        "api_key": "valyoo123",  
        "x-api-client": "android",  
        "x-app-version": "5.8.2 (260713001)",  
        "appversion": "5.8.2 (260713001)",  
        "X-Build-Version": "260713001",  
        "x-country-code": "IN",  
        "x-country-code-override": "IN",  
        "x-accept-language": "en",  
        "accept-language": "en",  
        "x-customer-type": self.customer_type,  
        "udid": self.udid,  
        "uniqueId": self.advertising_id[:16],  
        "brand": self.brand,  
        "model": self.model,  
        "x-b3-traceid": str(int(time.time() * 1000)),  
        "User-Agent": f"Dalvik/2.1.0 (Linux; U; Android {self.android_version}; {self.model} Build/{self.build_version})",  
        "Accept-Encoding": "gzip",  
        "Connection": "Keep-Alive",  
    }  
    if self.phone:  
        h["x-customer-phone"] = self.phone  
        h["x-customer-phone-code"] = self.phone_code.replace("+", "")  
    if self.session_token:  
        h["x-session-token"] = self.session_token  
    if self.x_assertion:  
        h["x-assertion"] = self.x_assertion  
    if extra:  
        h.update(extra)  
    return h  

def post(self, path, body=None, params=None):  
    headers = self.base_headers()  
    url = f"{BASE}{path}"  
    if params:  
        url += "?" + "&".join([f"{k}={v}" for k, v in params.items()])  
    r = self.s.post(url, headers=headers, json=body, timeout=30)  
    return r  

def get(self, path, params=None):  
    headers = self.base_headers()  
    url = f"{BASE}{path}"  
    if params:  
        url += "?" + "&".join([f"{k}={v}" for k, v in params.items()])  
    r = self.s.get(url, headers=headers, timeout=30)  
    return r  

def create_session(self):  
    print("[1/5] Creating session...")  
    r = self.post("/v2/sessions", {})  
    if r.status_code == 200:  
        data = r.json()  
        self.session_token = data.get("result", {}).get("id")  
        print(f" ✅ Session: {self.session_token[:20]}...")  
        return True  
    print(f" ❌ Failed: {r.status_code}")  
    print(f"Response: {r.text[:500]}")  
    return False  

def send_otp(self):  
    if not self.session_token:  
        return None  
    print("[2/5] Sending OTP...")  
    body = {"phoneCode": self.phone_code, "telephone": self.phone}  
    r = self.post("/v3/customers/sendOtp", body)  
    if r.status_code == 200:  
        data = r.json()  
        res = data.get("result") or {}  
        self.customer_type = "NEW" if res.get("isNewUser") else "EXISTING"  
        print(f" ✅ OTP sent! New user: {res.get('isNewUser')}")  
        return res  
    print(f" ❌ Failed: {r.status_code}")  
    print(f"Response: {r.text[:500]}")  
    return None  

def verify_otp(self, code: str):  
    print("[3/5] Verifying OTP...")  
    body = {"code": code, "phoneCode": self.phone_code, "telephone": self.phone}  
    r = self.post("/v2/customers/authenticate/mobile", body)  
    if r.status_code == 200:  
        data = r.json()  
        res = data.get("result") or {}  
        self.auth_token = res.get("token")  
        self.user_id = res.get("user_id")  
        if self.auth_token:  
            self.session_token = self.auth_token  
        print(f" ✅ OTP verified! User ID: {self.user_id}")  
        print(f" 🔑 x-assertion: {self.x_assertion[:30]}...")  
        return res  
    print(f" ❌ Failed: {r.status_code}")  
    print(f"Response: {r.text[:500]}")  
    return None  

def me(self):  
    print("[4/5] Getting profile...")  
    r = self.get("/v2/customers/me")  
    if r.status_code == 200:  
        data = r.json()  
        result = data.get("result", {})  
        self.user_id = result.get("id")  
        print(f" ✅ User ID: {self.user_id}")  
        print(f" 📱 Device: {self.brand} {self.model}")  
        print(f" 🆔 UDID: {self.udid}")  
        return data  
    print(f" ❌ Failed: {r.status_code}")  
    print(f"Response: {r.text[:500]}")  
    return None  

def build_steps_payload(self, steps: int = 30000):  
    DAY_MS = 86400000  
    ist_offset_ms = 5.5 * 3600 * 1000  
    now_utc_ms = int(time.time() * 1000)  
    now_ist_ms = now_utc_ms + ist_offset_ms  
    today_midnight_ist = (now_ist_ms // DAY_MS) * DAY_MS  
    today_midnight_utc = today_midnight_ist - ist_offset_ms  
    step_counts = [0, 0, 0, 0, 0, 0, steps]  
    payload = []  
    for i in range(6, -1, -1):  
        ts = today_midnight_utc - i * DAY_MS  
        payload.append({  
            "distance": 0.0,  
            "steps": step_counts[i],  
            "timestamp": int(ts)  
        })  
    return payload  

def claim_reward(self, steps: int = 30000):  
    print(f"\n[5/5] Claiming reward with {steps} steps...")  
    body = self.build_steps_payload(steps)  
    params = {"campaignName": "run-for-frame"}  
    print(" 📊 Steps data (7 days):")  
    for i, entry in enumerate(body):  
        dt = datetime.fromtimestamp(entry["timestamp"] / 1000)  
        print(f" Day {i+1} ({dt.strftime('%d %b')}): {entry['steps']} steps")  
    print(f"\n 🔑 Device:")  
    print(f" Brand: {self.brand}")  
    print(f" Model: {self.model}")  
    print(f" UDID: {self.udid}")  
    print(f" x-assertion: {self.x_assertion[:30]}...")  
    r = self.post("/v2/customers/bff/campaign/eligibility", body, params)  
    print(f"\n 📥 Status: {r.status_code}")  
    try:  
        data = r.json()  
    except:  
        data = {"raw": r.text[:500]}  
    if r.status_code == 200:  
        res = data.get("result") or {}  
        if res.get("giftVoucher"):  
            print("\n" + "="*60)  
            print(f"🎉 REWARD UNLOCKED for {self.phone}!")  
            print("="*60)  
            print(f" 🏆 Tier: {res.get('tier')}")  
            print(f" 🎫 Voucher: {res.get('giftVoucher')}")  
            print(f" 📊 Steps: {res.get('steps')}")  
            if res.get('giftVoucherExpiryDate'):  
                exp = res.get('giftVoucherExpiryDate')  
                exp_dt = datetime.fromtimestamp(exp / 1000)  
                print(f" ⏰ Expiry: {exp_dt.strftime('%d %b %Y')}")  
            print("="*60)  
            filename = f"reward_{self.phone}.json"  
            with open(filename, "w") as f:  
                json.dump(data, f, indent=2)  
            print(f"💾 Saved to {filename}")  
            return res  
        else:  
            print(f"\n⚠️ {res.get('message', 'Reward not unlocked')}")  
            return res  
    else:  
        print(f"\n❌ Error: {r.status_code}")  
        print(f"Response: {r.text[:500]}")  
        return None  

def check_vouchers(self):  
    print("\n📋 Checking vouchers...")  
    r = self.get("/v2/customers/me/giftVoucher", params={"campaignName": "run-for-frame"})  
    if r.status_code == 200:  
        data = r.json()  
        print(json.dumps(data, indent=2, ensure_ascii=False))  
        return data  
    return None

---------- Telegram Bot Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"👋 Lenskart Run‑For‑Frame Bot\n\n"
"Use /claim to start claiming a reward.\n"
"You'll need your phone number and the OTP received.\n"
"Use /cancel to abort at any step.",
parse_mode="Markdown"
)

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"📱 Please enter your phone number without country code (e.g., 9876543210):",
parse_mode="Markdown"
)
return PHONE

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
raw_phone = update.message.text.strip()
# Remove any leading '+' and digits up to country code if present
if raw_phone.startswith('+'):
# Assume it's +91xxxxxxxxxx, keep only digits after country code
# Simple: remove leading '+' and then strip country code if it matches +91
# But to be safe, we'll just take the last 10 digits if length > 10
if len(raw_phone) > 10:
raw_phone = raw_phone[-10:]
else:
raw_phone = raw_phone[1:]  # remove '+'
# Now raw_phone should be local number
if not raw_phone.isdigit() or len(raw_phone) < 10:
await update.message.reply_text(
"❌ Invalid phone number. Please enter at least 10 digits (without country code)."
)
return PHONE

context.user_data["phone"] = raw_phone  
# Create device instance and send OTP  
device = LenskartFakeDevice(raw_phone)  # default phone_code "+91"  
context.user_data["device"] = device  

# Capture output from send_otp  
with io.StringIO() as buf, contextlib.redirect_stdout(buf):  
    device.create_session()  
    result = device.send_otp()  
    output = buf.getvalue()  

if result is None:  
    await update.message.reply_text(  
        f"❌ Failed to send OTP.\n\n```\n{output[:1500]}\n```",  
        parse_mode="Markdown"  
    )  
    return ConversationHandler.END  

await update.message.reply_text(  
    f"✅ OTP sent to {raw_phone}.\n"  
    f"New user: {result.get('isNewUser', 'unknown')}\n"  
    f"Please enter the OTP (4‑6 digits):"  
)  
return OTP

async def otp_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
otp = update.message.text.strip()
if not otp.isdigit() or len(otp) < 4:
await update.message.reply_text("❌ OTP must be a numeric code of 4‑6 digits. Try again:")
return OTP

device = context.user_data.get("device")  
if not device:  
    await update.message.reply_text("❌ Session expired. Please start again with /claim.")  
    return ConversationHandler.END  

# Capture the entire claim process  
with io.StringIO() as buf, contextlib.redirect_stdout(buf):  
    # Verify OTP  
    verify_res = device.verify_otp(otp)  
    if verify_res is None:  
        await update.message.reply_text(f"❌ OTP verification failed.\n\n```\n{buf.getvalue()[:1500]}\n```", parse_mode="Markdown")  
        return ConversationHandler.END  

    # Get profile  
    device.me()  

    # Claim reward  
    reward = device.claim_reward(steps=30000)  

    # Check vouchers  
    device.check_vouchers()  

    output = buf.getvalue()  

# Build final message  
msg = f"✅ *Claim process completed for {device.phone}*\n\n"  
msg += f"📱 Device: {device.brand} {device.model}\n"  
msg += f"🆔 UDID: {device.udid}\n"  
msg += f"🔑 x-assertion: {device.x_assertion[:30]}...\n\n"  

if reward and reward.get("giftVoucher"):  
    msg += "🎉 *REWARD UNLOCKED!*\n"  
    msg += f"🏆 Tier: {reward.get('tier')}\n"  
    msg += f"🎫 Voucher: {reward.get('giftVoucher')}\n"  
    msg += f"📊 Steps: {reward.get('steps')}\n"  
    if reward.get('giftVoucherExpiryDate'):  
        exp = reward.get('giftVoucherExpiryDate')  
        exp_dt = datetime.fromtimestamp(exp / 1000).strftime('%d %b %Y')  
        msg += f"⏰ Expiry: {exp_dt}\n"  
else:  
    msg += "⚠️ No reward unlocked. See details below:\n"  

# Append the captured log (truncate if too long)  
if len(output) > 2000:  
    output = output[:2000] + "\n... (truncated)"  
msg += f"\n```\n{output}\n```"  

await update.message.reply_text(msg, parse_mode="Markdown")  
return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text("❌ Operation cancelled.")
return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
logger.error(msg="Exception while handling an update:", exc_info=context.error)
if update and update.effective_message:
await update.effective_message.reply_text("❌ Something went wrong. Please try again later.")

---------- Main ----------

def main():
application = Application.builder().token(BOT_TOKEN).build()

conv_handler = ConversationHandler(  
    entry_points=[CommandHandler("claim", claim)],  
    states={  
        PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, phone_input)],  
        OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, otp_input)],  
    },  
    fallbacks=[CommandHandler("cancel", cancel)],  
)  

application.add_handler(CommandHandler("start", start))  
application.add_handler(conv_handler)  
application.add_error_handler(error_handler)  

print("🤖 Bot started. Press Ctrl+C to stop.")  
application.run_polling(allowed_updates=Update.ALL_TYPES)

if name == "main":
main()
