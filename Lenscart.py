#!/usr/bin/env python3
"""
Lenskart "Run For Frame" - Telegram Bot
"""
import os
import sys
import json
import random
import time
import uuid
import hashlib
import base64
import requests
from datetime import datetime
import io
import contextlib
import logging
import threading
import traceback

# ---------- Setup logging ----------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)
logger.info("=== LENSKART BOT STARTING ===")

# ---------- Imports ----------
try:
    from flask import Flask
    from telegram import Update
    from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, ContextTypes
    from telegram.error import Conflict, InvalidToken
except Exception as e:
    logger.error(f"Import error: {e}")
    traceback.print_exc()
    sys.exit(1)

# ---------- Configuration ----------
BOT_TOKEN = "8600716140:AAHJD07OkUOy2XtGk9tXsdOh_BvQWqdwltI"   # <-- Replace if regenerated
BASE = "https://api-gateway.juno.lenskart.com"
PHONE, OTP = range(2)

logger.info(f"Bot token loaded: {BOT_TOKEN[:10]}...")

# ---------- Device pools ----------
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

# ---------- Lenskart Device Class ----------
class LenskartFakeDevice:
    def __init__(self, phone: str, phone_code: str = "+91"):
        self.phone = phone
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
        logger.info("[1/5] Creating session...")
        r = self.post("/v2/sessions", {})
        if r.status_code == 200:
            data = r.json()
            self.session_token = data.get("result", {}).get("id")
            logger.info(f" ✅ Session: {self.session_token[:20]}...")
            return True
        logger.error(f" ❌ Session failed: {r.status_code} - {r.text[:200]}")
        return False

    def send_otp(self):
        if not self.session_token:
            return None
        logger.info("[2/5] Sending OTP...")
        body = {"phoneCode": self.phone_code, "telephone": self.phone}
        r = self.post("/v3/customers/sendOtp", body)
        if r.status_code == 200:
            data = r.json()
            res = data.get("result") or {}
            self.customer_type = "NEW" if res.get("isNewUser") else "EXISTING"
            logger.info(f" ✅ OTP sent! New user: {res.get('isNewUser')}")
            return res
        logger.error(f" ❌ OTP send failed: {r.status_code} - {r.text[:200]}")
        return None

    def verify_otp(self, code: str):
        logger.info("[3/5] Verifying OTP...")
        body = {"code": code, "phoneCode": self.phone_code, "telephone": self.phone}
        r = self.post("/v2/customers/authenticate/mobile", body)
        if r.status_code == 200:
            data = r.json()
            res = data.get("result") or {}
            self.auth_token = res.get("token")
            self.user_id = res.get("user_id")
            if self.auth_token:
                self.session_token = self.auth_token
            logger.info(f" ✅ OTP verified! User ID: {self.user_id}")
            return res
        logger.error(f" ❌ OTP verify failed: {r.status_code} - {r.text[:200]}")
        return None

    def me(self):
        logger.info("[4/5] Getting profile...")
        r = self.get("/v2/customers/me")
        if r.status_code == 200:
            data = r.json()
            result = data.get("result", {})
            self.user_id = result.get("id")
            logger.info(f" ✅ User ID: {self.user_id}")
            logger.info(f" 📱 Device: {self.brand} {self.model}")
            return data
        logger.error(f" ❌ Me failed: {r.status_code} - {r.text[:200]}")
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
        logger.info(f"\n[5/5] Claiming reward with {steps} steps...")
        body = self.build_steps_payload(steps)
        params = {"campaignName": "run-for-frame"}
        r = self.post("/v2/customers/bff/campaign/eligibility", body, params)
        logger.info(f" 📥 Status: {r.status_code}")
        try:
            data = r.json()
        except:
            data = {"raw": r.text[:500]}
        if r.status_code == 200:
            res = data.get("result") or {}
            if res.get("giftVoucher"):
                logger.info(f"🎉 REWARD UNLOCKED! Voucher: {res.get('giftVoucher')}")
                return res
            else:
                logger.info(f"⚠️ {res.get('message', 'Reward not unlocked')}")
                return res
        else:
            logger.error(f"❌ Claim error: {r.status_code} - {r.text[:200]}")
            return None

    def check_vouchers(self):
        logger.info("📋 Checking vouchers...")
        r = self.get("/v2/customers/me/giftVoucher", params={"campaignName": "run-for-frame"})
        if r.status_code == 200:
            data = r.json()
            logger.info(json.dumps(data, indent=2, ensure_ascii=False))
            return data
        return None

# ---------- Telegram Handlers ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Start from {update.effective_user.username}")
    await update.message.reply_text(
        "👋 *Lenskart Run‑For‑Frame Bot*\n\n"
        "Use /claim to start claiming a reward.\n"
        "You'll need your phone number and the OTP received.\n"
        "Use /cancel to abort at any step.",
        parse_mode="Markdown"
    )

async def claim(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"Claim from {update.effective_user.username}")
    await update.message.reply_text(
        "📱 Please enter your phone number **without** country code (e.g., `9876543210`):",
        parse_mode="Markdown"
    )
    return PHONE

async def phone_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw_phone = update.message.text.strip()
    if raw_phone.startswith('+'):
        if len(raw_phone) > 10:
            raw_phone = raw_phone[-10:]
        else:
            raw_phone = raw_phone[1:]
    if not raw_phone.isdigit() or len(raw_phone) < 10:
        await update.message.reply_text("❌ Invalid phone number. Please enter at least 10 digits.")
        return PHONE

    context.user_data["phone"] = raw_phone
    device = LenskartFakeDevice(raw_phone)
    context.user_data["device"] = device

    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
        device.create_session()
        result = device.send_otp()
        output = buf.getvalue()
    if output:
        logger.info(output)

    if result is None:
        await update.message.reply_text("❌ Failed to send OTP. Check logs.")
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
        await update.message.reply_text("❌ OTP must be numeric, 4‑6 digits. Try again:")
        return OTP

    device = context.user_data.get("device")
    if not device:
        await update.message.reply_text("❌ Session expired. Start /claim again.")
        return ConversationHandler.END

    with io.StringIO() as buf, contextlib.redirect_stdout(buf):
        verify_res = device.verify_otp(otp)
        if verify_res is None:
            await update.message.reply_text("❌ OTP verification failed. Check logs.")
            return ConversationHandler.END
        device.me()
        reward = device.claim_reward(steps=30000)
        device.check_vouchers()
        output = buf.getvalue()
    if output:
        logger.info(output)

    msg = f"✅ *Claim completed for {device.phone}*\n\n"
    msg += f"📱 Device: {device.brand} {device.model}\n"
    msg += f"🆔 UDID: {device.udid}\n"
    msg += f"🔑 x-assertion: {device.x_assertion[:30]}...\n\n"

    if reward and reward.get("giftVoucher"):
        msg += "🎉 *REWARD UNLOCKED!*\n"
        msg += f"🏆 Tier: {reward.get('tier')}\n"
        msg += f"🎫 Voucher: {reward.get('giftVoucher')}\n"
        if reward.get('giftVoucherExpiryDate'):
            exp = reward.get('giftVoucherExpiryDate')
            exp_dt = datetime.fromtimestamp(exp / 1000).strftime('%d %b %Y')
            msg += f"⏰ Expiry: {exp_dt}\n"
    else:
        msg += "⚠️ No reward unlocked."

    await update.message.reply_text(msg, parse_mode="Markdown")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Operation cancelled.")
    return ConversationHandler.END

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Telegram error: {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text("❌ Something went wrong. Please try again later.")

# ---------- Flask Web Server ----------
flask_app = Flask(__name__)

@flask_app.route('/')
def health():
    logger.info("Health check")
    return "Bot is running!", 200

@flask_app.route('/ping')
def ping():
    return "pong", 200

# ---------- Bot Runner ----------
def run_bot():
    logger.info("Starting Telegram bot...")
    try:
        application = Application.builder().token(BOT_TOKEN).build()
    except InvalidToken as e:
        logger.error(f"Invalid token: {e}. Regenerate your token at @BotFather and update the script.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error building application: {e}")
        traceback.print_exc()
        sys.exit(1)

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
    logger.info("Bot is ready – starting polling...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Conflict:
        logger.error("Conflict: another instance is running. Regenerate your token at @BotFather.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Unexpected error in polling: {e}")
        traceback.print_exc()
        sys.exit(1)

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Flask server on port {port}")
    flask_app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ---------- Main ----------
if __name__ == "__main__":
    logger.info("Starting main process...")
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    logger.info("Flask thread started.")
    run_bot()
