#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os
import sys
import asyncio
import time
import urllib.request
import urllib.parse
import json
from urllib.parse import urlparse

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.network.connection.tcpabridged import ConnectionTcpAbridged
from telethon.tl.types import PeerChannel

# ================== 环境变量 ==================
API_ID_RAW = os.environ.get("TG_API_ID", "").strip()
API_HASH = os.environ.get("TG_API_HASH", "").strip()
SESSION_STRING = os.environ.get("TG_SESSION_STRING", "").strip()
PROXY_SERVER = os.environ.get("PROXY_SERVER", "").strip()

GROUP_ID_RAW = os.environ.get("DNSHE_GROUP_ID", "").strip()

# Bot 推送（可选，不填则不推送）
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()

CHECKIN_COMMAND = "/checkin@DNSHEbot"

# ================== 参数校验 ==================
if not API_ID_RAW or not API_HASH or not SESSION_STRING:
    print("❌ 缺少必要的环境变量：请设置 TG_API_ID, TG_API_HASH, TG_SESSION_STRING")
    sys.exit(1)

try:
    API_ID = int(API_ID_RAW)
except ValueError:
    print(f"❌ TG_API_ID 不是合法整数: {API_ID_RAW!r}")
    sys.exit(1)

if not GROUP_ID_RAW:
    print("❌ 缺少环境变量 DNSHE_GROUP_ID，例如 -1003219886860")
    sys.exit(1)

try:
    DNSHE_GROUP_ID = int(GROUP_ID_RAW)
except ValueError:
    print(f"❌ DNSHE_GROUP_ID 不是合法整数: {GROUP_ID_RAW!r}")
    sys.exit(1)

print(f"API_ID 长度: {len(str(API_ID))}, API_HASH 长度: {len(API_HASH)}")
print(f"SESSION_STRING 长度: {len(SESSION_STRING)} 字符")
print(f"🎯 目标私有群 ID: {DNSHE_GROUP_ID}")
print(f"📝 签到命令: {CHECKIN_COMMAND}")
print(f"📣 Bot 推送: {'已启用' if TG_BOT_TOKEN and TG_CHAT_ID else '未启用'}")

if len(SESSION_STRING) < 50:
    print("⚠️ SESSION_STRING 过短，可能无效")
    sys.exit(1)

# ================== 代理解析 ==================
proxy = None
if PROXY_SERVER:
    parsed = urlparse(PROXY_SERVER)
    if parsed.scheme in ("http", "https"):
        proxy = ("http", parsed.hostname, parsed.port)
    elif parsed.scheme == "socks5":
        proxy = ("socks5", parsed.hostname, parsed.port)
    else:
        print(f"⚠️ 未知代理协议: {parsed.scheme}，忽略代理")
    if proxy:
        print(f"🔌 使用代理: {PROXY_SERVER}")

client = TelegramClient(
    StringSession(SESSION_STRING),
    API_ID,
    API_HASH,
    proxy=proxy,
    connection=ConnectionTcpAbridged,
)


# ================== Bot 推送函数 ==================
def push_via_bot(text: str):
    """用 Telegram Bot API 推送消息。失败不影响主流程。"""
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": TG_CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if '"ok":true' in body:
                print("📣 Bot 推送成功")
            else:
                print(f"⚠️ Bot 推送返回异常: {body[:200]}")
    except Exception as e:
        print(f"⚠️ Bot 推送失败: {e}")


async def resolve_group(client, group_id):
    try:
        return await client.get_entity(PeerChannel(group_id))
    except Exception as e:
        print(f"⚠️ PeerChannel 直接解析失败: {e}")
        print("🔍 尝试扫描对话列表查找群组...")
    try:
        async for dialog in client.iter_dialogs():
            if dialog.id == group_id:
                print(f"✅ 在对话列表中找到群组: {dialog.name}")
                return dialog.entity
    except Exception as e:
        print(f"❌ 扫描对话列表失败: {e}")
    raise ValueError(
        f"无法定位群组 {group_id}。请确认：\n"
        f"  1. 账号已加入该私有群\n"
        f"  2. DNSHE_GROUP_ID 是否正确（-100 开头）\n"
        f"  3. SESSION_STRING 是否来自同一个账号"
    )


async def main():
    # ---------- 登录 ----------
    try:
        await client.connect()
        if not await client.is_user_authorized():
            msg = "❌ DNSHE 签到失败：会话未授权（SESSION_STRING 可能已失效）"
            print(msg)
            push_via_bot(msg)
            sys.exit(1)
        print("✅ 会话授权检查通过")

        await client.start()
        me = await client.get_me()
        print(f"👤 登录用户: {me.first_name} (@{me.username or '无用户名'})")
    except Exception as e:
        msg = f"❌ DNSHE 签到失败：登录异常\n<code>{e}</code>"
        print(msg)
        push_via_bot(msg)
        sys.exit(1)

    # ---------- 定位群组 ----------
    try:
        group = await resolve_group(client, DNSHE_GROUP_ID)
        print(f"📌 已定位群组: {getattr(group, 'title', DNSHE_GROUP_ID)}")
    except Exception as e:
        msg = f"❌ DNSHE 签到失败：无法定位群组\n<code>{e}</code>"
        print(msg)
        push_via_bot(msg)
        sys.exit(1)

    # ---------- 发送签到命令 ----------
    send_time = time.time()
    try:
        sent_msg = await client.send_message(group, CHECKIN_COMMAND)
        print(f"📤 已在群组中发送: {CHECKIN_COMMAND}")
    except Exception as e:
        msg = f"❌ DNSHE 签到失败：发送命令异常\n<code>{e}</code>"
        print(msg)
        push_via_bot(msg)
        sys.exit(1)

    # ---------- 等待机器人回复 ----------
    print("⏳ 等待机器人回复...")
    timeout = 20
    reply_text = None

    while time.time() - send_time < timeout:
        try:
            messages = await client.get_messages(group, limit=20)
        except Exception as e:
            print(f"⚠️ 获取群消息失败: {e}")
            messages = []

        for msg in messages:
            if msg.out:
                continue
            if msg.date.timestamp() < send_time:
                continue

            text = msg.text or ""
            sender_username = ""
            try:
                if msg.sender:
                    sender_username = (getattr(msg.sender, "username", "") or "").lower()
            except Exception:
                pass

            is_reply_to_us = getattr(msg, "reply_to_msg_id", None) == sent_msg.id
            keyword_hit = any(k in text for k in ("签到", "积分", "checkin", "Checkin", "CHECKIN"))

            if sender_username == "dnshebot" or is_reply_to_us or keyword_hit:
                print("📩 机器人回复:")
                print(text)
                reply_text = text
                break

        if reply_text:
            break
        await asyncio.sleep(1)

    # ---------- 推送签到结果 ----------
    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
    if reply_text:
        # 群里消息 30 秒后会自动删除，这里把原文转存到 Bot 推送
        push_text = (
            f"✅ <b>DNSHE 签到成功</b>\n"
            f"👤 账号: {me.first_name} (@{me.username or '无'})\n"
            f"🕒 时间: {now_str}\n"
            f"💬 回复:\n<pre>{reply_text}</pre>"
        )
        push_via_bot(push_text)
    else:
        push_text = (
            f"⚠️ <b>DNSHE 签到超时</b>\n"
            f"👤 账号: {me.first_name} (@{me.username or '无'})\n"
            f"🕒 时间: {now_str}\n"
            f"命令 <code>{CHECKIN_COMMAND}</code> 已发送，但 20 秒内未收到机器人回复。\n"
            f"可能已签到成功但机器人静默。"
        )
        push_via_bot(push_text)

    await client.disconnect()
    print("🔒 连接已断开")


if __name__ == "__main__":
    asyncio.run(main())
