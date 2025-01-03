import requests
from vk_api import VkApi
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from deep_translator import GoogleTranslator
from tabulate import tabulate
from collections import Counter
import html

TELEGRAM_TOKEN = '7915283986:AAFIocGTVRJrVPMp0_ON1eJTH067AFODCyA'
VK_API_VERSION = '5.131'
VK_CREDENTIALS = [{'app_id': '52785329', 'app_secret': 'xTJVQx15fdHUrteyrbkS'}]
current_credential_index = 0

# Получение сервисного токена VK
def get_service_token():
    global current_credential_index
    credentials = VK_CREDENTIALS[current_credential_index]
    app_id = credentials['app_id']
    app_secret = credentials['app_secret']
    url = (
        f"https://oauth.vk.com/access_token?client_id={app_id}"
        f"&client_secret={app_secret}&v={VK_API_VERSION}&grant_type=client_credentials"
    )
    response = requests.get(url)
    data = response.json()
    if 'access_token' in data:
        return data['access_token']
    else:
        current_credential_index = (current_credential_index + 1) % len(VK_CREDENTIALS)
        credentials = VK_CREDENTIALS[current_credential_index]
        app_id = credentials['app_id']
        app_secret = credentials['app_secret']
        url = (
            f"https://oauth.vk.com/access_token?client_id={app_id}"
            f"&client_secret={app_secret}&v={VK_API_VERSION}&grant_type=client_credentials"
        )
        response = requests.get(url)
        data = response.json()
        if 'access_token' in data:
            return data['access_token']
        else:
            raise Exception("Ошибка получения сервисного токена VK: авторизация не удалась для обоих наборов.")

VK_SERVICE_TOKEN = get_service_token()
vk_session = VkApi(token=VK_SERVICE_TOKEN)
vk = vk_session.get_api()

# Переключение токена при возникновении ошибки
def refresh_vk_session():
    global VK_SERVICE_TOKEN, vk_session, vk
    VK_SERVICE_TOKEN = get_service_token()
    vk_session = VkApi(token=VK_SERVICE_TOKEN)
    vk = vk_session.get_api()


# Перевод текста
def translate_text(text, target_language, source_language='auto'):
    try:
        translated_text = GoogleTranslator(source=source_language, target=target_language).translate(text)
        return translated_text
    except Exception as e:
        print(f"Ошибка перевода: {e}")
        return text


# Форматирование текста с ограничением длины строки
def wrap_text(text, max_length=40):
    words = text.split()
    lines = []
    line = ""
    for word in words:
        if len(line) + len(word) + 1 > max_length:
            lines.append(line)
            line = word
        else:
            line += (" " + word if line else word)
    lines.append(line)
    return "\n".join(lines)


# Форматирование даты рождения
def format_bdate(bdate, target_language):
    month_names = {'01': 'января', '02': 'февраля', '03': 'марта', '04': 'апреля', '05': 'мая', '06': 'июня',
                   '07': 'июля', '08': 'августа', '09': 'сентября', '10': 'октября', '11': 'ноября', '12': 'декабря'}
    month_names_en = {'01': 'January', '02': 'February', '03': 'March', '04': 'April', '05': 'May', '06': 'June',
                      '07': 'July', '08': 'August', '09': 'September', '10': 'October', '11': 'November',
                      '12': 'December'}
    month_dict = month_names if target_language == 'ru' else month_names_en
    parts = bdate.split('.')
    if len(parts) == 3:
        day, month, year = parts
        return f"{int(day)} {month_dict.get(month.zfill(2), '')} {year}"
    elif len(parts) == 2:
        day, month = parts
        return f"{int(day)} {month_dict.get(month.zfill(2), '')}"
    return bdate


# Получение имени и фамилии родственников
def get_relative_names(relatives, language):
    if not relatives:
        return None
    relative_names = []
    for relative in relatives:
        relative_id = relative.get("id")
        try:
            user_info = vk.users.get(user_ids=relative_id)
            if user_info:
                name = f"{user_info[0]['first_name']} {user_info[0]['last_name']}"
                relation = translate_text(relative.get('type', ''), language)
                relative_names.append(f"{relation}: {name}")
        except Exception as e:
            print(f"Ошибка при получении данных о родственнике: {e}")
    return ', '.join(relative_names) if relative_names else None



# Форматирование значений, включая словари и списки
def format_value(value, language):
    if isinstance(value, dict):
        if "title" in value:
            return value["title"]
        return ', '.join(f"{translate_text(k, language)}: {v}" for k, v in value.items() if isinstance(v, (str, int)))
    elif isinstance(value, list):
        return ', '.join(format_value(item, language) for item in value if isinstance(item, (dict, str, int)))
    return translate_text(str(value), language)


# Получение числового ID пользователя
def get_vk_user_id(vk_id):
    try:
        if vk_id.isdigit():
            return int(vk_id)
        response = vk.users.get(user_ids=vk_id)
        return response[0]['id'] if response else None
    except Exception as e:
        if 'authorization failed' in str(e).lower() or 'service token' in str(e).lower():
            print(f"Ошибка при получении ID пользователя: {e}. Попытка сменить сервисный токен.")
            refresh_vk_session()  # Смена токена
            try:
                if vk_id.isdigit():
                    return int(vk_id)
                response = vk.users.get(user_ids=vk_id)
                return response[0]['id'] if response else None
            except Exception as e:
                print(f"Ошибка при повторной попытке получения ID пользователя: {e}")
                return None
        else:
            print(f"Ошибка при получении ID пользователя: {e}")
            return None


# Получение информации о пользователе ВКонтакте
def fetch_vk_info(vk_id):
    try:
        response = vk.users.get(
            user_ids=vk_id,
            fields="first_name, last_name, maiden_name, screen_name, sex, relation, relation_partner, bdate, "
                   "bdate_visibility, home_town, country, city, status, phone, verified, online, universities, "
                   "schools, occupation, personal, interests, movies, tv, books, games, about, quotes, relatives, "
                   "photo_max",
            v=VK_API_VERSION
        )
        return response[0] if response else None
    except Exception as e:
        print(f"Ошибка при запросе к API ВКонтакте: {e}")
        return None



# Получение списка друзей и их городов
def fetch_vk_friends(vk_id, language):
    try:
        friends = vk.friends.get(user_id=vk_id, fields="city")
        if 'items' not in friends:
            raise Exception("Profile is private")
        city_counter = Counter()
        for friend in friends['items']:
            city_title = friend.get('city', {}).get('title')
            if city_title:
                city_counter[city_title] += 1
        sorted_cities = sorted(city_counter.items(), key=lambda x: x[1], reverse=True)
        filtered_cities = {city: count for city, count in sorted_cities if count >= 5}
        if filtered_cities:
            response = "\n".join(
                [f"{translate_text(city, language)}: {count}" for city, count in filtered_cities.items()])
        else:
            response = translate_text("Profile is private.", language)
        return response
    except Exception as e:
        print(f"Ошибка при получении друзей: {e}")
        return translate_text("Profile is private.", language)


# Получение списка подписок
def fetch_vk_subscriptions(vk_id, language):
    try:
        subscriptions = vk.users.getSubscriptions(user_id=vk_id, extended=1)
        if subscriptions['count'] == 0:
            return translate_text("Profile is private.", language)
        return "\n".join([f"{s['name']} (https://vk.com/{s['screen_name']})" for s in subscriptions['items']])
    except Exception as e:
        print(f"Ошибка при получении подписок: {e}")
        return translate_text("Profile is private.", language)


# Установка языка
async def set_language(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    context.user_data['language'] = 'ru' if query.data == 'lang_ru' else 'en'
    msg = "Язык установлен на русский.\nВведите ссылку на страницу ВК, либо id пользователя." if query.data == 'lang_ru' else "Language set to English.\nEnter the link to the VK page or the user ID."
    await query.edit_message_text(msg)


# Форматирование данных с фиксированным отступом для значений
def format_data_with_fixed_value_alignment(data):
    formatted_data = []
    for label, value in data:
        formatted_label = f"{label}:"
        formatted_data.append(f"{formatted_label} {value}")
    return "\n".join(formatted_data)


# Обработка ссылки с фиксированным выравниванием значений
async def handle_link(update: Update, context: CallbackContext):
    vk_id_input = update.message.text.strip().split('/')[-1]
    vk_id = get_vk_user_id(vk_id_input)
    if not vk_id:
        await update.message.reply_text("Ошибка: Не удалось определить ID пользователя.")
        return
    language = context.user_data.get('language', 'ru')
    target_lang = 'ru' if language == 'ru' else 'en'
    user_info = fetch_vk_info(vk_id)
    friends_info = fetch_vk_friends(vk_id, target_lang)
    subscriptions_info = fetch_vk_subscriptions(vk_id, target_lang)
    if user_info:
        data = []
        photo_url = user_info.get("photo_max")
        full_name = translate_text(f"{user_info.get('first_name', '')} {user_info.get('last_name', '')}", target_lang)
        if full_name.strip():
            data.append([f"👤 Имя" if target_lang == 'ru' else "👤 Name", full_name])
        fields = {
            "Пол": "sex", "Девичья фамилия": "maiden_name", "Короткое имя": "screen_name",
            "Семейное положение": "relation", "Партнер": "relation_partner", "Дата рождения": "bdate",
            "Родной город": "home_town", "Страна": "country", "Город": "city", "Статус": "status",
            "Телефон": "phone", "Верифицирован": "verified", "Онлайн": "online", "Университеты": "universities",
            "Школы": "schools", "Работа": "occupation", "Интересы": "interests",
            "Фильмы": "movies", "Телевидение": "tv", "Книги": "books", "Игры": "games", "О себе": "about",
            "Родственники": "relatives"
        }
        icons = {
            "Пол": "🚻", "Девичья фамилия": "💍", "Короткое имя": "🔖", "Семейное положение": "💑",
            "Партнер": "💞", "Дата рождения": "🎂", "Родной город": "🏠", "Страна": "🌍", "Город": "🏙️",
            "Статус": "📜", "Телефон": "📞", "Верифицирован": "✅", "Онлайн": "💻", "Университеты": "🎓",
            "Школы": "🏫", "Работа": "💼", "Интересы": "💡", "Фильмы": "🎬", "Телевидение": "📺",
            "Книги": "📚", "Игры": "🎮", "О себе": "💬", "Родственники": "👨‍👩‍👧‍👦"
        }
        field_translations = {
            "Пол": "Sex",
            "Девичья фамилия": "Maiden name",
            "Короткое имя": "Short name",
            "Семейное положение": "Relationship",
            "Партнер": "Partner",
            "Дата рождения": "Date of birth",
            "Родной город": "Hometown",
            "Страна": "Country",
            "Город": "City",
            "Статус": "Status",
            "Телефон": "Phone",
            "Верифицирован": "Verified",
            "Онлайн": "Online",
            "Университеты": "Universities",
            "Школы": "Schools",
            "Работа": "Work",
            "Интересы": "Interests",
            "Фильмы": "Movies",
            "Телевидение": "TV",
            "Книги": "Books",
            "Игры": "Games",
            "О себе": "About",
            "Родственники": "Relatives"
        }
        for label, field in fields.items():
            value = user_info.get(field)
            icon = icons.get(label, "")
            if field == "bdate":
                value = format_bdate(value, target_lang) if value else None
            elif field == "sex":
                value = "Мужской" if value == 2 else "Женский" if value == 1 else None
                if target_lang == 'en':
                    value = "Male" if value == "Мужской" else "Female" if value == "Женский" else None
            elif field == "verified":
                value = "Да" if value else "Нет"
                if target_lang == 'en':
                    value = "Yes" if value == "Да" else "No"
            elif field == "online":
                value = "Да" if value else "Нет"
                if target_lang == 'en':
                    value = "Yes" if value == "Да" else "No"
            elif field == "city":
                if user_info.get('city'):
                    value = user_info['city'].get("title")
                    value = translate_text(value, target_lang) if value else None
            elif field == "occupation":
                if user_info.get('occupation'):
                    value = user_info['occupation'].get("name")
                    if target_lang == 'en' and value:
                        value = translate_text(value, 'en')
            elif field == "universities":
                value = format_universities(value, target_lang)
            elif field == "schools":
                value = format_schools(value, target_lang)
            elif field == "relatives":
                value = get_relative_names(value, target_lang)
            elif field == "status":
                value = wrap_text(value)
            if value and isinstance(value, str) and value.lower() not in ["none", "no information", "нет информации", "информация отсутствует"]:
                data.append([f"{icon} {label if target_lang == 'ru' else field_translations.get(label)}", value])
        personal_info = user_info.get("personal")
        if personal_info:
            personal_formatted = format_personal_info(personal_info, target_lang)
            if personal_formatted and isinstance(personal_formatted, str) and personal_formatted.lower() not in ["none", "no information", "нет информации", "информация отсутствует"]:
                data.append([f"🤫 Личное" if target_lang == 'ru' else "🤫 Personal", personal_formatted])
        response = format_data_with_fixed_value_alignment(data)
        if friends_info and friends_info.lower() not in ["none", "no information", "нет информации", "profile is private"]:
            friends_header = "🌍 Анализ городов друзей:" if target_lang == 'ru' else "🌍 Friends cities analysis:"
            response += f"\n\n{friends_header}\n{friends_info}"
        escaped_response = html.escape(response)
        if photo_url:
            await update.message.reply_photo(photo=photo_url, caption=f"<pre>{escaped_response}</pre>", parse_mode="HTML")

    else:
        response = translate_text("Информация о пользователе не найдена.", target_lang)
        await update.message.reply_text(f"<pre>{html.escape(response)}</pre>", parse_mode="HTML")




def format_universities(universities, language):
    if not universities or not isinstance(universities, list):
        return None
    formatted_universities = []
    for uni in universities:
        name = uni.get("name")
        faculty = uni.get("faculty_name")
        graduation = uni.get("graduation")
        parts = []
        if name:
            parts.append(name)
        if faculty:
            parts.append(f"Faculty: {faculty}" if language == 'en' else f"Факультет: {faculty}")
        if graduation:
            parts.append(f"Graduated in {graduation}" if language == 'en' else f"Выпуск {graduation}")
        if parts:
            formatted_universities.append(", ".join(parts))
    return "\n".join(formatted_universities) if formatted_universities else None



def format_schools(schools, language):
    if not schools or all(not school.get("name") for school in schools):
        return None

    school_info = []
    for school in schools:
        name = school.get("name")
        year_from = school.get("year_from")
        year_to = school.get("year_to")
        if name:
            entry = f"{name}"
            if year_from and year_to:
                entry += f" ({year_from}–{year_to})"
            school_info.append(entry)
    return ", ".join(school_info) if school_info else None


# Маппинг значений для личных данных
personal_mappings = {
    "political": {
        1: "коммунистические", 2: "социалистические", 3: "умеренные", 4: "либеральные",
        5: "консервативные", 6: "монархические", 7: "ультраконсервативные", 8: "индифферентные", 9: "либертарианские"
    },
    "people_main": {
        1: "ум и креативность", 2: "доброта и честность", 3: "красота и здоровье",
        4: "власть и богатство", 5: "смелость и упорство", 6: "юмор и жизнелюбие"
    },
    "life_main": {
        1: "семья и дети", 2: "карьера и деньги", 3: "развлечения и отдых", 4: "наука и исследования",
        5: "совершенствование мира", 6: "саморазвитие", 7: "красота и искусство", 8: "слава и влияние"
    },
    "smoking": {
        1: "резко негативное", 2: "негативное", 3: "компромиссное", 4: "нейтральное", 5: "положительное"
    },
    "alcohol": {
        1: "резко негативное", 2: "негативное", 3: "компромиссное", 4: "нейтральное", 5: "положительное"
    }
}


# Форматирование личной информации (personal)
def format_personal_info(personal_info, language):
    personal_fields = {
        "alcohol": "🍷 Алкоголь" if language == 'ru' else "🍷 Alcohol",
        "inspired_by": "✨ Вдохновлен(а)" if language == 'ru' else "✨ Inspired by",
        "langs": "🌐 Языки" if language == 'ru' else "🌐 Languages",
        "life_main": "💼 Главное в жизни" if language == 'ru' else "💼 Life main",
        "people_main": "👥 Главное в людях" if language == 'ru' else "👥 People main",
        "smoking": "🚬 Курение" if language == 'ru' else "🚬 Smoking"
    }

    # Значения личных полей, которые должны выводиться вместо числовых значений
    translation_values = {
        "political": {
            1: "коммунистические" if language == 'ru' else "communist",
            2: "социалистические" if language == 'ru' else "socialist",
            3: "умеренные" if language == 'ru' else "moderate",
            4: "либеральные" if language == 'ru' else "liberal",
            5: "консервативные" if language == 'ru' else "conservative",
            6: "монархические" if language == 'ru' else "monarchist",
            7: "ультраконсервативные" if language == 'ru' else "ultra-conservative",
            8: "индифферентные" if language == 'ru' else "indifferent",
            9: "либертарианские" if language == 'ru' else "libertarian"
        },
        "people_main": {
            1: "ум и креативность" if language == 'ru' else "mind and creativity",
            2: "доброта и честность" if language == 'ru' else "kindness and honesty",
            3: "красота и здоровье" if language == 'ru' else "beauty and health",
            4: "власть и богатство" if language == 'ru' else "power and wealth",
            5: "смелость и упорство" if language == 'ru' else "courage and persistence",
            6: "юмор и жизнелюбие" if language == 'ru' else "humor and love of life"
        },
        "life_main": {
            1: "семья и дети" if language == 'ru' else "family and children",
            2: "карьера и деньги" if language == 'ru' else "career and money",
            3: "развлечения и отдых" if language == 'ru' else "entertainment and leisure",
            4: "наука и исследования" if language == 'ru' else "science and research",
            5: "совершенствование мира" if language == 'ru' else "world improvement",
            6: "саморазвитие" if language == 'ru' else "self-development",
            7: "красота и искусство" if language == 'ru' else "beauty and art",
            8: "слава и влияние" if language == 'ru' else "fame and influence"
        },
        "smoking": {
            1: "резко негативное" if language == 'ru' else "strongly negative",
            2: "негативное" if language == 'ru' else "negative",
            3: "компромиссное" if language == 'ru' else "compromise",
            4: "нейтральное" if language == 'ru' else "neutral",
            5: "положительное" if language == 'ru' else "positive"
        },
        "alcohol": {
            1: "резко негативное" if language == 'ru' else "strongly negative",
            2: "негативное" if language == 'ru' else "negative",
            3: "компромиссное" if language == 'ru' else "compromise",
            4: "нейтральное" if language == 'ru' else "neutral",
            5: "положительное" if language == 'ru' else "positive"
        }
    }

    formatted_lines = []
    for key, label in personal_fields.items():
        value = personal_info.get(key)
        if value is not None:
            # Заменяем числовые значения на их текстовое представление, если это возможно
            if key in translation_values and isinstance(value, int):
                value = translation_values[key].get(value, value)

            formatted_lines.append(f"{label}: {value}")

    return "\n".join(formatted_lines)


# Команда /start
async def start(update: Update, context: CallbackContext):
    keyboard = [
        [InlineKeyboardButton("🇷🇺 Русский", callback_data='lang_ru')],
        [InlineKeyboardButton("🇬🇧 English", callback_data='lang_en')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Выберите язык / Choose a language:", reply_markup=reply_markup)

# Основная функция
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(set_language))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    application.run_polling()

if __name__ == '__main__':
    main()
