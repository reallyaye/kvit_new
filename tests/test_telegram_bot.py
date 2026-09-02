import os
import shutil
import tempfile
import time

import config
from database import get_db, migrate_db
from services.security.auth_service import hash_password
from services.telegram_bot import TelegramAPIError, TelegramBotService, TelegramClient


def _seed_test_bot_data():
    migrate_db()
    con = get_db()
    con.execute('DELETE FROM telegram_users;')
    con.execute('''
        INSERT OR REPLACE INTO accounts(account_number, customer_name, address, street, building)
        VALUES ('800146', 'Иванов Иван', 'г. Алматы, ул. Абая 10, кв. 5', 'Абая', '10')
    ''')
    con.execute('''
        INSERT OR REPLACE INTO accounts(account_number, customer_name, address, street, building)
        VALUES ('800147', 'Петров Петр', 'г. Алматы, ул. Достык 20, кв. 1', 'Достык', '20')
    ''')
    con.commit()
    con.close()

def test_telegram_client_init_and_validation():
    """Тестирование инициализации клиента."""
    client = TelegramClient('test_token')
    assert client.token == 'test_token'
    assert client.base_url == 'https://api.telegram.org/bottest_token'
    assert client.file_base_url == 'https://api.telegram.org/file/bottest_token'

    empty_client = TelegramClient('')
    err_raised = False
    try:
        empty_client.get_me()
    except TelegramAPIError:
        err_raised = True
    assert err_raised, "Ожидалось исключение TelegramAPIError при пустом токене"

def test_bot_authorization_flow():
    """Тестирование проверки прав и команды /login."""
    _seed_test_bot_data()
    config.ADMIN_PASSWORD_HASH = hash_password('admin_pass_321')

    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001, 1002}

    # 1. Проверка по белому списку ID
    assert bot.is_admin(1001) is True
    assert bot.is_admin(1002) is True
    assert bot.is_admin(9999) is False

    sent_messages = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))

    # 2. Неверный пароль
    bot.handle_update({
        'message': {
            'chat': {'id': 9999},
            'from': {'id': 9999},
            'text': '/login wrong_password'
        }
    })
    assert bot.is_admin(9999) is False
    assert any('Неверный пароль' in m[1] for m in sent_messages)

    # 3. Верный пароль
    bot.handle_update({
        'message': {
            'chat': {'id': 9999},
            'from': {'id': 9999},
            'text': '/login admin_pass_321'
        }
    })
    assert bot.is_admin(9999) is True
    assert any('Авторизация успешна' in m[1] for m in sent_messages)

    # 4. Выход /logout
    bot.handle_update({
        'message': {
            'chat': {'id': 9999},
            'from': {'id': 9999},
            'text': '/logout'
        }
    })
    assert bot.is_admin(9999) is False

def test_bot_help_and_stats_commands():
    """Тестирование команд /start, /help, /stats."""
    _seed_test_bot_data()
    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001}

    sent_messages = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))

    # Команда /help
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/help'
        }
    })
    assert len(sent_messages) == 1
    assert 'Электронные квитанции ТОО «КРЭК»' in sent_messages[0][1]

    # Команда /stats
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/stats'
        }
    })
    assert len(sent_messages) == 2
    assert 'Статистика сервиса Kvit-App' in sent_messages[1][1]
    assert 'Всего лицевых счетов:' in sent_messages[1][1]

def test_bot_search_account_and_receipt(tmp_path=None):
    """Тестирование поиска квитанций по лицевому счету и адресу."""
    _seed_test_bot_data()
    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001}

    # Создаем тестовый PDF файл
    pdf_rel = '80/01/800146_testhash.pdf'
    pdf_full = os.path.join(config.RECEIPTS_DIR, '80', '01', '800146_testhash.pdf')
    os.makedirs(os.path.dirname(pdf_full), exist_ok=True)
    with open(pdf_full, 'wb') as f:
        f.write(b'%PDF-1.4 test receipt')

    valid_hex_token = '0123456789abcdef0123456789abcdef'
    valid_hex_token2 = '0123456789abcdef0123456789abcde0'
    con = get_db()
    con.execute('''
        INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address)
        VALUES ('800146', '08.2026', ?, 'hash800146', ?, 'г. Алматы, ул. Абая 10, кв. 5')
    ''', (pdf_rel, valid_hex_token))
    con.execute('''
        INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address)
        VALUES ('800146', '09.2026', ?, 'hash800146_2', ?, 'г. Алматы, ул. Абая 10, кв. 5')
    ''', (pdf_rel, valid_hex_token2))
    con.commit()
    con.close()

    sent_messages = []
    sent_documents = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))
    bot.client.send_document = lambda chat_id, file_path, **kwargs: sent_documents.append((chat_id, file_path, kwargs))

    # 1. Поиск по прямому номеру счета (должны быть отправлены обе квитанции за 2 периода)
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '800146'
        }
    })

    assert any('800146' in m[1] for m in sent_messages)
    assert len(sent_documents) == 2
    assert any('08.2026' in d[2].get('caption', '') for d in sent_documents)
    assert any('09.2026' in d[2].get('caption', '') for d in sent_documents)

    # 2. Поиск по адресу
    sent_documents.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/address ул. Абая 10, кв 5'
        }
    })
    assert len(sent_documents) == 2

def test_bot_upload_pdf_receipt_flow(tmp_path=None):
    """Тестирование загрузки PDF квитанции через Telegram."""
    _seed_test_bot_data()
    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001}

    work_dir = str(tmp_path) if tmp_path else tempfile.mkdtemp()
    sample_pdf = os.path.join(work_dir, "incoming_receipt.pdf")

    try:
        import pymupdf as fitz
    except ImportError:
        import fitz

    doc = fitz.open()
    font_path = 'C:/Windows/Fonts/arial.ttf' if os.path.exists('C:/Windows/Fonts/arial.ttf') else None
    page = doc.new_page()
    text = "Лицевой счет: 800146\nПериод: 09.2026\nАдрес: ул. Абая 10, кв 5"
    if font_path:
        page.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
        page.insert_text((50, 100), text, fontname='arial', fontsize=12)
    else:
        page.insert_text((50, 100), text, fontsize=12)
    doc.save(sample_pdf)
    doc.close()

    # Мокаем скачивание из Telegram
    bot.client.get_file = lambda file_id: {'file_path': 'documents/file_123.pdf'}
    def mock_download(file_path, dest_path):
        shutil.copy(sample_pdf, dest_path)
        return True
    bot.client.download_file = mock_download

    sent_messages = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))

    # 1. Попытка загрузки неавторизованным пользователем (ID: 9999)
    bot.handle_update({
        'message': {
            'chat': {'id': 9999},
            'from': {'id': 9999},
            'document': {
                'file_id': 'file_123',
                'file_name': 'test.pdf',
                'mime_type': 'application/pdf'
            }
        }
    })
    assert any('Доступ ограничен' in m[1] for m in sent_messages)

    # 2. Загрузка администратором (ID: 1001)
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'document': {
                'file_id': 'file_123',
                'file_name': 'test_upload.pdf',
                'mime_type': 'application/pdf'
            }
        }
    })

    # Проверяем отчет о загрузке (дожидаемся выполнения фоновой задачи)
    for _ in range(50):
        report = [m[1] for m in sent_messages if 'Обработан файл:' in m[1]]
        if report:
            break
        time.sleep(0.05)

    assert len(report) == 1
    assert 'Привязано к счетам: <b>1</b>' in report[0]

    # 3. Загрузка одобренным обычным пользователем (ID: 7777, role: 'USER')
    con = get_db()
    con.execute("INSERT OR REPLACE INTO telegram_users(telegram_id, username, first_name, status, role, requested_at) VALUES (7777, 'user7777', 'Пользователь', 'APPROVED', 'USER', 123456)")
    con.commit()
    con.close()

    sample_pdf_user = os.path.join(work_dir, "incoming_receipt_user.pdf")
    doc_u = fitz.open()
    page_u = doc_u.new_page()
    text_u = "Лицевой счет: 800147\nПериод: 09.2026\nАдрес: ул. Достык 20, кв 1"
    if font_path:
        page_u.insert_font(fontname='arial', fontfile=font_path, set_simple=False)
        page_u.insert_text((50, 100), text_u, fontname='arial', fontsize=12)
    else:
        page_u.insert_text((50, 100), text_u, fontsize=12)
    doc_u.save(sample_pdf_user)
    doc_u.close()

    bot.client.download_file = lambda file_path, dest_path: shutil.copy(sample_pdf_user, dest_path) or True

    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 7777},
            'from': {'id': 7777},
            'document': {
                'file_id': 'file_user_123',
                'file_name': 'test_upload_user.pdf',
                'mime_type': 'application/pdf'
            }
        }
    })
    for _ in range(50):
        report_user = [m[1] for m in sent_messages if 'Обработан файл:' in m[1]]
        if report_user:
            break
        time.sleep(0.05)

    assert len(report_user) == 1
    assert 'Привязано к счетам: <b>1</b>' in report_user[0]

def test_bot_user_registration_and_admin_approval_lifecycle():
    """Тестирование полного жизненного цикла: подача заявки, инлайн-кнопки, подтверждение и отказ."""
    _seed_test_bot_data()
    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001}

    sent_messages = []
    answered_callbacks = []
    edited_messages = []

    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text, kwargs))
    bot.client.answer_callback_query = lambda cb_id, **kwargs: answered_callbacks.append((cb_id, kwargs)) or True
    bot.client.edit_message_text = lambda chat_id, msg_id, text, **kwargs: edited_messages.append((chat_id, msg_id, text, kwargs))

    # 1. Неавторизованный пользователь ищет квитанции -> прямой публичный поиск
    bot.handle_update({
        'message': {
            'chat': {'id': 5001},
            'from': {'id': 5001, 'first_name': 'Алибек', 'username': 'alibek_test'},
            'text': '800146'
        }
    })
    assert any('800146' in m[1] for m in sent_messages)

    # 2. Пользователь подает заявку на регистрацию (/register)
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 5001},
            'from': {'id': 5001, 'first_name': 'Алибек', 'last_name': 'С.', 'username': 'alibek_test'},
            'text': '/register'
        }
    })

    # Пользователю отправлено подтверждение принятия заявки
    user_msgs = [m for m in sent_messages if m[0] == 5001]
    assert len(user_msgs) == 1
    assert 'Заявка на регистрацию принята' in user_msgs[0][1]

    # Администратору (1001) пришло оповещение с инлайн-кнопками
    admin_msgs = [m for m in sent_messages if m[0] == 1001]
    assert len(admin_msgs) == 1
    assert 'Новая заявка на регистрацию' in admin_msgs[0][1]
    assert 'alibek_test' in admin_msgs[0][1]
    markup = admin_msgs[0][2].get('reply_markup', {})
    inline_buttons = markup.get('inline_keyboard', [[]])[0]
    assert len(inline_buttons) == 2
    assert inline_buttons[0]['callback_data'] == 'approve_user:5001'
    assert inline_buttons[1]['callback_data'] == 'reject_user:5001'

    # Проверяем запись в БД со статусом PENDING
    rec = bot.get_user_record(5001)
    assert rec is not None
    assert rec['status'] == 'PENDING'
    assert bot.is_approved(5001) is False

    # 3. Администратор (1001) нажимает "✅ Одобрить"
    sent_messages.clear()
    bot.handle_update({
        'callback_query': {
            'id': 'cb_approve_999',
            'from': {'id': 1001, 'first_name': 'Главный Админ'},
            'data': 'approve_user:5001',
            'message': {'chat': {'id': 1001}, 'message_id': 777}
        }
    })

    assert len(answered_callbacks) == 1
    assert 'Заявка успешно одобрена' in answered_callbacks[0][1].get('text', '')
    assert len(edited_messages) == 1
    assert 'Заявка ОДОБРЕНА' in edited_messages[0][2]

    # Пользователю пришло уведомление об успешной регистрации
    user_notify = [m for m in sent_messages if m[0] == 5001]
    assert len(user_notify) == 1
    assert 'Ваша регистрация подтверждена' in user_notify[0][1]

    # Статус в БД стал APPROVED
    rec_after = bot.get_user_record(5001)
    assert rec_after['status'] == 'APPROVED'
    assert bot.is_approved(5001) is True

    # 4. Теперь одобренный пользователь может искать квитанции
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 5001},
            'from': {'id': 5001},
            'text': '800146'
        }
    })
    assert any('Лицевой счёт:' in m[1] for m in sent_messages)

    # 5. Тестируем отклонение заявки для второго пользователя (5002)
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 5002},
            'from': {'id': 5002, 'first_name': 'Спамер', 'username': 'spammer'},
            'text': '📝 Зарегистрироваться'
        }
    })
    assert bot.get_user_record(5002)['status'] == 'PENDING'

    # Админ отклоняет
    sent_messages.clear()
    bot.handle_update({
        'callback_query': {
            'id': 'cb_reject_888',
            'from': {'id': 1001, 'first_name': 'Главный Админ'},
            'data': 'reject_user:5002',
            'message': {'chat': {'id': 1001}, 'message_id': 778}
        }
    })

    assert bot.get_user_record(5002)['status'] == 'REJECTED'
    assert bot.is_approved(5002) is False
    rejected_notify = [m for m in sent_messages if m[0] == 5002]
    assert len(rejected_notify) == 1
    assert 'отклонена' in rejected_notify[0][1]

def test_bot_admin_user_management_commands():
    """Тестирование текстовых команд администратора: /users, /approve, /reject."""
    _seed_test_bot_data()
    bot = TelegramBotService('test_token')
    bot.admin_ids = {1001}

    sent_messages = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text, kwargs))

    # Пользователь 6001 отправляет заявку
    bot.handle_update({
        'message': {
            'chat': {'id': 6001},
            'from': {'id': 6001, 'first_name': 'Ерлан'},
            'text': '/register'
        }
    })

    # Админ запрашивает /users
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/users'
        }
    })
    assert any('Заявки, ожидающие рассмотрения' in m[1] for m in sent_messages)

    # Админ одобряет через текстовую команду: /approve 6001
    sent_messages.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/approve 6001'
        }
    })
    assert any('успешно <b>одобрен</b>' in m[1] for m in sent_messages)
    assert bot.is_approved(6001) is True


