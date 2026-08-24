import os
import re
import html
import tempfile
import shutil
import threading
import time
from typing import Optional, Set
import config
from database import get_db, write_transaction
from services.pdf import pdf_processor
from services.receipts import receipt_service
from services.security import auth_service
from services.websocket import ws_manager
from logger import logger
from .telegram_client import TelegramClient, TelegramAPIError

class TelegramBotService:
    """Сервис Telegram-бота для обработки квитанций, поиска счетов и выдачи статистики."""

    def __init__(self, token: Optional[str] = None):
        self.token = (token or config.TELEGRAM_BOT_TOKEN or '').strip()
        self.client = TelegramClient(self.token, timeout=config.TELEGRAM_POLLING_TIMEOUT)
        self.admin_ids: Set[int] = set(config.TELEGRAM_ADMIN_IDS)
        self.authenticated_users: Set[int] = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        if user_id in self.admin_ids:
            return True
        if user_id in self.authenticated_users:
            return True
        # Если ADMIN_IDS не заданы вовсе, но задан ADMIN_PASSWORD_HASH, требуем /login
        return False

    def get_main_keyboard(self, user_id: int) -> dict:
        """Возвращает кнопки главного меню."""
        is_adm = self.is_admin(user_id)
        keyboard = [
            [{"text": "📊 Статистика"}, {"text": "🔍 Найти квитанцию"}],
            [{"text": "❓ Помощь"}]
        ]
        if not is_adm:
            keyboard[1].append({"text": "🔐 Авторизация"})
        return {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    # ────────────────────── Обработка входящих обновлений ──────────────────────

    def handle_update(self, update: dict):
        """Маршрутизация входящего обновления Telegram."""
        message = update.get('message')
        if not message:
            return

        chat_id = message.get('chat', {}).get('id')
        from_user = message.get('from', {})
        user_id = from_user.get('id')

        if not chat_id or not user_id:
            return

        # 1. Если прислан документ (PDF квитанция)
        if 'document' in message:
            self._handle_document(chat_id, user_id, message)
            return

        # 2. Если текстовое сообщение
        text = (message.get('text') or '').strip()
        if not text:
            return

        self._handle_text(chat_id, user_id, text, message)

    def _handle_document(self, chat_id: int, user_id: int, message: dict):
        """Обработка загрузки PDF-квитанций."""
        doc = message.get('document', {})
        file_name = doc.get('file_name', 'receipt.pdf')
        mime_type = doc.get('mime_type', '')
        file_id = doc.get('file_id')

        # Проверка расширения / MIME-типа
        if not (file_name.lower().endswith('.pdf') or 'pdf' in mime_type.lower()):
            self.client.send_message(
                chat_id,
                "⚠️ Пожалуйста, отправьте квитанцию в формате <b>PDF</b>.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # Проверка прав доступа
        if not self.is_admin(user_id):
            self.client.send_message(
                chat_id,
                "⛔ <b>Доступ ограничен</b>\n"
                "Загрузка квитанций доступна только администраторам сервиса.\n\n"
                "Для входа используйте команду: <code>/login &lt;пароль&gt;</code>",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # Информируем пользователя о начале обработки
        status_msg = self.client.send_message(
            chat_id,
            f"⏳ <i>Загрузка и распознавание «{html.escape(file_name)}»...</i>",
            reply_to_message_id=message.get('message_id')
        )

        tmp_dir = tempfile.mkdtemp(prefix='kvit_tg_upload_')
        tmp_path = os.path.join(tmp_dir, file_name)

        try:
            # Получаем путь к файлу на серверах Telegram и скачиваем его
            file_info = self.client.get_file(file_id)
            tg_file_path = file_info.get('file_path')

            if not tg_file_path or not self.client.download_file(tg_file_path, tmp_path):
                self.client.send_message(
                    chat_id,
                    f"❌ Не удалось скачать файл «{html.escape(file_name)}» из Telegram. Попробуйте еще раз."
                )
                return

            # Обрабатываем PDF через встроенный процессор
            con = get_db()
            try:
                known_accounts = {row[0] for row in con.execute('SELECT account_number FROM accounts').fetchall()}
                existing_hashes = {row[0] for row in con.execute('SELECT content_hash FROM receipts WHERE content_hash IS NOT NULL').fetchall()}
            finally:
                con.close()

            added, orphan, skipped, dups, details, receipts_to_insert = pdf_processor.process_single_pdf(
                tmp_path, file_name, known_accounts, existing_hashes
            )

            if receipts_to_insert:
                with write_transaction() as con_write:
                    con_write.executemany(
                        'INSERT OR IGNORE INTO receipts(account_number, period, pdf_file, content_hash, access_token, address) VALUES (?,?,?,?,?,?)',
                        receipts_to_insert
                    )
                # Оповещаем подключенные веб-клиенты через WebSocket
                try:
                    ws_manager.broadcast('upload_batch_completed', {
                        'files_count': 1,
                        'added': added,
                        'orphan': orphan,
                        'duplicates': dups,
                        'skipped': skipped,
                        'source': 'telegram'
                    })
                except Exception as ws_err:
                    logger.debug(f"[Telegram] WS broadcast error: {ws_err}")

            # Формируем красивый отчет для Telegram
            status_icon = "✅" if (orphan == 0 and skipped == 0 and dups == 0) else "⚠️"
            report_lines = [
                f"{status_icon} <b>Обработан файл:</b> <code>{html.escape(file_name)}</code>",
                "────────────────────────",
                f"✅ Привязано к счетам: <b>{added}</b>",
                f"⚠️ Без счёта в базе: <b>{orphan}</b>",
                f"🔄 Дубликатов: <b>{dups}</b>",
                f"❌ Ошибок/не распознано: <b>{skipped}</b>"
            ]

            if details:
                report_lines.append("\n📋 <b>Детализация страниц:</b>")
                # Ограничиваем длину детализации, чтобы не превысить лимит сообщения Telegram (4096 символов)
                max_lines = 15
                for d in details[:max_lines]:
                    report_lines.append(f"• {html.escape(d.strip())}")
                if len(details) > max_lines:
                    report_lines.append(f"<i>...и ещё {len(details) - max_lines} записей</i>")

            self.client.send_message(
                chat_id,
                "\n".join(report_lines),
                reply_markup=self.get_main_keyboard(user_id)
            )

        except Exception as e:
            logger.error(f"[Telegram] Ошибка при обработке файла {file_name}: {e}", exc_info=True)
            self.client.send_message(
                chat_id,
                f"❌ <b>Произошла ошибка при обработке файла:</b>\n<code>{html.escape(str(e))}</code>"
            )
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _handle_text(self, chat_id: int, user_id: int, text: str, message: dict):
        """Обработка текстовых команд и поисковых запросов."""
        lower_text = text.lower()

        # 1. Команды старта и помощи
        if lower_text in ('/start', '/help', '❓ помощь', 'помощь'):
            self._send_help(chat_id, user_id)
            return

        # 2. Авторизация администратора
        if lower_text.startswith('/login') or lower_text in ('🔐 авторизация', 'вход'):
            parts = text.split(maxsplit=1)
            if len(parts) > 1:
                password = parts[1].strip()
                if auth_service.verify_password(password):
                    self.authenticated_users.add(user_id)
                    self.client.send_message(
                        chat_id,
                        "✅ <b>Авторизация успешна!</b>\n"
                        "Вам открыт доступ к загрузке квитанций и управлению через Telegram.",
                        reply_markup=self.get_main_keyboard(user_id)
                    )
                else:
                    self.client.send_message(
                        chat_id,
                        "❌ <b>Неверный пароль администратора.</b>\n"
                        "Попробуйте снова: <code>/login &lt;пароль&gt;</code>",
                        reply_markup=self.get_main_keyboard(user_id)
                    )
            else:
                self.client.send_message(
                    chat_id,
                    "🔐 Для авторизации администратора отправьте команду:\n"
                    "<code>/login ваш_пароль</code>",
                    reply_markup=self.get_main_keyboard(user_id)
                )
            return

        # 3. Выход из режима администратора
        if lower_text == '/logout':
            self.authenticated_users.discard(user_id)
            self.client.send_message(
                chat_id,
                "👋 Вы вышли из режима администратора.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # 4. Статистика и сверка
        if lower_text in ('/stats', '/reconcile', '📊 статистика', 'статистика', 'сверка'):
            self._send_stats(chat_id, user_id)
            return

        # 5. Поиск квитанции (подсказка)
        if lower_text in ('🔍 найти квитанцию', 'найти квитанцию', '/search', '/kvit'):
            self.client.send_message(
                chat_id,
                "🔍 <b>Поиск квитанции:</b>\n\n"
                "• Отправьте <b>номер лицевого счёта</b> (например: <code>800146</code>)\n"
                "• Или используйте команду: <code>/kvit 800146</code>\n"
                "• Или укажите точный адрес: <code>/address ул. Абая 10, кв 5</code>",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # 6. Поиск по команде /address
        if lower_text.startswith('/address'):
            query = text[len('/address'):].strip()
            self._search_by_address(chat_id, user_id, query)
            return

        # 7. Поиск по команде /kvit или /search с аргументом
        if lower_text.startswith('/kvit ') or lower_text.startswith('/search '):
            query = text.split(maxsplit=1)[1].strip()
            self._search_account_or_address(chat_id, user_id, query)
            return

        # 8. Прямой ввод текста: проверка номера счёта или адреса
        self._search_account_or_address(chat_id, user_id, text)

    def _send_help(self, chat_id: int, user_id: int):
        """Отправляет справочное сообщение с описанием команд."""
        is_adm = self.is_admin(user_id)
        role_badge = "👑 <b>Статус:</b> Администратор" if is_adm else "👤 <b>Статус:</b> Пользователь"

        msg = [
            "📄 <b>Kvit-App Telegram Bot</b>",
            role_badge,
            "────────────────────────",
            "🚀 <b>Как загрузить квитанции:</b>",
            "Просто <b>отправьте PDF-файл</b> (или несколько файлов) в этот чат. Бот автоматически распознает лицевые счета, периоды, распределит по папкам и сохранит в базу данных.",
            "",
            "🔍 <b>Поиск и выдача квитанций:</b>",
            "• Отправьте номер счёта: <code>800146</code> или <code>/kvit 800146</code>",
            "• Поиск по точному адресу: <code>/address ул. Пушкина 12, кв 4</code>",
            "<i>(Бот сразу пришлёт PDF-файл квитанции прямо в чат)</i>",
            "",
            "📊 <b>Команды управления:</b>",
            "• <code>/stats</code> — статистика базы и процент покрытия квитанциями",
            "• <code>/login &lt;пароль&gt;</code> — авторизация администратора",
            "• <code>/help</code> — это меню справки"
        ]
        self.client.send_message(chat_id, "\n".join(msg), reply_markup=self.get_main_keyboard(user_id))

    def _send_stats(self, chat_id: int, user_id: int):
        """Отправляет актуальную статистику базы и сверки."""
        con = get_db()
        try:
            total_accounts = con.execute('SELECT COUNT(*) FROM accounts').fetchone()[0]
            total_receipts = con.execute('SELECT COUNT(*) FROM receipts').fetchone()[0]
            matched = con.execute('''
                SELECT COUNT(DISTINCT a.account_number)
                FROM accounts a
                JOIN receipts r ON a.account_number = r.account_number
            ''').fetchone()[0]
            orphans = con.execute('''
                SELECT COUNT(DISTINCT r.account_number)
                FROM receipts r
                LEFT JOIN accounts a ON r.account_number = a.account_number
                WHERE a.account_number IS NULL
            ''').fetchone()[0]
            periods_rows = con.execute(
                'SELECT DISTINCT period FROM receipts WHERE period IS NOT NULL AND period != "" ORDER BY period DESC'
            ).fetchall()
            periods = [r['period'] for r in periods_rows]
        finally:
            con.close()

        unmatched = max(0, total_accounts - matched)
        coverage_pct = round(matched / total_accounts * 100, 1) if total_accounts > 0 else 0.0

        periods_str = ", ".join(f"<code>{html.escape(p)}</code>" for p in periods[:6]) or "нет"
        if len(periods) > 6:
            periods_str += f" <i>(всего {len(periods)})</i>"

        msg = [
            "📊 <b>Статистика сервиса Kvit-App</b>",
            "────────────────────────",
            f"👥 Всего лицевых счетов: <b>{total_accounts:,}</b>",
            f"📄 Загружено квитанций: <b>{total_receipts:,}</b>",
            f"✅ Счетов с квитанцией: <b>{matched:,}</b>",
            f"❌ Счетов без квитанции: <b>{unmatched:,}</b>",
            f"⚠️ Квитанций без счёта в базе: <b>{orphans:,}</b>",
            f"📈 Процент покрытия: <b>{coverage_pct}%</b>",
            "────────────────────────",
            f"🗓 Доступные периоды: {periods_str}"
        ]
        self.client.send_message(chat_id, "\n".join(msg), reply_markup=self.get_main_keyboard(user_id))

    def _search_account_or_address(self, chat_id: int, user_id: int, query: str):
        """Интеллектуальный поиск: по номеру лицевого счёта или по адресу."""
        clean_q = query.strip()
        if not clean_q:
            return

        # Если запрос состоит только из цифр (номер лицевого счёта)
        if re.match(r'^\d+$', clean_q):
            self._send_account_receipts(chat_id, user_id, clean_q)
        else:
            self._search_by_address(chat_id, user_id, clean_q)

    def _send_account_receipts(self, chat_id: int, user_id: int, account_number: str):
        """Ищет информацию по лицевому счету и отправляет PDF квитанции."""
        account_info = receipt_service.get_account(account_number)
        receipts = receipt_service.get_receipts(account_number)

        if not account_info and not receipts:
            self.client.send_message(
                chat_id,
                f"❌ Лицевой счёт <code>{html.escape(account_number)}</code> не найден в базе данных.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        cust_name = account_info.get('customer_name', '') if account_info else ''
        addr = account_info.get('address', '') if account_info else ''

        header_lines = [
            f"📋 <b>Лицевой счёт:</b> <code>{html.escape(account_number)}</code>"
        ]
        if cust_name:
            header_lines.append(f"👤 <b>Абонент:</b> {html.escape(cust_name)}")
        if addr:
            header_lines.append(f"🏠 <b>Адрес:</b> {html.escape(addr)}")

        if not receipts:
            header_lines.append("\n⚠️ <i>Квитанции для данного счёта ещё не загружены.</i>")
            self.client.send_message(chat_id, "\n".join(header_lines), reply_markup=self.get_main_keyboard(user_id))
            return

        header_lines.append(f"\n📄 <b>Найдено квитанций:</b> {len(receipts)}")
        self.client.send_message(chat_id, "\n".join(header_lines))

        # Отправляем последнюю квитанцию файлом
        latest_rec = receipts[0]
        token = latest_rec['access_token']
        pdf_full_path = receipt_service.get_pdf_by_token(token) if token else None

        if pdf_full_path and os.path.isfile(pdf_full_path):
            caption = f"📄 Квитанция за период: <b>{html.escape(latest_rec['period'])}</b> (Л/С: <code>{html.escape(account_number)}</code>)"
            visible_name = f"Квитанция_{account_number}_{latest_rec['period']}.pdf".replace('/', '_').replace(' ', '_')
            try:
                self.client.send_document(chat_id, pdf_full_path, caption=caption, visible_filename=visible_name)
            except Exception as e:
                logger.error(f"[Telegram] Ошибка при отправке PDF {pdf_full_path}: {e}")
                self.client.send_message(chat_id, f"⚠️ Не удалось прикрепить PDF-файл: {html.escape(str(e))}")
        else:
            self.client.send_message(chat_id, f"⚠️ Файл квитанции за период {latest_rec['period']} не найден на диске.")

    def _search_by_address(self, chat_id: int, user_id: int, address_query: str):
        """Строгий поиск лицевого счета по адресу с защитой приватности."""
        status, acc_data, prompt_msg = receipt_service.search_account_by_specific_address(address_query)

        if status == 'EXACT_MATCH' and acc_data:
            acc_num = str(acc_data['account_number'])
            self._send_account_receipts(chat_id, user_id, acc_num)
        else:
            # Выводим подсказку с уточнением
            self.client.send_message(
                chat_id,
                f"ℹ️ {html.escape(prompt_msg)}",
                reply_markup=self.get_main_keyboard(user_id)
            )

    # ────────────────────── Long Polling & Управление потоком ──────────────────────

    def setup_bot_menu(self):
        """Устанавливает подсказки команд в интерфейсе Telegram."""
        commands = [
            {"command": "start", "description": "Перезапуск и главное меню"},
            {"command": "stats", "description": "Статистика базы и сверка"},
            {"command": "search", "description": "Поиск квитанции по счету или адресу"},
            {"command": "login", "description": "Авторизация администратора"},
            {"command": "help", "description": "Справка по возможностям"}
        ]
        self.client.set_my_commands(commands)

    def run_polling(self):
        """Цикл long polling обновлений."""
        if not self.token:
            logger.warning("[Telegram] TELEGRAM_BOT_TOKEN не настроен. Бот отключен.")
            return

        logger.info("[Telegram] Запуск Telegram-бота...")
        try:
            bot_info = self.client.get_me()
            logger.info(f"[Telegram] Бот успешно подключен: @{bot_info.get('username')} ({bot_info.get('first_name')})")
            self.setup_bot_menu()
        except Exception as e:
            logger.error(f"[Telegram] Ошибка подключения к Telegram Bot API: {e}")
            return

        self._running = True

        while self._running:
            try:
                updates = self.client.get_updates(
                    offset=self._last_update_id + 1,
                    timeout=config.TELEGRAM_POLLING_TIMEOUT
                )
                for update in updates:
                    update_id = update.get('update_id')
                    if update_id:
                        self._last_update_id = max(self._last_update_id, update_id)
                    try:
                        self.handle_update(update)
                    except Exception as upd_err:
                        logger.error(f"[Telegram] Ошибка обработки обновления {update_id}: {upd_err}", exc_info=True)
            except TelegramAPIError as api_err:
                if self._running:
                    logger.warning(f"[Telegram] Ошибка API: {api_err}. Повтор через 5с...")
                    time.sleep(5)
            except Exception as e:
                if self._running:
                    logger.error(f"[Telegram] Непредвиденная ошибка в polling: {e}. Повтор через 5с...")
                    time.sleep(5)

        logger.info("[Telegram] Бот остановлен.")

    def start_in_thread(self) -> threading.Thread:
        """Запускает long polling в отдельном фоновом потоке-демоне."""
        if not self.token:
            return None
        self._thread = threading.Thread(target=self.run_polling, name="TelegramBotThread", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        """Останавливает цикл polling."""
        self._running = False

telegram_bot_service = TelegramBotService()
