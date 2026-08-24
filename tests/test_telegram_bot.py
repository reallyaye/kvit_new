import os
import tempfile
import shutil
import config
from database import get_db, migrate_db
from services.security.auth_service import hash_password
from services.telegram_bot import TelegramClient, TelegramBotService, TelegramAPIError

def _seed_test_bot_data():
    migrate_db()
    con = get_db()
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
    assert 'Kvit-App Telegram Bot' in sent_messages[0][1]

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

    # Создаем тестовый PDF файл
    pdf_rel = '80/01/800146_testhash.pdf'
    pdf_full = os.path.join(config.RECEIPTS_DIR, '80', '01', '800146_testhash.pdf')
    os.makedirs(os.path.dirname(pdf_full), exist_ok=True)
    with open(pdf_full, 'wb') as f:
        f.write(b'%PDF-1.4 test receipt')

    valid_hex_token = '0123456789abcdef0123456789abcdef'
    con = get_db()
    con.execute('''
        INSERT OR REPLACE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address)
        VALUES ('800146', '08.2026', ?, 'hash800146', ?, 'г. Алматы, ул. Абая 10, кв. 5')
    ''', (pdf_rel, valid_hex_token))
    con.commit()
    con.close()

    sent_messages = []
    sent_documents = []
    bot.client.send_message = lambda chat_id, text, **kwargs: sent_messages.append((chat_id, text))
    bot.client.send_document = lambda chat_id, file_path, **kwargs: sent_documents.append((chat_id, file_path, kwargs))

    # 1. Поиск по прямому номеру счета
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '800146'
        }
    })

    assert any('800146' in m[1] for m in sent_messages)
    assert len(sent_documents) == 1
    assert os.path.samefile(sent_documents[0][1], pdf_full)

    # 2. Поиск по адресу
    sent_documents.clear()
    bot.handle_update({
        'message': {
            'chat': {'id': 1001},
            'from': {'id': 1001},
            'text': '/address ул. Абая 10, кв 5'
        }
    })
    assert len(sent_documents) == 1

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

    # Проверяем отчет о загрузке
    report = [m[1] for m in sent_messages if 'Обработан файл:' in m[1]]
    assert len(report) == 1
    assert 'Привязано к счетам: <b>1</b>' in report[0]

    # Проверяем, что квитанция появилась в базе данных
    con = get_db()
    row = con.execute('SELECT account_number, period FROM receipts WHERE account_number = "800146" AND period = "09.2026"').fetchone()
    con.close()
    assert row is not None
    assert row[0] == '800146'
    assert row[1] == '09.2026'

