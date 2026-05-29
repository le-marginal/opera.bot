import os
import json
import logging
import sys
import re
from datetime import datetime, timedelta, timezone
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    FlexSendMessage, PostbackEvent, FollowEvent
)
from google import genai
from google.genai import types as genai_types

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

load_dotenv('/home/gaston/htdocs/opera.bot/.env')
app = Flask(__name__)

LINE_CHANNEL_SECRET       = os.getenv('LINE_CHANNEL_SECRET')
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_CHANNEL_ACCESS_TOKEN')
GOOGLE_CLOUD_PROJECT      = os.getenv('GOOGLE_CLOUD_PROJECT', 'projet-gaston-blondin')

line_bot_api = LineBotApi(LINE_CHANNEL_ACCESS_TOKEN)
handler      = WebhookHandler(LINE_CHANNEL_SECRET)

CACHE_FILE        = '/home/gaston/htdocs/opera.bot/menu_cache.json'
KNOWLEDGE_FILE    = '/home/gaston/htdocs/opera.bot/opera_knowledge.json'
CONVERSATIONS_DIR = '/home/gaston/htdocs/opera.bot/conversations'
STAFF_GROUP_ID    = None   # À renseigner quand le groupe staff sera créé
MANAGER_USER_ID   = 'tlL4Lw9POM'
GEMINI_MODEL      = 'gemini-2.5-flash'
CONVERSATION_TTL_HOURS = 24

os.makedirs(CONVERSATIONS_DIR, exist_ok=True)

# ====================== GEMINI ======================

os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "/home/gaston/.secrets/vertex-key.json"
gemini_client = genai.Client(
    vertexai=True,
    project=GOOGLE_CLOUD_PROJECT,
    location="us-central1"
)

# ====================== KNOWLEDGE BASE ======================

def load_knowledge() -> dict:
    try:
        with open(KNOWLEDGE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lecture knowledge: {e}")
        return {}

# ====================== MENU CACHE ======================

def load_menu_cache() -> dict:
    try:
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Erreur lecture menu_cache.json: {e}")
        return {}

def send_flex_from_cache(event, key, fallback_text, extra_keys=None):
    cache = load_menu_cache()
    item  = cache.get(key)
    if item:
        messages = [FlexSendMessage(alt_text=item.get('altText', key), contents=item['contents'])]
        if extra_keys:
            for extra_key in extra_keys:
                extra_item = cache.get(extra_key)
                if extra_item:
                    messages.append(FlexSendMessage(
                        alt_text=extra_item.get('altText', extra_key),
                        contents=extra_item['contents']
                    ))
        line_bot_api.reply_message(event.reply_token, messages)
        logger.info(f"Flex message '{key}' envoyé.")
    else:
        logger.warning(f"Clé '{key}' absente du cache.")
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=fallback_text))

# ====================== CONVERSATION STORE ======================

def _conv_path(user_id: str) -> str:
    return os.path.join(CONVERSATIONS_DIR, f"{user_id}.json")

def load_conversation(user_id: str) -> dict:
    path = _conv_path(user_id)
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                conv = json.load(f)
            updated = conv.get('updated_at', '')
            if updated:
                age = datetime.now(timezone.utc) - datetime.fromisoformat(updated)
                if age > timedelta(hours=CONVERSATION_TTL_HOURS):
                    logger.info(f"Conversation expirée pour {user_id}")
                    return _empty_conversation()
            return conv
        except Exception as e:
            logger.error(f"Erreur lecture conversation {user_id}: {e}")
    return _empty_conversation()

def _empty_conversation() -> dict:
    return {
        "mode": None,
        "reservation": {"date": None, "time": None, "name": None, "guests": None},
        "history": [],
        "updated_at": datetime.now(timezone.utc).isoformat()
    }

def save_conversation(user_id: str, conv: dict):
    conv['updated_at'] = datetime.now(timezone.utc).isoformat()
    try:
        with open(_conv_path(user_id), 'w', encoding='utf-8') as f:
            json.dump(conv, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Erreur sauvegarde conversation {user_id}: {e}")

def clear_conversation(user_id: str):
    path = _conv_path(user_id)
    if os.path.exists(path):
        os.remove(path)

# ====================== STAFF NOTIFICATION ======================

def notify_staff(reservation: dict, user_id: str):
    """Envoie un récap de réservation au manager et au groupe staff si configuré."""
    now_taipei = datetime.now(timezone(timedelta(hours=8))).strftime("%d/%m/%Y %H:%M")
    msg = (
        f"🔔 New Reservation — Opéra Taipei\n\n"
        f"👤 Name: {reservation.get('name', '?')}\n"
        f"📅 Date: {reservation.get('date', '?')}\n"
        f"🕘 Time: {reservation.get('time', '?')}\n"
        f"👥 Guests: {reservation.get('guests', '?')}\n\n"
        f"📱 LINE ID: {user_id}\n"
        f"⏱ Received: {now_taipei} (Taipei)"
    )
    # Toujours notifier le manager
    try:
        line_bot_api.push_message(MANAGER_USER_ID, TextSendMessage(text=msg))
        logger.info(f"✅ Notification manager envoyée pour {user_id}")
    except Exception as e:
        logger.error(f"Erreur notification manager: {e}")
    # Notifier le groupe staff si configuré
    if STAFF_GROUP_ID:
        try:
            line_bot_api.push_message(STAFF_GROUP_ID, TextSendMessage(text=msg))
        except Exception as e:
            logger.error(f"Erreur notification groupe staff: {e}")

# ====================== GEMINI — RÉSERVATION ======================

RESERVATION_SYSTEM = """
You are the virtual concierge of Opéra Taipei, a luxury skybar on the 15th floor of the Illume Hotel, Taipei. Your role is to collect reservation information from the client.

Opening hours (answer directly if asked, even during reservation flow):
- Tuesday, Wednesday, Thursday: 6:00 PM – 1:00 AM
- Friday, Saturday: 6:00 PM – 3:00 AM
- Sunday & Monday: Closed

You must collect exactly 4 pieces of information:
1. date
2. time
3. name (reservation name)
4. guests (number of people)

CRITICAL RULE — LANGUAGE:
Detect the language of the client's message and reply EXCLUSIVELY in that language.
- Client writes in Chinese (繁體中文) → reply in Chinese only.
- Client writes in English → reply in English only.
- Client writes in French → reply in French only.
- Client writes in Japanese → reply in Japanese only.
- Never mix languages. Never default to English if the client wrote in another language.

Other rules:
- Be polite and concise. 2-3 sentences maximum per reply.
- Ask one question at a time if information is missing.
- If the client provides multiple details at once, record them all and ask only for what's missing.
- If asked about hours or other general questions, answer them first, then continue collecting reservation info.
- When you have all 4 pieces of information, send the confirmation message AND the JSON summary line.

CRITICAL — CONFIRMATION MESSAGE:
When the reservation is complete, your message to the client MUST be (translated into their language):
"I have noted your reservation and am forwarding it to the Manager for confirmation."
Then add a brief recap of the details (date, time, name, guests) in 1-2 lines.
Nothing more. Do not add poetic flourishes or extra sentences.

Response format when all info is collected:
[CONFIRMATION MESSAGE IN CLIENT'S LANGUAGE + recap]
###JSON###
{"date": "...", "time": "...", "name": "...", "guests": N, "complete": true}

Response format when info is missing:
[QUESTION IN CLIENT'S LANGUAGE]
###JSON###
{"date": "..." or null, "time": "..." or null, "name": "..." or null, "guests": N or null, "complete": false}
"""

def call_gemini_reservation(history: list, new_message: str) -> tuple[str, dict]:
    try:
        contents = []
        for h in history[-10:]:
            role = "user" if h["role"] == "user" else "model"
            contents.append(genai_types.Content(
                role=role,
                parts=[genai_types.Part(text=h["text"])]
            ))
        contents.append(genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=new_message)]
        ))

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=RESERVATION_SYSTEM,
                temperature=0.7,
                max_output_tokens=500
            )
        )

        full_text = response.text or ""
        json_data = {"complete": False, "date": None, "time": None, "name": None, "guests": None}
        if "###JSON###" in full_text:
            parts = full_text.split("###JSON###")
            reply_text = parts[0].strip()
            try:
                json_data = json.loads(parts[1].strip())
            except Exception:
                pass
        else:
            reply_text = full_text.strip()

        return reply_text, json_data

    except Exception as e:
        logger.error(f"Erreur Gemini réservation: {e}")
        return "I'm sorry, I encountered a small issue. Please try again.", {"complete": False}

# ====================== GEMINI — CHAT LIBRE ======================

CHAT_SYSTEM_TEMPLATE = """
{persona}

Today is {today} (Taipei time).

Establishment info:
{knowledge}

CRITICAL — LANGUAGE:
Reply EXCLUSIVELY in the language the client used. Chinese → Chinese. English → English. French → French. Japanese → Japanese. Never mix.

CRITICAL — NATURAL ANSWERS:
Answer the actual question, not a generic dump of information.
- "Are you open tonight?" → Check today's day, answer YES/NO with hours. Example: "Yes, we're open tonight from 6 PM to 1 AM."
- "What time do you close?" → Give today's closing time directly.
- "Are you open on Sunday?" → "We're closed on Sundays."
Do NOT list all opening hours unless explicitly asked for the full schedule.

Other rules:
- 2-3 sentences maximum. Be direct and warm.
- For reservations, invite them to tap the "Reservations" button in the menu.
- Never invent information not in the knowledge base.
"""

def call_gemini_chat(history: list, new_message: str) -> str:
    try:
        knowledge = load_knowledge()
        today_taipei = datetime.now(timezone(timedelta(hours=8))).strftime("%A, %d %B %Y %H:%M")
        system = CHAT_SYSTEM_TEMPLATE.format(
            persona=knowledge.get("bot_persona", "You are the virtual concierge of Opéra Taipei."),
            today=today_taipei,
            knowledge=json.dumps(knowledge, ensure_ascii=False, indent=2)
        )

        contents = []
        for h in history[-8:]:
            role = "user" if h["role"] == "user" else "model"
            contents.append(genai_types.Content(
                role=role,
                parts=[genai_types.Part(text=h["text"])]
            ))
        contents.append(genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=new_message)]
        ))

        response = gemini_client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system,
                temperature=0.8,
                max_output_tokens=400
            )
        )

        return response.text or "..."

    except Exception as e:
        logger.error(f"Erreur Gemini chat: {e}")
        return "I apologize, I'm having a small technical issue. Please try again in a moment. 🙏"

# ====================== WEBHOOK ======================

@app.route("/webhook", methods=['POST'])
def webhook():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    logger.info(f"==> REQUETE RECUE. Signature: {signature}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Signature Invalide.")
        abort(400)
    except Exception as e:
        logger.error(f"Erreur globale: {e}")
    return 'OK'

# ====================== POSTBACK (boutons rich menu) ======================

@handler.add(PostbackEvent)
def handle_postback(event):
    data    = event.postback.data
    user_id = event.source.user_id
    logger.info(f"POSTBACK REÇU: {data} — user: {user_id}")

    if data == "action=info_hours":
        knowledge = load_knowledge()
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=knowledge.get("info_hours", "Please check our website for hours."))
        )

    elif data == "action=reservation":
        conv = _empty_conversation()
        conv['mode'] = 'reservation'
        save_conversation(user_id, conv)
        opening = (
            "Welcome to Opéra Taipei 🎭\n\n"
            "It would be my pleasure to assist with your reservation.\n"
            "For what date are you joining us?"
        )
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=opening))

    elif data == "action=drinks_menu":
        send_flex_from_cache(
            event, 'drinks_menu_1',
            "Our drinks menu is being updated. Please try again soon."
        )

    elif data == "action=food_menu":
        send_flex_from_cache(
            event, 'food_carousel',
            "Our food menu is being updated. Please try again soon."
        )

    elif data == "action=contact_staff":
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="I am connecting you with our manager right away. 🙏")
        )
        try:
            line_bot_api.push_message(
                MANAGER_USER_ID,
                TextSendMessage(text=f"📩 A client is requesting contact on the Opéra Taipei Official Line.\n👤 LINE ID: {user_id}")
            )
            logger.info(f"✅ Notification manager envoyée pour contact de {user_id}")
        except Exception as e:
            logger.error(f"Erreur notification manager (contact): {e}")

    else:
        logger.warning(f"Postback non géré: {data}")

# ====================== FOLLOW (nouveau follower) ======================

@handler.add(FollowEvent)
def handle_follow(event):
    user_id = event.source.user_id
    logger.info(f"Nouveau follower: {user_id}")
    welcome = (
        "Welcome to Opéra Taipei 🎭\n"
        "How may I be at your service?\n\n"
        "歡迎來到 Opéra Taipei 🎭\n"
        "請問有什麼我可以為您服務的嗎？"
    )
    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=welcome))
    except Exception as e:
        logger.error(f"Erreur message d'accueil: {e}")

# ====================== MESSAGE TEXTE ======================

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    if STAFF_GROUP_ID and hasattr(event.source, 'group_id') and event.source.group_id == STAFF_GROUP_ID:
        return

    user_id = event.source.user_id
    text    = event.message.text.strip()
    logger.info(f"Message texte reçu de {user_id}: {text[:80]}")

    conv = load_conversation(user_id)

    if conv.get('mode') == 'reservation':
        _handle_reservation_message(event, user_id, text, conv)
    else:
        _handle_chat_message(event, user_id, text, conv)

# ====================== FLOW RÉSERVATION ======================

def _handle_reservation_message(event, user_id: str, text: str, conv: dict):
    history = conv.get('history', [])
    reply_text, json_data = call_gemini_reservation(history, text)

    res = conv.get('reservation', {})
    for field in ('date', 'time', 'name', 'guests'):
        if json_data.get(field) is not None:
            res[field] = json_data[field]
    conv['reservation'] = res

    history.append({"role": "user",  "text": text})
    history.append({"role": "model", "text": reply_text})
    conv['history'] = history

    if json_data.get('complete'):
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))
        notify_staff(res, user_id)
        clear_conversation(user_id)
        logger.info(f"✅ Réservation complète pour {user_id}: {res}")
    else:
        save_conversation(user_id, conv)
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# ====================== CHAT LIBRE ======================

def _handle_chat_message(event, user_id: str, text: str, conv: dict):
    history = conv.get('history', [])
    reply_text = call_gemini_chat(history, text)

    history.append({"role": "user",  "text": text})
    history.append({"role": "model", "text": reply_text})
    conv['history'] = history[-20:]
    conv['mode']    = 'chat'
    save_conversation(user_id, conv)

    line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply_text))

# ====================== MAIN ======================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5002)
