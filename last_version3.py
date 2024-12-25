import requests
from vk_api import VkApi
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackContext, CallbackQueryHandler
from deep_translator import GoogleTranslator
from tabulate import tabulate
from collections import Counter
import html
import re

TELEGRAM_TOKEN = '7915283986:AAFIocGTVRJrVPMp0_ON1eJTH067AFODCyA'
VK_API_VERSION = '5.131'
VK_CREDENTIALS = [{'app_id': '52828225', 'app_secret': 'a289ZA6AzwBNOZlkE0oU'}]
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


def fetch_vk_friends(vk_id, language, user_last_name):
    try:
        # Получаем список друзей пользователя
        friends = vk.friends.get(user_id=vk_id, fields="city,last_name,screen_name,occupation")

        # Проверка на доступность профиля
        if 'items' not in friends:
            raise Exception("Profile is private")

        city_counter = Counter()  # Счетчик для городов друзей
        occupation_counter = Counter()  # Счетчик для профессий друзей
        relatives_info = []  # Список для родственников с их ссылками

        # Функция для проверки совпадения фамилии с учетом женской формы
        def check_last_name_match(friend_last_name, user_last_name):
            # Если фамилия друга совпадает с фамилией пользователя или женская форма фамилии
            return friend_last_name == user_last_name or friend_last_name == user_last_name + 'a'

        # Итерируем по друзьям
        for friend in friends['items']:
            city_title = friend.get('city', {}).get('title')  # Город друга
            friend_last_name = friend.get('last_name')  # Фамилия друга
            friend_screen_name = friend.get('screen_name')  # Короткое имя друга
            occupation = friend.get('occupation', {}).get('name')  # Работа друга

            # Добавляем город друга в счетчик
            if city_title:
                city_counter[city_title] += 1

            # Добавляем профессию друга в счетчик
            if occupation:
                occupation_counter[occupation] += 1

            # Проверяем, если фамилия друга совпадает с фамилией пользователя (учитывая женскую форму)
            if check_last_name_match(friend_last_name, user_last_name):
                # Формируем строку с именем, фамилией и ссылкой на профиль
                profile_url = f"https://vk.com/{friend_screen_name}" if friend_screen_name else "Ссылка не найдена"
                relative_info = f"{friend.get('first_name')} {friend_last_name} ({profile_url})"
                relatives_info.append(relative_info)

        # Сортировка городов друзей по количеству встреч
        sorted_cities = sorted(city_counter.items(), key=lambda x: x[1], reverse=True)
        filtered_cities = {city: count for city, count in sorted_cities if count >= 5}

        # Сортировка университетов друзей по количеству встреч
        sorted_occupations = sorted(occupation_counter.items(), key=lambda x: x[1], reverse=True)
        filtered_occupations = {occupation: count for occupation, count in sorted_occupations if count >= 7}

        # Формирование ответа по городам друзей
        cities_response = ""
        if filtered_cities:
            cities_response = "\n".join(
                [f"{translate_text(city, language)}: {count}" for city, count in filtered_cities.items()]
            )
        else:
            cities_response = translate_text("Profile is private.", language)

        # Формирование ответа по профессиям друзей
        occupations_response = ""
        if filtered_occupations:
            occupations_header = "💼 Анализ университетов друзей:" if language == 'ru' else "💼 University friends analysis:"
            occupations_response = f"\n{occupations_header}\n" + "\n".join(
                [f"{translate_text(occupation, language)}: {count}" for occupation, count in filtered_occupations.items()]
            )

        # Формирование ответа по родственникам
        relatives_response = ""
        if relatives_info:
            relatives_header = "👨‍👩‍👧‍👦 Анализ родственников:" if language == 'ru' else "👨‍👩‍👧‍👦 Relatives analysis:"
            relatives_response = f"\n{relatives_header}\n" + "\n".join(relatives_info)

        # Объединение данных и возврат без повторений
        if cities_response.strip() and relatives_response.strip() and occupations_response.strip():
            return f"{cities_response}\n{occupations_response}\n{relatives_response}"

        # Возвращаем только один из блоков, если второй или третий пустой
        return cities_response if cities_response.strip() else (occupations_response if occupations_response.strip() else relatives_response)

    except Exception as e:
        print(f"Ошибка при получении друзей: {e}")
        return translate_text("Profile is private.", language)





# Получение списка подписок
def fetch_vk_subscriptions(vk_id, language):
    try:
        # Получение подписок пользователя
        subscriptions = vk.users.getSubscriptions(user_id=vk_id, extended=1)

        # Фильтруем только личные профили (тип profile)
        user_subscriptions = [
            sub for sub in subscriptions.get('items', [])
            if sub.get('type') == 'profile'  # Проверяем, что это профиль пользователя
        ]

        # Если нет подходящих подписок
        if not user_subscriptions:
            return translate_text("Нет подписок на пользователей.", language)

        # Формируем список ссылок
        return "\n".join([
            f"{sub['first_name']} {sub['last_name']} (https://vk.com/{sub['screen_name']})"
            for sub in user_subscriptions
        ])
    except Exception as e:
        print(f"Ошибка при получении подписок: {e}")
        return translate_text("Не удалось получить данные о подписках.", language)


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


SOCIAL_NETWORK_PATTERNS = {
    'Instagram': r'(https?://(www\.)?instagram\.com/[^\s]+)',
    'Telegram': r'(https?://(www\.)?t\.me/[^\s]+|https?://(www\.)?telegram\.me/[^\s]+)',
    'Одноклассники': r'(https?://(www\.)?ok\.ru/[^\s]+)',
    'Facebook': r'(https?://(www\.)?facebook\.com/[^\s]+)',
    'Twitter': r'(https?://(www\.)?twitter\.com/[^\s]+)',
    'YouTube': r'(https?://(www\.)?youtube\.com/[^\s]+|https?://youtu\.be/[^\s]+)',
    'VK': r'(https?://(www\.)?vk\.com/[^\s]+)'  # Добавлено регулярное выражение для ВКонтакте
}

def find_social_links(text):
    links = {}
    for network, pattern in SOCIAL_NETWORK_PATTERNS.items():
        matches = re.findall(pattern, text)
        if matches:
            # Берём первую часть совпадения — это сама ссылка
            links[network] = [match[0] for match in matches]
    return links



def fetch_social_links_from_profile(user_info, language):
    links = {}
    # Поля, где могут быть ссылки
    fields_to_check = ['about', 'status']

    for field in fields_to_check:
        if field in user_info and user_info[field]:
            field_links = find_social_links(user_info[field])
            for network, urls in field_links.items():
                links.setdefault(network, []).extend(urls)
    return links


# Функция для поиска ссылок в постах пользователя
def fetch_social_links_from_posts(vk_id):
    try:
        # Получаем посты пользователя
        wall_posts = vk.wall.get(owner_id=vk_id, count=100)  # Максимум 100 постов
        links = {}

        for post in wall_posts.get('items', []):
            text = post.get('text', '')
            if text:
                # Ищем ссылки в тексте поста
                post_links = find_social_links(text)
                for network, urls in post_links.items():
                    links.setdefault(network, []).extend(urls)

        # Удаляем дубликаты
        for network in links:
            links[network] = list(set(links[network]))

        return links
    except Exception as e:
        print(f"Ошибка при получении постов: {e}")
        return {}


async def handle_link(update: Update, context: CallbackContext):
    vk_id_input = update.message.text.strip().split('/')[-1]
    vk_id = get_vk_user_id(vk_id_input)
    if not vk_id:
        await update.message.reply_text("Ошибка: Не удалось определить ID пользователя.")
        return

    language = context.user_data.get('language', 'ru')
    target_lang = 'ru' if language == 'ru' else 'en'

    # Получение информации о пользователе
    user_info = fetch_vk_info(vk_id)
    user_last_name = user_info.get("last_name", "") if user_info else ""

    # Анализ друзей и родственников
    friends_info = fetch_vk_friends(vk_id, target_lang, user_last_name)

    # Поиск ссылок на соцсети в постах
    post_links = fetch_social_links_from_posts(vk_id)

    # Форматируем ссылки для вывода в анализ постов
    if post_links:
        links_header = "Анализ постов:" if target_lang == 'ru' else "Post analysis:"
        links_content = ""
        for network, urls in post_links.items():
            links_content += f"{network}: {', '.join(urls)}\n"
        post_analysis = f"\n\n{links_header}\n{links_content}"
    else:
        post_analysis = "\n\nАнализ постов:\nСсылки на социальные сети не найдены." if target_lang == 'ru' else "\n\nPost analysis:\nNo social network links found."

    # Формирование ответа с основными данными
    response = ""
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
            "Школы": "schools", "Университет": "occupation", "Интересы": "interests",
            "Фильмы": "movies", "Телевидение": "tv", "Книги": "books", "Игры": "games", "О себе": "about",
            "Родственники": "relatives"
        }
        icons = {
            "Пол": "🚻", "Девичья фамилия": "💍", "Короткое имя": "🔖", "Семейное положение": "💑",
            "Партнер": "💞", "Дата рождения": "🎂", "Родной город": "🏠", "Страна": "🌍", "Город": "🏙️",
            "Статус": "📜", "Телефон": "📞", "Верифицирован": "✅", "Онлайн": "💻", "Университеты": "🎓",
            "Школы": "🏫", "Университет": "💼", "Интересы": "💡", "Фильмы": "🎬", "Телевидение": "📺",
            "Книги": "📚", "Игры": "🎮", "О себе": "💬", "Родственники": "👨‍👩‍👧‍👦"
        }

        for label, field in fields.items():
            value = user_info.get(field)
            icon = icons.get(label, "")
            if field == "bdate":
                continue
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
            if value and isinstance(value, str) and value.lower() not in ["none", "no information", "нет информации",
                                                                          "информация отсутствует"]:
                data.append([f"{icon} {label if target_lang == 'ru' else fields.get(label)}", value])

        response = format_data_with_fixed_value_alignment(data)

        # Добавляем анализ друзей
        if friends_info and friends_info.lower() not in ["none", "no information", "нет информации",
                                                         "profile is private"]:
            friends_header = "🌍 Анализ городов друзей:" if target_lang == 'ru' else "🌍 Friends cities analysis:"
            response += f"\n\n{friends_header}\n{friends_info}"

        # Добавляем анализ постов в конец
        response += post_analysis

        # Ограничиваем длину основного ответа (если с фото)
        if len(response) > 900:  # Немного меньше 1024, чтобы оставить место для форматирования
            response = response[:900] + "...\n(Данные обрезаны)"

        # Отправляем фото с основной информацией
        escaped_response = html.escape(response)
        if photo_url:
            await update.message.reply_photo(photo=photo_url, caption=f"<pre>{escaped_response}</pre>", parse_mode="HTML")
        else:
            await update.message.reply_text(response)




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
