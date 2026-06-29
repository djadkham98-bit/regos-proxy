#!/usr/bin/env python3
"""
telegram_bot.py — Telegram-бот для отчётов Regos.

Установка зависимостей (один раз):
    pip install "python-telegram-bot[job-queue]" openai-whisper
    # ffmpeg должен быть установлен и доступен в PATH

Голосовые команды (отправьте голосовое сообщение):
    «Выручка за вчера»
    «Отчёт за 25 июня»
    «С 1 по 28 июня по Чорсу»
    «За июнь по всем магазинам»

Запуск:
    python telegram_bot.py

Команды:
    /report                       — выручка за вчера
    /report 2026-06-28            — за конкретный день
    /report 2026-06-01 2026-06-30 — за период
    /help                         — справка

После команды появляется inline-меню выбора магазинов.
Ежедневный отчёт за вчера автоматически отправляется в 9:00 (Ташкент UTC+5).
"""

import logging
import os
import re
import sys
import tempfile
import calendar as _calendar
import requests
from datetime import datetime, timedelta, timezone, time as dtime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)

# Конфиг: tg_config.py имеет приоритет; на Railway — переменные окружения
try:
    from tg_config import TG_TOKEN, TG_CHAT_ID, API_URL
except ImportError:
    TG_TOKEN   = os.environ.get("TG_TOKEN", "")
    TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")
    API_URL    = os.environ.get("API_URL", "https://web-production-a7040.up.railway.app")
    if not TG_TOKEN:
        print("Ошибка: задайте TG_TOKEN в переменных окружения Railway.")
        sys.exit(1)

# Модель Whisper: tiny (быстро) | small (точнее) | none (отключить)
_WHISPER_MODEL_NAME = os.environ.get("WHISPER_MODEL", "tiny")

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler()]
)

TZ = timezone(timedelta(hours=5))

MONTH_RU = [
    "", "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]

ALL_STORES = [
    "Кадышева", "Чорсу",
    "Азиз бозор", "Мархабо",
    "Согдиана", "Узбекистанский", "Bonasera Men",
]

GROUPS = [
    ("🏙 ТАШКЕНТ",   ["Кадышева", "Чорсу"]),
    ("🏔 САМАРКАНД", ["Азиз бозор", "Мархабо"]),
    ("🏪 BONASERA",  ["Согдиана", "Узбекистанский", "Bonasera Men"]),
]

# ── Состояние пользователя ────────────────────────────────────────────────────
# chat_id → { selected: set, date_start: str, date_end: str }
_state: dict = {}

def get_state(chat_id: int) -> dict:
    if chat_id not in _state:
        _state[chat_id] = {
            "selected":   set(ALL_STORES),
            "date_start": None,
            "date_end":   None,
        }
    return _state[chat_id]


# ── Утилиты ───────────────────────────────────────────────────────────────────
def fmt(n: float) -> str:
    return f"{round(n):,}".replace(",", " ")  # узкий неразрывный пробел

def fmt_date(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return f"{dt.day} {MONTH_RU[dt.month]} {dt.year}"

def period_label(s: str, e: str) -> str:
    return fmt_date(s) if s == e else f"{fmt_date(s)} — {fmt_date(e)}"

def validate_date(s: str) -> str:
    datetime.strptime(s, "%Y-%m-%d")   # бросает ValueError если невалидно
    return s

def yesterday() -> str:
    return (datetime.now(TZ) - timedelta(days=1)).strftime("%Y-%m-%d")


# ── Клавиатура выбора магазинов ───────────────────────────────────────────────
def build_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    sel = get_state(chat_id)["selected"]
    rows = []

    # Магазины по 2 в ряд
    stores = list(ALL_STORES)
    for i in range(0, len(stores), 2):
        row = []
        for store in stores[i:i + 2]:
            icon = "✅" if store in sel else "⬜"
            row.append(InlineKeyboardButton(
                f"{icon} {store}",
                callback_data=f"rg:t:{store}"
            ))
        rows.append(row)

    # Кнопки управления
    rows.append([
        InlineKeyboardButton("☑️ Все",       callback_data="rg:all"),
        InlineKeyboardButton("✖️ Сбросить",  callback_data="rg:none"),
    ])
    rows.append([InlineKeyboardButton("📊 Показать отчёт", callback_data="rg:show")])
    return InlineKeyboardMarkup(rows)

def menu_text(chat_id: int) -> str:
    s = get_state(chat_id)
    label = period_label(s["date_start"], s["date_end"])
    return f"📅 *{label}*\n\nВыберите магазины:"


# ── API ───────────────────────────────────────────────────────────────────────
def fetch_report(date_start: str, date_end: str) -> dict:
    url = f"{API_URL}/revenue-report?start={date_start}&end={date_end}"
    resp = requests.get(url, timeout=90)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        raise RuntimeError(f"API error: {data}")
    return data

def build_message(data: dict, selected: set) -> str:
    ds = data.get("date_start") or data.get("date", "")
    de = data.get("date_end")   or data.get("date", "")
    label = period_label(ds, de)

    lines = [f"📊 *Выручка за {label}*", ""]
    revenue = data.get("revenue", {})
    grand = 0

    for grp_label, stores in GROUPS:
        grp_lines = []
        for store in stores:
            if store not in selected:
                continue
            val = revenue.get(store, 0)
            if val > 0:
                grp_lines.append(f"  • {store}: {fmt(val)} сум")
                grand += val
        if grp_lines:
            lines.append(grp_label)
            lines.extend(grp_lines)
            lines.append("")

    lines.append("━━━━━━━━━━━━━")
    lines.append(f"*ИТОГО: {fmt(grand)} сум*")

    top5 = data.get("top5_qty", [])
    if top5:
        lines.append("")
        lines.append("🔥 *Топ-5 товаров*")
        medals = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for i, item in enumerate(top5):
            lines.append(f"{medals[i]} {item['name']} — {fmt(item['qty'])} шт")

    return "\n".join(lines)


# ── Хэндлеры команд ───────────────────────────────────────────────────────────
async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = get_state(chat_id)
    args = context.args or []

    try:
        if len(args) == 0:
            d = yesterday()
            s["date_start"] = s["date_end"] = d
        elif len(args) == 1:
            d = validate_date(args[0])
            s["date_start"] = s["date_end"] = d
        else:
            s["date_start"] = validate_date(args[0])
            s["date_end"]   = validate_date(args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат даты. Используй YYYY-MM-DD.\n\n"
            "Примеры:\n"
            "  /report\n"
            "  /report 2026-06-28\n"
            "  /report 2026-06-01 2026-06-30"
        )
        return

    s["selected"] = set(ALL_STORES)
    await update.message.reply_text(
        menu_text(chat_id),
        reply_markup=build_keyboard(chat_id),
        parse_mode="Markdown",
    )

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Команды бота:*\n\n"
        "`/report` — выручка за вчера\n"
        "`/report 2026-06-28` — за конкретный день\n"
        "`/report 2026-06-01 2026-06-30` — за период\n\n"
        "После команды появится меню выбора магазинов.\n"
        "Ежедневный отчёт приходит автоматически в 9:00.",
        parse_mode="Markdown",
    )


# ── Хэндлер inline-кнопок ────────────────────────────────────────────────────
async def cb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    if not data.startswith("rg:"):
        return

    chat_id = query.message.chat_id
    s = get_state(chat_id)
    action = data[3:]   # убираем "rg:"

    if action == "all":
        s["selected"] = set(ALL_STORES)
        await query.edit_message_text(
            menu_text(chat_id),
            reply_markup=build_keyboard(chat_id),
            parse_mode="Markdown",
        )

    elif action == "none":
        s["selected"] = set()
        await query.edit_message_text(
            menu_text(chat_id),
            reply_markup=build_keyboard(chat_id),
            parse_mode="Markdown",
        )

    elif action == "show":
        if not s["selected"]:
            await query.answer("Выберите хотя бы один магазин!", show_alert=True)
            return
        await query.edit_message_text("⏳ Загружаю данные…")
        try:
            report_data = fetch_report(s["date_start"], s["date_end"])
            text = build_message(report_data, s["selected"])
            await query.edit_message_text(text, parse_mode="Markdown")
        except Exception as e:
            await query.edit_message_text(f"❌ Ошибка: {e}")

    elif action.startswith("t:"):
        store = action[2:]
        if store in ALL_STORES:
            if store in s["selected"]:
                s["selected"].discard(store)
            else:
                s["selected"].add(store)
            await query.edit_message_text(
                menu_text(chat_id),
                reply_markup=build_keyboard(chat_id),
                parse_mode="Markdown",
            )


# ── Ежедневный отчёт (job_queue) ─────────────────────────────────────────────
async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    """Автоматически в 9:00 по Ташкенту (04:00 UTC)."""
    d = yesterday()
    try:
        data = fetch_report(d, d)
        text = build_message(data, set(ALL_STORES))
    except Exception as e:
        text = f"❌ Ошибка ежедневного отчёта: {e}"
    await context.bot.send_message(
        chat_id=TG_CHAT_ID,
        text=text,
        parse_mode="Markdown",
    )



# ── Whisper (голосовое управление) ───────────────────────────────────────────

_whisper_model = None

def _get_whisper():
    """Возвращает модель Whisper или None если WHISPER_MODEL=none."""
    global _whisper_model
    if _WHISPER_MODEL_NAME == "none":
        return None
    if _whisper_model is None:
        try:
            import whisper as _w
            _whisper_model = _w.load_model(_WHISPER_MODEL_NAME)
        except ImportError:
            raise RuntimeError(
                "openai-whisper не установлен. "
                "Запустите: pip install openai-whisper  "
                "или задайте WHISPER_MODEL=none"
            )
    return _whisper_model


_MONTH_NUM = {
    "янв": 1, "фев": 2, "мар": 3, "апр": 4, "май": 5,
    "июн": 6, "июл": 7, "авг": 8, "сен": 9, "окт": 10, "ноя": 11, "дек": 12,
}

def _match_month(word: str) -> int:
    """Возвращает номер месяца по фрагменту слова (0 если не распознано)."""
    w = word.lower()
    if w in ("мая", "май"):
        return 5
    return _MONTH_NUM.get(w[:3], 0)


def _parse_dates(text: str):
    """
    Парсит дату/период из русского текста.
    Возвращает (date_start, date_end) «YYYY-MM-DD» или None.

    Примеры:
      вчера / сегодня / позавчера
      за 25 июня
      с 1 по 28 июня
      за июнь
    """
    t = text.lower()
    now = datetime.now(TZ)

    if "позавчера" in t:
        d = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        return d, d
    if "вчера" in t:
        d = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return d, d
    if "сегодня" in t:
        d = now.strftime("%Y-%m-%d")
        return d, d

    # "с D1 по D2 Месяц"
    m = re.search(r"с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+(\w+)", t)
    if m:
        mn = _match_month(m.group(3))
        if mn:
            yr = now.year
            return (f"{yr}-{mn:02d}-{int(m.group(1)):02d}",
                    f"{yr}-{mn:02d}-{int(m.group(2)):02d}")

    # "за D Месяц"
    m = re.search(r"за\s+(\d{1,2})\s+(\w+)", t)
    if m:
        mn = _match_month(m.group(2))
        if mn:
            yr = now.year
            d = f"{yr}-{mn:02d}-{int(m.group(1)):02d}"
            return d, d

    # "за Месяц" — весь месяц
    m = re.search(r"за\s+(\w+)", t)
    if m:
        mn = _match_month(m.group(1))
        if mn:
            yr = now.year
            last = _calendar.monthrange(yr, mn)[1]
            return f"{yr}-{mn:02d}-01", f"{yr}-{mn:02d}-{last:02d}"

    return None


# Ключевые слова магазинов (порядок важен — длинные фразы раньше)
_STORE_KW = [
    (["кадышев"],                                       "Кадышева"),
    (["чорсу"],                                         "Чорсу"),
    (["азиз", "газиз", "бозор"],                        "Азиз бозор"),
    (["мархабо"],                                       "Мархабо"),
    (["согдиан"],                                       "Согдиана"),
    (["узбекистан"],                                    "Узбекистанский"),
    (["bonasera men", "бонасера мен", "bonasera man"],  "Bonasera Men"),
]
_BONASERA_KW  = ["bonasera", "бонасера"]
_BONASERA_ALL = ["Согдиана", "Узбекистанский", "Bonasera Men"]


def _parse_stores(text: str) -> list:
    """Извлекает список магазинов. Если не найдено — все магазины."""
    t = text.lower()

    if re.search(r"все\s+магазин|по\s+всем|все\s+отчёт|все\s+отчет", t):
        return list(ALL_STORES)

    found = []
    for keywords, store in _STORE_KW:
        for kw in keywords:
            if kw in t:
                if store not in found:
                    found.append(store)
                break

    # "bonasera/бонасера" без "men" → все три Bonasera-магазина
    for kw in _BONASERA_KW:
        if kw in t:
            for s in _BONASERA_ALL:
                if s not in found:
                    found.append(s)
            break

    return found if found else list(ALL_STORES)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Голосовое управление: Whisper → парсинг даты/магазинов → отчёт."""
    msg = update.message
    await msg.reply_text("🎙 Распознаю голос…")

    if _WHISPER_MODEL_NAME == "none":
        lines = [
            "🎙 Голосовые сообщения отключены в этой конфигурации.",
            "Используйте текстовые команды:",
            "`/report` — вчера",
            "`/report 2026-06-25` — конкретный день",
            "`/report 2026-06-01 2026-06-30` — период",
        ]
        await msg.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    tmp_path = None
    recognized = ""
    try:
        tg_file = await context.bot.get_file(msg.voice.file_id)
        with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
            tmp_path = tmp.name
        await tg_file.download_to_drive(tmp_path)

        model = _get_whisper()
        result = model.transcribe(tmp_path, language="ru", fp16=False)
        recognized = (result.get("text") or "").strip()

    except Exception as e:
        await msg.reply_text(f"❌ Ошибка распознавания: {e}")
        return
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

    if not recognized:
        await msg.reply_text(
            "❌ Не удалось распознать речь.\n"
            "Попробуйте говорить чётче и ближе к микрофону."
        )
        return

    await msg.reply_text(f'🗣 Распознано: «{recognized}»')

    # Парсим дату
    dates = _parse_dates(recognized)
    if dates is None:
        await msg.reply_text(
            "❓ Не смог понять *дату*.\n\n"
            "Примеры голосовых команд:\n"
            "• «Покажи выручку за вчера»\n"
            "• «Отчёт за 25 июня»\n"
            "• «С 1 по 28 июня по Чорсу»\n"
            "• «За июнь по всем магазинам»\n"
            "• «Выручка за сегодня по Кадышевой и Чорсу»",
            parse_mode="Markdown",
        )
        return

    date_start, date_end = dates
    stores = _parse_stores(recognized)

    stores_label = (
        ", ".join(stores)
        if len(stores) < len(ALL_STORES)
        else "все магазины"
    )
    await msg.reply_text(
        f"⏳ Загружаю: {period_label(date_start, date_end)} | {stores_label}…"
    )

    try:
        data = fetch_report(date_start, date_end)
        reply_text = build_message(data, set(stores))
        await msg.reply_text(reply_text, parse_mode="Markdown")
    except Exception as e:
        await msg.reply_text(f"❌ Ошибка при получении отчёта: {e}")


# ── Точка входа ───────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TG_TOKEN).build()

    app.add_handler(CommandHandler("report", cmd_report))
    app.add_handler(CommandHandler("start",  cmd_help))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CallbackQueryHandler(cb_handler))
    app.add_handler(MessageHandler(filters.VOICE, voice_handler))

    # 9:00 Ташкент = 04:00 UTC
    app.job_queue.run_daily(
        daily_report,
        time=dtime(hour=4, minute=0, tzinfo=timezone.utc),
    )

    print("🤖 Бот запущен. Ctrl+C для остановки.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
