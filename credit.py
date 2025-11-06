import logging
import json
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
import os
from flask import Flask
import threading

# --- ⚙️ CONFIGURATION ---
BOT_TOKEN = "8462882669:AAHKzV9leqDxXm4tkx38Lw_wU7mINnmVCIc"
ADMIN_IDS = [7057912029]
SUPPORT_USER_ID = 7057912029
CHANNEL_URL = "https://t.me/pfp_kahi_nhi_milega"
PHONE_API_ENDPOINT = "https://demon.taitanx.workers.dev/?mobile={num}"
USER_DATA_FILE = "users.json"

INITIAL_CREDITS = 3
REFERRAL_CREDITS = 5
SEARCH_COST = 1  # Cost per search

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id_str = str(user.id)
    user_data = load_user_data()

    welcome_message = f"👋 Welcome back, {user.first_name}!"

    if user_id_str not in user_data:
        user_data[user_id_str] = {"credits": INITIAL_CREDITS, "referred_by": None}
        welcome_message = f"🎉 Welcome, {user.first_name}!\n\nYou have been given **{INITIAL_CREDITS} free credits** to start."

        if context.args and len(context.args) > 0:
            referrer_id = context.args[0]
            if referrer_id.isdigit() and referrer_id in user_data and referrer_id != user_id_str:
                user_data[user_id_str]["referred_by"] = referrer_id
                user_data[referrer_id]["credits"] += REFERRAL_CREDITS
                welcome_message += f"\nThanks for joining via a referral!"
                try:
                    await context.bot.send_message(
                        chat_id=int(referrer_id),
                        text=f"✅ User {user.first_name} joined using your link. You've earned **{REFERRAL_CREDITS} credits**!",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.warning(f"Could not notify referrer {referrer_id}: {e}")
        save_user_data(user_data)

    main_menu_text = f"{welcome_message}\n\nPlease send me a **10-digit mobile number** to start the search or select an option from the menu."

    keyboard = [
        [
            InlineKeyboardButton("Phone 📱", callback_data='search_phone')
        ],
        [
            InlineKeyboardButton("Check Credit 💰", callback_data='check_credit'),
            InlineKeyboardButton("Get Referral Link 🔗", callback_data='get_referral')
        ],
        [
            InlineKeyboardButton("Support 👨‍💻", callback_data='support'),
            InlineKeyboardButton("Join Channel 📢", url=CHANNEL_URL)
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(main_menu_text, reply_markup=reply_markup, parse_mode='Markdown')

async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = load_user_data()

    if query.data == 'search_phone':
        context.user_data['state'] = 'awaiting_phone'
        await query.message.reply_text("➡️ Please send me the 10-digit mobile number.")
    elif query.data == 'check_credit':
        credits = user_data.get(user_id_str, {}).get('credits', 0)
        credit_text = f"💰 You have **{credits}** credits."
        if user_id in ADMIN_IDS:
            credit_text = "👑 As an admin, you have **unlimited** credits."
        await context.bot.send_message(chat_id=user_id, text=credit_text, parse_mode='Markdown')
    elif query.data == 'get_referral':
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        message_text = (f"🔗 **Your Referral Link**\n\n`{referral_link}`\n\n"
                        f"Share this link. For every new user who starts the bot, you get **{REFERRAL_CREDITS} credits**! 🚀")
        await query.message.reply_text(text=message_text, parse_mode='Markdown')
    elif query.data == 'support':
        support_text = "Click the button below to contact the admin directly."
        keyboard = [[InlineKeyboardButton("Contact Admin 👨‍💻", url=f"tg://user?id={SUPPORT_USER_ID}")]]
        await query.message.reply_text(text=support_text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id_str = str(user.id)
    user_data = load_user_data()

    if user_id_str not in user_data:
        await update.message.reply_text("Please use the /start command first to register.")
        return

    is_admin = user.id in ADMIN_IDS
    if not is_admin and user_data[user_id_str].get("credits", 0) < SEARCH_COST:
        await update.message.reply_text(f"❌ **Out of Credits!**\nEach search costs {SEARCH_COST} credit. Refer friends or contact support to get more.", parse_mode='Markdown')
        return

    state = context.user_data.get('state')

    if state == 'awaiting_phone' or (update.message.text.strip().isdigit() and len(update.message.text.strip()) == 10):
        await perform_phone_lookup(update, context)
    else:
        await update.message.reply_text("🤔 Please select **Phone 📱** from the /start menu or send a **10-digit mobile number** directly.")

    if 'state' in context.user_data:
        del context.user_data['state']

async def perform_phone_lookup(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id_str = str(user.id)
    phone_number = update.message.text.strip()

    if not (phone_number.isdigit() and len(phone_number) == 10):
        await update.message.reply_text("❌ **Invalid Input**\nPlease send a valid 10-digit mobile number.", parse_mode='Markdown')
        return

    sent_message = await update.message.reply_text(f"Searching for mobile: `{phone_number}`...", parse_mode='Markdown')

    try:
        response = requests.get(PHONE_API_ENDPOINT.format(num=phone_number), timeout=15)
        response.raise_for_status()

        try:
            data = response.json()
        except json.JSONDecodeError:
            logger.error(f"JSON Decode Error for {phone_number}. Response Text: {response.text[:200]}...")
            await sent_message.edit_text("⚠️ **API Response Error:** Server ne aisa data bheja jise padha nahi jaa sakta. Kripya Admin se sampark karein.")
            return

        results = []
        if isinstance(data, dict):
            if 'data' in data and isinstance(data['data'], list):
                results = data['data']
            elif 'results' in data and isinstance(data['results'], list):
                results = data['results']
            elif any(key in data for key in ['mobile', 'name', 'address', 'Mobile', 'Name']):
                results = [data]
        elif isinstance(data, list):
            results = data

        if results:
            user_data = load_user_data()
            is_admin = user.id in ADMIN_IDS
            if not is_admin:
                user_data[user_id_str]["credits"] -= SEARCH_COST
                save_user_data(user_data)

            result_text = f"📱 **Indian Mobile Search Results** for `{phone_number}` ({len(results)} found)\n\n"

            for i, info in enumerate(results, 1):
                mobile_source = info.get('mobile', info.get('Mobile', info.get('phone', 'N/A')))
                name = info.get('name', info.get('Name', info.get('full_name', info.get('user_name', 'N/A'))))
                father_spouse_name = info.get('fname', info.get('Father', info.get('FatherName', info.get('father_name', 'N/A'))))
                address = info.get('address', info.get('Address', info.get('Loc', info.get('location', info.get('full_address', 'N/A')))))
                alt_mobile = info.get('alt', info.get('AltMobile', info.get('Alt', info.get('alt_mobile', info.get('AlternateMobile', info.get('AltMobileNo', info.get('mobile_2', 'N/A')))))))
                circle = info.get('circle', info.get('Circle', info.get('Operator', info.get('operator', info.get('Area', info.get('area', 'N/A'))))))
                aadhaar_id = info.get('id', info.get('Id', info.get('ID', info.get('id_number', info.get('Aadhaar', info.get('aadhaar_id', 'N/A'))))))

                record_text = (f"-- **Record {i}** -- \n"
                               f"📞 **Mobile/Source**: {mobile_source}\n"
                               f"👤 **Name**: {name}\n"
                               f"👨‍👦 **Father's/Spouse's Name**: {father_spouse_name}\n"
                               f"🏠 **Address**: {address}\n"
                               f"📞 **Alt Mobile**: {alt_mobile}\n"
                               f"🌍 **Circle**: {circle}\n"
                               f"🆔 **ID/Aadhaar**: `{aadhaar_id}`\n\n")
                result_text += record_text

            credits_left = user_data[user_id_str]['credits'] if not is_admin else "Unlimited"
            result_text += f"\n💳 Credits Left: **{credits_left}**"

            await sent_message.edit_text(result_text, parse_mode='Markdown')
        else:
            await sent_message.edit_text(f"🤷 No details found for mobile number `{phone_number}`.")

    except Exception as e:
        await sent_message.edit_text("⚠️ Error occurred. Contact admin.")
        logger.error(e)

async def add_credit(update: Update, context: CallbackContext) -> None:
    if update.effective_user.id not in ADMIN_IDS: return
    try:
        target_user_id, amount = context.args[0], int(context.args[1])
        user_data = load_user_data()
        if str(target_user_id) in user_data:
            user_data[str(target_user_id)]["credits"] += amount
            save_user_data(user_data)
            try:
                await context.bot.send_message(chat_id=target_user_id, text=f"🎉 An admin has added **{amount} credits** to your account!", parse_mode='Markdown')
            except Exception:
                await update.message.reply_text(f"⚠️ Could not notify the user.")
            await update.message.reply_text(f"✅ Added {amount} credits to user {target_user_id}.")
        else:
            await update.message.reply_text("❌ User not found.")
    except Exception:
        await update.message.reply_text("⚠️ Usage: `/addcredit <UserID> <Amount>`")

def main():
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("addcredit", add_credit))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot is running...")
    application.run_polling()

# --- 🧩 FAKE WEB SERVER for Render (keeps bot alive) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running successfully!"

if __name__ == '__main__':
    threading.Thread(target=main).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)