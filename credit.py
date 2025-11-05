import logging
import json
import requests
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, error
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler

# --- ⚙️ CONFIGURATION ---
BOT_TOKEN = "8462882669:AAHKzV9leqDxXm4tkx38Lw_wU7mINnmVCIc"
ADMIN_IDS = [7057912029]
SUPPORT_USER_ID = 7057912029
CHANNEL_URL = "https://t.me/pfp_kahi_nhi_milega"
PHONE_API_ENDPOINT = "https://demon.taitanx.workers.dev/?mobile={num}"

USER_DATA_FILE = "users.json"
INITIAL_CREDITS = 3
REFERRAL_CREDITS = 5
SEARCH_COST = 1

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- 💾 Data Management ---
def load_user_data():
    try:
        with open(USER_DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_user_data(data):
    with open(USER_DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)


# --- 🤖 START COMMAND ---
async def start(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id_str = str(user.id)
    user_data = load_user_data()

    welcome_message = f"👋 Welcome back, {user.first_name}!"

    if user_id_str not in user_data:
        user_data[user_id_str] = {"credits": INITIAL_CREDITS, "referred_by": None}
        welcome_message = f"🎉 Welcome, {user.first_name}!\n\nYou have been given **{INITIAL_CREDITS} free credits** to start."
        save_user_data(user_data)

    main_menu_text = f"{welcome_message}\n\nPlease send me a **10-digit mobile number** to start the search or select an option below 👇"

    keyboard = [
        [InlineKeyboardButton("Phone 📱", callback_data='search_phone')],
        [
            InlineKeyboardButton("Check Credit 💰", callback_data='check_credit'),
            InlineKeyboardButton("Get Referral Link 🔗", callback_data='get_referral')
        ],
        [
            InlineKeyboardButton("Support 👨‍💻", callback_data='support'),
            InlineKeyboardButton("Join Channel 📢", url=CHANNEL_URL)
        ]
    ]

    # 👑 Admin-only options
    if user.id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("🧮 Manage Credits", callback_data='manage_credits')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(main_menu_text, reply_markup=reply_markup, parse_mode='Markdown')


# --- ⚙️ BUTTON HANDLER ---
async def button_handler(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_id_str = str(user_id)
    user_data = load_user_data()

    # Normal User Options
    if query.data == 'search_phone':
        context.user_data['state'] = 'awaiting_phone'
        await query.message.reply_text("➡️ Send me a 10-digit mobile number.")
    elif query.data == 'check_credit':
        credits = user_data.get(user_id_str, {}).get('credits', 0)
        text = f"💰 You have **{credits}** credits." if user_id not in ADMIN_IDS else "👑 You have **unlimited credits**."
        await query.message.reply_text(text, parse_mode='Markdown')
    elif query.data == 'get_referral':
        bot_username = (await context.bot.get_me()).username
        referral_link = f"https://t.me/{bot_username}?start={user_id}"
        msg = f"🔗 **Your Referral Link**\n\n`{referral_link}`\n\nEach new user gives you **{REFERRAL_CREDITS} credits!**"
        await query.message.reply_text(msg, parse_mode='Markdown')
    elif query.data == 'support':
        support_keyboard = [[InlineKeyboardButton("Contact Admin 👨‍💻", url=f"tg://user?id={SUPPORT_USER_ID}")]]
        await query.message.reply_text("Need help? Tap below 👇", reply_markup=InlineKeyboardMarkup(support_keyboard))

    # 👑 Admin Manage Credit Panel
    elif query.data == 'manage_credits':
        if user_id in ADMIN_IDS:
            keyboard = [
                [InlineKeyboardButton("➕ Add Credits", callback_data='add_credits')],
                [InlineKeyboardButton("➖ Deduct Credits", callback_data='deduct_credits')],
                [InlineKeyboardButton("👁️ Check User Credits", callback_data='check_user_credits')]
            ]
            await query.message.reply_text("🧮 Choose an admin action:", reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await query.message.reply_text("❌ Only admins can access this panel.")

    elif query.data == 'add_credits':
        context.user_data['state'] = 'awaiting_target_user_add'
        await query.message.reply_text("👤 Send the **User ID** to add credits to.")

    elif query.data == 'deduct_credits':
        context.user_data['state'] = 'awaiting_target_user_deduct'
        await query.message.reply_text("👤 Send the **User ID** to deduct credits from.")

    elif query.data == 'check_user_credits':
        context.user_data['state'] = 'awaiting_target_user_check'
        await query.message.reply_text("👁️ Send the **User ID** whose credits you want to check.")


# --- 💬 HANDLE MESSAGES ---
async def handle_message(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id = str(user.id)
    user_data = load_user_data()

    # Admin credit management flow
    state = context.user_data.get('state')

    # --- ADD CREDITS FLOW ---
    if state == 'awaiting_target_user_add':
        context.user_data['target_user_id'] = update.message.text.strip()
        context.user_data['state'] = 'awaiting_credit_amount_add'
        await update.message.reply_text("💰 Send the **amount of credits** to add.")
        return

    elif state == 'awaiting_credit_amount_add':
        try:
            amount = int(update.message.text.strip())
            target = context.user_data['target_user_id']
            if target not in user_data:
                await update.message.reply_text("❌ User not found.")
            else:
                user_data[target]["credits"] += amount
                save_user_data(user_data)
                await update.message.reply_text(f"✅ Added **{amount} credits** to `{target}`.", parse_mode='Markdown')
                try:
                    await context.bot.send_message(chat_id=int(target),
                        text=f"🎉 Admin added **{amount} credits** to your account!", parse_mode='Markdown')
                except:
                    pass
        except:
            await update.message.reply_text("⚠️ Invalid amount.")
        finally:
            context.user_data.clear()
        return

    # --- DEDUCT CREDITS FLOW ---
    elif state == 'awaiting_target_user_deduct':
        context.user_data['target_user_id'] = update.message.text.strip()
        context.user_data['state'] = 'awaiting_credit_amount_deduct'
        await update.message.reply_text("💳 Send the **amount of credits** to deduct.")
        return

    elif state == 'awaiting_credit_amount_deduct':
        try:
            amount = int(update.message.text.strip())
            target = context.user_data['target_user_id']
            if target not in user_data:
                await update.message.reply_text("❌ User not found.")
            else:
                user_data[target]["credits"] = max(0, user_data[target]["credits"] - amount)
                save_user_data(user_data)
                await update.message.reply_text(f"✅ Deducted **{amount} credits** from `{target}`.", parse_mode='Markdown')
                try:
                    await context.bot.send_message(chat_id=int(target),
                        text=f"⚠️ Admin deducted **{amount} credits** from your account.", parse_mode='Markdown')
                except:
                    pass
        except:
            await update.message.reply_text("⚠️ Invalid amount.")
        finally:
            context.user_data.clear()
        return

    # --- CHECK USER CREDITS FLOW ---
    elif state == 'awaiting_target_user_check':
        target = update.message.text.strip()
        if target not in user_data:
            await update.message.reply_text("❌ User not found.")
        else:
            credits = user_data[target]["credits"]
            await update.message.reply_text(f"👁️ User `{target}` has **{credits} credits**.", parse_mode='Markdown')
        context.user_data.clear()
        return

    # --- PHONE LOOKUP ---
    if state == 'awaiting_phone' or (update.message.text.strip().isdigit() and len(update.message.text.strip()) == 10):
        await perform_phone_lookup(update, context)
        context.user_data.clear()
        return

    # --- DEFAULT ---
    await update.message.reply_text("🤔 Please select an option from /start or send a 10-digit number.")


# --- 🔍 PHONE LOOKUP FUNCTION ---
async def perform_phone_lookup(update: Update, context: CallbackContext) -> None:
    user = update.effective_user
    user_id_str = str(user.id)
    phone_number = update.message.text.strip()

    if not (phone_number.isdigit() and len(phone_number) == 10):
        await update.message.reply_text("❌ Invalid number. Send a valid 10-digit mobile number.")
        return

    sent = await update.message.reply_text(f"🔎 Searching `{phone_number}`...", parse_mode='Markdown')

    try:
        response = requests.get(PHONE_API_ENDPOINT.format(num=phone_number), timeout=15)
        data = response.json()
        results = data.get("data", data.get("results", [data])) if isinstance(data, dict) else data

        if not results:
            await sent.edit_text(f"🤷 No data found for `{phone_number}`.")
            return

        user_data = load_user_data()
        if user.id not in ADMIN_IDS:
            user_data[user_id_str]["credits"] -= SEARCH_COST
            save_user_data(user_data)

        result_text = f"📱 **Search Results for `{phone_number}`**\n\n"
        for i, info in enumerate(results, 1):
            result_text += (
                f"— **Record {i}** —\n"
                f"👤 Name: {info.get('name','N/A')}\n"
                f"📞 Mobile: {info.get('mobile','N/A')}\n"
                f"🏠 Address: {info.get('address','N/A')}\n"
                f"🌍 Circle: {info.get('circle','N/A')}\n\n"
            )

        credits_left = user_data[user_id_str]['credits'] if user.id not in ADMIN_IDS else 'Unlimited'
        result_text += f"💳 Credits Left: **{credits_left}**"
        await sent.edit_text(result_text, parse_mode='Markdown')

    except Exception as e:
        await sent.edit_text("⚠️ Error occurred while searching.")
        logger.error(f"Phone Lookup Error: {e}")


# --- 🚀 RUN BOT ---
def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("🚀 Bot is running with Full Admin Credit Management (Add, Deduct, Check)...")
    application.run_polling()


if __name__ == '__main__':
    main()