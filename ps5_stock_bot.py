"""
PS5 Stock Bot — เฝ้าสต็อก store.sony.co.th แล้วแจ้งเตือนเข้า Telegram / Discord
ใช้แค่ Python 3 (ไม่ต้องลงไลบรารีเพิ่ม)

วิธีใช้:
  1) ตั้งค่าในส่วน CONFIG ด้านล่าง (อย่างน้อย Telegram หรือ Discord อย่างใดอย่างหนึ่ง)
  2) ทดสอบการแจ้งเตือน:   python ps5_stock_bot.py --test
  3) เริ่มเฝ้าสต็อก:        python ps5_stock_bot.py
"""

import json
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

# ======================= CONFIG =======================

# รุ่นที่ต้องการเฝ้า — ใส่ SKU (ไม่สนตัวพิมพ์/ขีด/ช่องว่าง) จับคู่แบบ "ขึ้นต้นด้วย"
WATCH_SKUS = [
    "CFI-2118A",      # PS5 Slim รุ่นมีช่องใส่แผ่น 1TB (CFI-2118 A01) 20,990 บาท
    # "CFI-2118B",    # PS5 Digital Edition 825GB (CFI-2118 B01) 18,790 บาท
    # "ASIA-00480",   # PS5 Slim Digital + จอย 2 ตัว 20,790 บาท
]

# Telegram: สร้างบอทกับ @BotFather -> ได้ token, แล้วหา chat_id (ดูวิธีในคำอธิบาย)
TELEGRAM_BOT_TOKEN = ""   # เช่น "123456789:AAH..."
TELEGRAM_CHAT_ID = ""     # เช่น "987654321"

# Discord: Server Settings > Integrations > Webhooks > New Webhook > Copy URL
DISCORD_WEBHOOK_URL = ""

CHECK_EVERY_SECONDS = 60      # เช็กทุกกี่วินาที (อย่าต่ำกว่า 30 เกรงใจเว็บ)

# ถ้ามีค่าใน Environment Variables (เช่น GitHub Secrets) จะใช้ค่านั้นแทน
import os
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN") or TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID") or TELEGRAM_CHAT_ID
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL") or DISCORD_WEBHOOK_URL
REMIND_EVERY_MINUTES = 10     # ถ้ายังมีของ จะเตือนซ้ำทุกกี่นาที

# ======================================================

STORE = "https://store.sony.co.th"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) PS5StockBot/1.0"


def norm(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def http_get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8"))


def http_post(url: str, data: dict, as_json: bool):
    if as_json:
        body = json.dumps(data).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": UA}
    else:
        body = urllib.parse.urlencode(data).encode("utf-8")
        headers = {"Content-Type": "application/x-www-form-urlencoded", "User-Agent": UA}
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def fetch_all_products():
    """ดึงสินค้าทั้งร้าน (Shopify /products.json) ทีละหน้า"""
    products, page = [], 1
    while True:
        data = http_get_json(f"{STORE}/products.json?limit=250&page={page}&_={int(time.time())}")
        batch = data.get("products", [])
        if not batch:
            break
        products.extend(batch)
        if len(batch) < 250:
            break
        page += 1
    return products


def find_watched(products):
    """คืน list ของ variant ที่ตรงกับ WATCH_SKUS"""
    targets = [norm(s) for s in WATCH_SKUS]
    found = []
    for p in products:
        for v in p.get("variants", []):
            sku = norm(v.get("sku"))
            if any(sku.startswith(t) for t in targets):
                found.append({
                    "key": f"{p['handle']}#{v['id']}",
                    "title": p.get("title", ""),
                    "sku": v.get("sku", ""),
                    "price": v.get("price", ""),
                    "available": bool(v.get("available")),
                    "url": f"{STORE}/products/{urllib.parse.quote(p['handle'])}",
                })
    return found


def notify(text: str):
    sent = False
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        try:
            http_post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                      {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": "false"},
                      as_json=False)
            sent = True
        except Exception as e:
            log(f"ส่ง Telegram ไม่สำเร็จ: {e}")
    if DISCORD_WEBHOOK_URL:
        try:
            http_post(DISCORD_WEBHOOK_URL, {"content": text}, as_json=True)
            sent = True
        except Exception as e:
            log(f"ส่ง Discord ไม่สำเร็จ: {e}")
    if not sent:
        log("ยังไม่ได้ตั้งค่า Telegram/Discord — แสดงในหน้าจอแทน")
    print("\a" + text)  # เสียงบี๊บในเทอร์มินัล


def log(msg: str):
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def main():
    if "--test" in sys.argv:
        notify("✅ ทดสอบ PS5 Stock Bot — ถ้าเห็นข้อความนี้แปลว่าแจ้งเตือนใช้งานได้")
        found = find_watched(fetch_all_products())
        if not found:
            log("⚠️ ไม่เจอ SKU ที่ตั้งไว้ในร้านเลย — ตรวจ WATCH_SKUS อีกที")
        for f in found:
            log(f"{'มีของ' if f['available'] else 'หมด'} | {f['title']} | {f['price']} บาท")
        return

    if "--once" in sys.argv:
        # โหมดเช็กครั้งเดียว (ใช้กับ GitHub Actions ที่รันทุก 5 นาที)
        found = find_watched(fetch_all_products())
        for f in found:
            log(f"{f['sku']}: {'มีของ' if f['available'] else 'หมด'}")
            if f["available"]:
                notify(f"🚨 PS5 มีของแล้ว!\n{f['title']}\nราคา {float(f['price']):,.0f} บาท\nรีบกด 👉 {f['url']}")
        if not found:
            log("ไม่พบ SKU ที่ตั้งไว้")
        return

    log(f"เริ่มเฝ้าสต็อก: {', '.join(WATCH_SKUS)} (ทุก ~{CHECK_EVERY_SECONDS} วิ)")
    last_state, last_alert, errors = {}, {}, 0

    while True:
        try:
            found = find_watched(fetch_all_products())
            errors = 0
            if not found:
                log("⚠️ ไม่เจอ SKU ที่ตั้งไว้ในหน้าร้าน (สินค้าอาจถูกซ่อน/เปลี่ยนรหัส)")
            for f in found:
                was = last_state.get(f["key"])
                now = f["available"]
                if now and (was is not True or time.time() - last_alert.get(f["key"], 0) > REMIND_EVERY_MINUTES * 60):
                    notify(f"🚨 PS5 มีของแล้ว!\n{f['title']}\nราคา {float(f['price']):,.0f} บาท\nรีบกด 👉 {f['url']}")
                    last_alert[f["key"]] = time.time()
                elif was is True and not now:
                    notify(f"❌ หมดอีกแล้ว: {f['title']}")
                last_state[f["key"]] = now
            log(" | ".join(f"{f['sku']}: {'✅ มีของ' if f['available'] else 'หมด'}" for f in found) or "ไม่พบสินค้า")
        except Exception as e:
            errors += 1
            log(f"เช็กไม่สำเร็จ ({errors}): {e}")
            if errors == 10:
                notify("⚠️ PS5 Stock Bot เช็กเว็บไม่ได้ติดกัน 10 ครั้งแล้ว ลองดูเครื่อง/เน็ตหน่อย")

        time.sleep(CHECK_EVERY_SECONDS + random.uniform(0, 15))


if __name__ == "__main__":
    main()
