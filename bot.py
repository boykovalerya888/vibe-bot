import logging
import sqlite3
import openai
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
import os
from dotenv import load_dotenv
import random
import string

load_dotenv()

# Токены и ключи
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

openai.api_key = OPENAI_API_KEY

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# База данных
def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  referrer_id INTEGER,
                  answers_count INTEGER DEFAULT 0,
                  analysis_sent INTEGER DEFAULT 0)''')
    c.execute('''CREATE TABLE IF NOT EXISTS answers
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  user_id INTEGER,
                  friend_id INTEGER,
                  answer1 TEXT,
                  answer2 TEXT,
                  answer3 TEXT,
                  answer4 TEXT,
                  answer5 TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_answers
                 (user_id INTEGER PRIMARY KEY,
                  answer1 TEXT,
                  answer2 TEXT,
                  answer3 TEXT,
                  answer4 TEXT,
                  answer5 TEXT,
                  answered_friends TEXT DEFAULT '[]')''')
    conn.commit()
    conn.close()

init_db()

# Функция генерации реферального кода
def generate_referral_code(user_id):
    return f"ref_{user_id}"

# Вопросы (5 штук)
QUESTIONS = [
    "1️⃣ Первое слово. Когда ты думаешь об этом человеке, какое **одно слово** приходит в голову первым?",
    "2️⃣ Стихия. Если представить его энергию в виде явления природы — что это? (Лесной пожар, тихий омут, горная река, утренний туман...)",
    "3️⃣ Качество. Какое его качество (сильное или уязвимое) замечаешь **только ты**, а другим оно не видно?",
    "4️⃣ Цвет. Если бы у этого человека был цвет, который лучше всего описывает его суть — какой это цвет?",
    "5️⃣ Проявление. В какой момент или в каком деле этот человек становится **самим собой**?"
]

# Архетипы (для промпта)
ARCHETYPES = """
Опора: надежный, стабильный, заботливый, но забывает себя
Искра: вдохновляющий, творческий, легкий, но разбрасывается
Глубина: мыслитель, интуитивный, чувствительный, но закрытый
Движение: активный, целеустремленный, лидер, но жесткий
Чуткость: эмпатичный, понимающий, дипломат, но без границ
Простота: искренний, прямой, живой, но уязвимый
Мастер: умелый, профессиональный, эксперт, но перфекционист
Перемены: гибкий, свободный, непредсказуемый, но нестабильный
Тишина: спокойный, уравновешенный, наблюдатель, но пассивный
Свет: теплый, принимающий, добрый, но размытый
"""

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Проверяем, есть ли реферальный код
    args = context.args
    referrer_id = None
    if args and args[0].startswith('ref_'):
        try:
            referrer_id = int(args[0].replace('ref_', ''))
        except:
            pass
    
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO users (user_id, referrer_id, answers_count) VALUES (?, ?, ?)", 
              (user_id, referrer_id, 0))
    conn.commit()
    conn.close()
    
    if referrer_id:
        # Это друг, перешедший по ссылке
        context.user_data['referrer_id'] = referrer_id
        context.user_data['question_index'] = 0
        context.user_data['answers'] = []
        
        await update.message.reply_text(
            "🌟 Твой друг изучает себя и ему важно твое мнение.\n"
            "Ответь на 5 коротких вопросов — это займет всего 2 минуты.\n\n"
            f"{QUESTIONS[0]}"
        )
    else:
        # Новый пользователь
        ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start={generate_referral_code(user_id)}"
        
        await update.message.reply_text(
            "🌀 **Клуб практик «ЯЗНАЮ»**\n\n"
            "Ты когда-нибудь задумывался, как тебя видят другие?\n"
            "Не просто со стороны, а в энергии, в проявлениях, в тех качествах, "
            "которые заметны только близким?\n\n"
            "**Как это работает:**\n"
            "1️⃣ Ты отправляешь эту ссылку 10 своим знакомым\n"
            "2️⃣ Они отвечают на 5 вопросов о тебе\n"
            "3️⃣ Мы анализируем ответы через древнее знание и ИИ\n"
            "4️⃣ Ты получаешь свой глубинный портрет\n\n"
            f"🔗 **Твоя ссылка:**\n`{ref_link}`\n\n"
            "Отправь её 10 друзьям. Когда наберется 5 ответов — получишь первый набросок.\n"
            "А при 10 ответах — полный портрет с архетипом и приглашением в клуб."
        )

# Обработка ответов друга
async def handle_friend_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text
    
    if 'question_index' not in context.user_data:
        return
    
    # Сохраняем ответ
    context.user_data['answers'].append(text)
    context.user_data['question_index'] += 1
    
    # Если ответили на все 5 вопросов
    if context.user_data['question_index'] >= 5:
        referrer_id = context.user_data.get('referrer_id')
        answers = context.user_data['answers']
        
        # Сохраняем ответы в базу
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute('''INSERT INTO answers 
                     (user_id, friend_id, answer1, answer2, answer3, answer4, answer5) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (referrer_id, user_id, answers[0], answers[1], answers[2], answers[3], answers[4]))
        
        # Обновляем счетчик ответов для пользователя
        c.execute("UPDATE users SET answers_count = answers_count + 1 WHERE user_id = ?", (referrer_id,))
        
        # Получаем текущее количество ответов
        c.execute("SELECT answers_count FROM users WHERE user_id = ?", (referrer_id,))
        count = c.fetchone()[0]
        conn.commit()
        
        # Если набралось 3, 5 или 10 ответов - запускаем анализ
        if count in [3, 5, 10]:
            await run_analysis(referrer_id, count, context)
        
        conn.close()
        
        # Вирусное сообщение для друга
        friend_ref_link = f"https://t.me/{(await context.bot.get_me()).username}?start={generate_referral_code(user_id)}"
        await update.message.reply_text(
            "✨ Спасибо! Твой ответ очень важен.\n\n"
            "**Хочешь узнать, как тебя видят другие?**\n"
            "Отправь эту ссылку 10 своим знакомым — получи свой портрет:\n\n"
            f"`{friend_ref_link}`"
        )
        
        # Очищаем данные
        del context.user_data['question_index']
        del context.user_data['answers']
        del context.user_data['referrer_id']
    else:
        # Задаем следующий вопрос
        await update.message.reply_text(QUESTIONS[context.user_data['question_index']])

# Функция анализа через OpenAI
async def run_analysis(user_id: int, count: int, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    
    # Получаем все ответы друзей для этого пользователя
    c.execute('''SELECT answer1, answer2, answer3, answer4, answer5 
                 FROM answers WHERE user_id = ?''', (user_id,))
    all_answers = c.fetchall()
    
    # Формируем промпт
    answers_text = ""
    for i, ans in enumerate(all_answers, 1):
        answers_text += f"\nДруг {i}:\n1. {ans[0]}\n2. {ans[1]}\n3. {ans[2]}\n4. {ans[3]}\n5. {ans[4]}\n"
    
    prompt = f"""
Ты — мудрый проводник, глубокий психолог. Проанализируй {count} ответов друзей о человеке.

Ответы друзей:
{answers_text}

Напиши портрет этого человека:
1. Как его видят другие (плюсы, сильные стороны, энергия)
2. Что скрыто от него самого (тень, слепое пятно, минусы)
3. Какой архетип ему ближе всего (из списка ниже) — выбери один или создай свой

Архетипы:
{ARCHETYPES}

В конце добавь мягкое приглашение в клуб практик "ЯЗНАЮ", связанное с его тенью.
Говори тепло, образно, про энергию и проявление. Длина: 5-7 предложений.
"""
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "Ты — мудрый проводник, говоришь глубоко и бережно."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=500
        )
        analysis = response.choices[0].message.content
        
        # Отправляем результат пользователю
        await context.bot.send_message(
            chat_id=user_id,
            text=f"✨ **Твой портрет готов** ✨\n\n{analysis}"
        )
        
        # Отмечаем, что анализ отправлен
        c.execute("UPDATE users SET analysis_sent = 1 WHERE user_id = ?", (user_id,))
        conn.commit()
        
    except Exception as e:
        logger.error(f"Ошибка OpenAI: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="⚠️ Что-то пошло не так. Мы уже чиним!"
        )
    
    conn.close()

# Команда /status (проверить, сколько ответов)
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute("SELECT answers_count FROM users WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    
    if result:
        count = result[0]
        await update.message.reply_text(f"📊 Собрано ответов: {count}/10")
    else:
        await update.message.reply_text("Начни с /start")

# Запуск бота
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_friend_answer))
    
    print("🤖 Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
