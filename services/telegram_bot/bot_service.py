# -*- coding: utf-8 -*-
import datetime
import html
import os
import re
import shutil
import tempfile
import threading
import time
from typing import Optional, Set

import config
from database import get_db
from database.connection import write_transaction
from logger import logger
from services.receipts import receipt_service
from services.security import auth_service
from services.tasks import task_manager

from .telegram_client import TelegramAPIError, TelegramClient

BTN_STATS = "📊 Статистика"
BTN_SEARCH = "🔍 Найти квитанцию"
BTN_HELP = "❓ Помощь"
BTN_REQUESTS = "👥 Заявки"
BTN_AUTH = "🔐 Авторизация"
BTN_STATUS = "⏳ Статус заявки"
BTN_REGISTER = "📝 Зарегистрироваться"
MSG_DIVIDER = "────────────────────────"


class TelegramBotService:
    """Сервис Telegram-бота для регистрации пользователей, обработки квитанций, поиска счетов и выдачи статистики."""

    def __init__(self, token: Optional[str] = None):
        self.token = (token or config.TELEGRAM_BOT_TOKEN or '').strip()
        self.client = TelegramClient(self.token, timeout=config.TELEGRAM_POLLING_TIMEOUT)
        self.admin_ids: Set[int] = set(config.TELEGRAM_ADMIN_IDS)
        self.authenticated_users: Set[int] = set()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    # ────────────────────── Проверка прав и статусов ──────────────────────

    def get_user_record(self, user_id: int) -> Optional[dict]:
        """Возвращает запись пользователя из таблицы telegram_users."""
        con = get_db()
        try:
            row = con.execute(
                'SELECT telegram_id, username, first_name, last_name, status, role, requested_at, reviewed_at, reviewed_by, comment '
                'FROM telegram_users WHERE telegram_id = ?',
                (user_id,)
            ).fetchone()
            if row:
                return dict(row)
            return None
        finally:
            con.close()

    def is_admin(self, user_id: int) -> bool:
        """Проверяет, является ли пользователь администратором."""
        if user_id in self.admin_ids or user_id in config.TELEGRAM_ADMIN_IDS:
            return True
        if user_id in self.authenticated_users:
            return True
        rec = self.get_user_record(user_id)
        if rec and rec.get('status') == 'APPROVED' and rec.get('role') == 'ADMIN':
            return True
        return False

    def is_approved(self, user_id: int) -> bool:
        """Проверяет, одобрен ли доступ пользователю к боту."""
        if self.is_admin(user_id):
            return True
        rec = self.get_user_record(user_id)
        if rec and rec.get('status') == 'APPROVED':
            return True
        return False

    def get_all_admin_ids(self) -> Set[int]:
        """Возвращает множество всех ID администраторов (из config, активных сессий и БД)."""
        admins = set(self.admin_ids) | set(config.TELEGRAM_ADMIN_IDS) | set(self.authenticated_users)
        con = get_db()
        try:
            rows = con.execute(
                "SELECT telegram_id FROM telegram_users WHERE status = 'APPROVED' AND role = 'ADMIN'"
            ).fetchall()
            for r in rows:
                admins.add(r[0])
        except Exception:
            pass
        finally:
            con.close()
        return admins

    def get_main_keyboard(self, user_id: int) -> dict:
        """Возвращает кнопки главного меню в зависимости от роли и статуса."""
        is_adm = self.is_admin(user_id)
        is_appr = self.is_approved(user_id)

        if is_adm:
            keyboard = [
                [{"text": BTN_SEARCH}, {"text": BTN_STATS}],
                [{"text": BTN_REQUESTS}, {"text": BTN_HELP}]
            ]
        elif is_appr:
            keyboard = [
                [{"text": BTN_SEARCH}, {"text": BTN_STATS}],
                [{"text": BTN_HELP}]
            ]
        else:
            keyboard = [
                [{"text": BTN_SEARCH}, {"text": BTN_HELP}],
                [{"text": BTN_AUTH}]
            ]

        return {
            "keyboard": keyboard,
            "resize_keyboard": True,
            "one_time_keyboard": False
        }

    # ────────────────────── Обработка входящих обновлений ──────────────────────

    def handle_update(self, update: dict):
        """Маршрутизация входящего обновления Telegram."""
        # 1. Обработка нажатий на инлайн-кнопки (Callback Query)
        if 'callback_query' in update:
            self._handle_callback_query(update['callback_query'])
            return

        message = update.get('message')
        if not message:
            return

        chat_id = message.get('chat', {}).get('id')
        from_user = message.get('from', {})
        user_id = from_user.get('id')

        if not chat_id or not user_id:
            return

        # 2. Если прислан документ (PDF квитанция)
        if 'document' in message:
            self._handle_document(chat_id, user_id, message)
            return

        # 3. Если текстовое сообщение
        text = (message.get('text') or '').strip()
        if not text:
            return

        self._handle_text(chat_id, user_id, text, message)

    # ────────────────────── Callback Query (Одобрение / Отклонение) ──────────────────────

    def _handle_callback_query(self, cb: dict):
        """Обработка нажатий администратором на инлайн-кнопки одобрения/отклонения заявок."""
        cb_id = cb.get('id')
        from_user = cb.get('from', {})
        admin_id = from_user.get('id')
        admin_name = from_user.get('first_name') or f"Admin({admin_id})"
        data = cb.get('data') or ''
        message = cb.get('message', {})
        msg_chat_id = message.get('chat', {}).get('id')
        msg_id = message.get('message_id')

        if not self.is_admin(admin_id):
            if cb_id:
                self.client.answer_callback_query(cb_id, text="⛔ Действие доступно только администраторам.", show_alert=True)
            return

        # Обработка одобрения заявки: approve_user:<user_id>
        if data.startswith('approve_user:'):
            try:
                target_user_id = int(data.split(':', 1)[1])
            except (ValueError, IndexError):
                return

            now_ts = time.time()
            with write_transaction() as con:
                con.execute(
                    "UPDATE telegram_users SET status = 'APPROVED', reviewed_at = ?, reviewed_by = ? WHERE telegram_id = ?",
                    (now_ts, admin_id, target_user_id)
                )

            if cb_id:
                self.client.answer_callback_query(cb_id, text="✅ Заявка успешно одобрена!")

            target_rec = self.get_user_record(target_user_id)
            user_display = html.escape(target_rec.get('first_name') or str(target_user_id)) if target_rec else str(target_user_id)
            user_uname = f" (@{html.escape(target_rec.get('username'))})" if target_rec and target_rec.get('username') else ""

            if msg_chat_id and msg_id:
                updated_text = (
                    f"✅ <b>Заявка ОДОБРЕНА</b>\n"
                    f"────────────────────────\n"
                    f"👤 <b>Пользователь:</b> {user_display}{user_uname}\n"
                    f"🆔 <b>ID:</b> <code>{target_user_id}</code>\n"
                    f"👨‍💼 <b>Администратор:</b> {html.escape(admin_name)}\n"
                    f"🕒 <b>Время:</b> {datetime.datetime.fromtimestamp(now_ts).strftime('%d.%m.%Y %H:%M')}"
                )
                try:
                    self.client.edit_message_text(msg_chat_id, msg_id, updated_text)
                except Exception as edit_err:
                    logger.debug(f"[Telegram] Не удалось отредактировать сообщение заявки: {edit_err}")

            try:
                self.client.send_message(
                    target_user_id,
                    "🎉 <b>Поздравляем! Ваша регистрация подтверждена.</b>\n\n"
                    "Теперь вам доступен полный функционал сервиса:\n"
                    "• Поиск квитанций по номеру лицевого счёта\n"
                    "• Поиск квитанций по адресу\n"
                    "• Просмотр статистики базы данных\n\n"
                    "Нажмите /start или выберите нужное действие в меню ниже.",
                    reply_markup=self.get_main_keyboard(target_user_id)
                )
            except Exception as notify_err:
                logger.warning(f"[Telegram] Не удалось отправить уведомление пользователю {target_user_id}: {notify_err}")

            return

        # Обработка отклонения заявки: reject_user:<user_id>
        if data.startswith('reject_user:'):
            try:
                target_user_id = int(data.split(':', 1)[1])
            except (ValueError, IndexError):
                return

            now_ts = time.time()
            with write_transaction() as con:
                con.execute(
                    "UPDATE telegram_users SET status = 'REJECTED', reviewed_at = ?, reviewed_by = ? WHERE telegram_id = ?",
                    (now_ts, admin_id, target_user_id)
                )

            if cb_id:
                self.client.answer_callback_query(cb_id, text="❌ Заявка отклонена.")

            target_rec = self.get_user_record(target_user_id)
            user_display = html.escape(target_rec.get('first_name') or str(target_user_id)) if target_rec else str(target_user_id)
            user_uname = f" (@{html.escape(target_rec.get('username'))})" if target_rec and target_rec.get('username') else ""

            if msg_chat_id and msg_id:
                updated_text = (
                    f"❌ <b>Заявка ОТКЛОНЕНА</b>\n"
                    f"────────────────────────\n"
                    f"👤 <b>Пользователь:</b> {user_display}{user_uname}\n"
                    f"🆔 <b>ID:</b> <code>{target_user_id}</code>\n"
                    f"👨‍💼 <b>Администратор:</b> {html.escape(admin_name)}\n"
                    f"🕒 <b>Время:</b> {datetime.datetime.fromtimestamp(now_ts).strftime('%d.%m.%Y %H:%M')}"
                )
                try:
                    self.client.edit_message_text(msg_chat_id, msg_id, updated_text)
                except Exception as edit_err:
                    logger.debug(f"[Telegram] Не удалось отредактировать сообщение заявки: {edit_err}")

            try:
                self.client.send_message(
                    target_user_id,
                    "❌ <b>Ваша заявка на регистрацию была отклонена администратором.</b>\n\n"
                    "Если вы считаете, что это произошло по ошибке, вы можете отправить повторную заявку с помощью команды <code>/register</code>.",
                    reply_markup=self.get_main_keyboard(target_user_id)
                )
            except Exception as notify_err:
                logger.warning(f"[Telegram] Не удалось отправить уведомление пользователю {target_user_id}: {notify_err}")

            return

    # ────────────────────── Регистрация пользователей ──────────────────────

    def _handle_registration_request(self, chat_id: int, user_id: int, from_user: dict):
        """Обрабатывает подачу заявки на регистрацию от пользователя."""
        if self.is_approved(user_id):
            self.client.send_message(
                chat_id,
                "✅ <b>Вы уже зарегистрированы и имеете доступ к боту!</b>",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        rec = self.get_user_record(user_id)
        if rec and rec.get('status') == 'PENDING':
            self.client.send_message(
                chat_id,
                "⏳ <b>Ваша заявка уже находится на рассмотрении.</b>\n"
                "Администратор сервиса уведомит вас сразу после проверки.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        username = from_user.get('username') or ''
        first_name = from_user.get('first_name') or ''
        last_name = from_user.get('last_name') or ''
        now_ts = time.time()

        with write_transaction() as con:
            con.execute('''
                INSERT INTO telegram_users(telegram_id, username, first_name, last_name, status, role, requested_at)
                VALUES (?, ?, ?, ?, 'PENDING', 'USER', ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    last_name = excluded.last_name,
                    status = 'PENDING',
                    requested_at = excluded.requested_at,
                    reviewed_at = NULL,
                    reviewed_by = NULL
            ''', (user_id, username, first_name, last_name, now_ts))

        self.client.send_message(
            chat_id,
            "⏳ <b>Заявка на регистрацию принята!</b>\n\n"
            "Запрос отправлен администраторам сервиса. Как только администратор подтвердит регистрацию, вы получите уведомление.",
            reply_markup=self.get_main_keyboard(user_id)
        )

        admin_ids = self.get_all_admin_ids()
        admin_alert = [
            "🔔 <b>Новая заявка на регистрацию в Kvit-App!</b>",
            MSG_DIVIDER,
            f"👤 <b>Имя:</b> {html.escape(first_name)} {html.escape(last_name)}".strip(),
            f"🔗 <b>Username:</b> @{html.escape(username)}" if username else "🔗 <b>Username:</b> <i>не указан</i>",
            f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>",
            f"📅 <b>Дата:</b> {datetime.datetime.fromtimestamp(now_ts).strftime('%d.%m.%Y %H:%M')}",
            MSG_DIVIDER,
            "Выберите действие:"
        ]
        admin_markup = {
            "inline_keyboard": [
                [
                    {"text": "✅ Одобрить", "callback_data": f"approve_user:{user_id}"},
                    {"text": "❌ Отклонить", "callback_data": f"reject_user:{user_id}"}
                ]
            ]
        }

        for adm_id in admin_ids:
            try:
                self.client.send_message(adm_id, "\n".join(admin_alert), reply_markup=admin_markup)
            except Exception as e:
                logger.warning(f"[Telegram] Не удалось отправить уведомление о заявке админу {adm_id}: {e}")

    # ────────────────────── Админ-список заявок и пользователей ──────────────────────

    def _send_users_list_to_admin(self, chat_id: int, user_id: int):
        """Отправляет список ожидающих и зарегистрированных пользователей администратору."""
        if not self.is_admin(user_id):
            return

        con = get_db()
        try:
            pending_rows = con.execute(
                "SELECT telegram_id, username, first_name, last_name, requested_at FROM telegram_users WHERE status = 'PENDING' ORDER BY requested_at DESC"
            ).fetchall()
            approved_count = con.execute(
                "SELECT COUNT(*) FROM telegram_users WHERE status = 'APPROVED'"
            ).fetchone()[0]
        finally:
            con.close()

        if not pending_rows:
            self.client.send_message(
                chat_id,
                f"👥 <b>Управление пользователями:</b>\n\n"
                f"✅ Одобренных пользователей: <b>{approved_count}</b>\n"
                f"⏳ Заявок на рассмотрении: <b>0</b>\n\n"
                f"<i>Все новые заявки будут автоматически приходить вам с кнопками одобрения.</i>",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        self.client.send_message(
            chat_id,
            f"⏳ <b>Заявки, ожидающие рассмотрения ({len(pending_rows)}):</b>",
            reply_markup=self.get_main_keyboard(user_id)
        )

        for row in pending_rows[:10]:
            uid, uname, fname, lname, req_ts = row[0], row[1], row[2], row[3], row[4]
            u_name_full = f"{fname or ''} {lname or ''}".strip() or f"User({uid})"
            u_uname_str = f"@{uname}" if uname else "нет"
            req_time_str = datetime.datetime.fromtimestamp(req_ts).strftime('%d.%m.%Y %H:%M') if req_ts else "недавно"

            msg_text = (
                f"👤 <b>{html.escape(u_name_full)}</b> ({html.escape(u_uname_str)})\n"
                f"🆔 ID: <code>{uid}</code> | 📅 {req_time_str}"
            )
            markup = {
                "inline_keyboard": [
                    [
                        {"text": "✅ Одобрить", "callback_data": f"approve_user:{uid}"},
                        {"text": "❌ Отклонить", "callback_data": f"reject_user:{uid}"}
                    ]
                ]
            }
            self.client.send_message(chat_id, msg_text, reply_markup=markup)

    # ────────────────────── Загрузка документов ──────────────────────

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

        # Проверка прав доступа: загрузка доступна всем одобренным пользователям и администраторам
        if not self.is_approved(user_id):
            self.client.send_message(
                chat_id,
                "⛔ <b>Доступ ограничен</b>\n"
                "Загрузка квитанций доступна только зарегистрированным пользователям.\n\n"
                "Для подачи заявки нажмите кнопку <b>«📝 Зарегистрироваться»</b> или отправьте команду <code>/register</code>.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # Информируем пользователя о начале обработки
        self.client.send_message(
            chat_id,
            f"⏳ <i>Загрузка и распознавание «{html.escape(file_name)}»...</i>",
            reply_to_message_id=message.get('message_id')
        )

        tmp_dir = tempfile.mkdtemp(prefix='kvit_tg_upload_', dir=config.SPOOL_DIR)
        tmp_path = os.path.join(tmp_dir, file_name)

        try:
            file_info = self.client.get_file(file_id)
            tg_file_path = file_info.get('file_path')

            if not tg_file_path or not self.client.download_file(tg_file_path, tmp_path):
                shutil.rmtree(tmp_dir, ignore_errors=True)
                self.client.send_message(
                    chat_id,
                    f"❌ Не удалось скачать файл «{html.escape(file_name)}» из Telegram. Попробуйте еще раз."
                )
                return

            self.client.send_message(
                chat_id,
                f"📥 <b>Файл «{html.escape(file_name)}» принят!</b>\n"
                f"Поставлен в очередь фоновой обработки. По окончании вы получите итоговый отчёт.",
                reply_markup=self.get_main_keyboard(user_id)
            )

            def _on_telegram_job_completed(task):
                status_icon = "✅" if (task.orphan == 0 and task.skipped == 0 and task.duplicates == 0) else "⚠️"
                report_lines = [
                    f"{status_icon} <b>Обработан файл:</b> <code>{html.escape(file_name)}</code>",
                    MSG_DIVIDER,
                    f"✅ Привязано к счетам: <b>{task.added}</b>",
                    f"⚠️ Без счёта в базе: <b>{task.orphan}</b>",
                    f"🔄 Дубликатов: <b>{task.duplicates}</b>",
                    f"❌ Ошибок/не распознано: <b>{task.skipped}</b>"
                ]

                if task.details:
                    report_lines.append("\n📋 <b>Детализация страниц:</b>")
                    max_lines = 15
                    for d in task.details[:max_lines]:
                        report_lines.append(f"• {html.escape(d.strip())}")
                    if len(task.details) > max_lines:
                        report_lines.append(f"<i>...и ещё {len(task.details) - max_lines} записей</i>")

                if task.error_message:
                    report_lines.append(f"\n⚠️ Ошибка: {html.escape(task.error_message)}")

                try:
                    self.client.send_message(
                        chat_id,
                        "\n".join(report_lines),
                        reply_markup=self.get_main_keyboard(user_id)
                    )
                except Exception as send_err:
                    logger.error(f"[Telegram] Сбой отправки отчёта в чат {chat_id}: {send_err}", exc_info=True)

            task_manager.submit_pdf_job(
                files=[(file_name, tmp_path)],
                source='telegram',
                spool_dir=tmp_dir,
                callbacks=[_on_telegram_job_completed],
                meta={'user_id': str(user_id), 'chat_id': str(chat_id), 'file_name': file_name}
            )

        except Exception as e:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            logger.error(f"[Telegram] Ошибка при приёме файла {file_name}: {e}", exc_info=True)
            self.client.send_message(
                chat_id,
                f"❌ <b>Произошла ошибка при обработке файла:</b>\n<code>{html.escape(str(e))}</code>"
            )

    # ────────────────────── Текстовые команды ──────────────────────

    def _handle_text(self, chat_id: int, user_id: int, text: str, message: dict):
        """Обработка текстовых команд и поисковых запросов."""
        lower_text = text.lower()

        # 1. Регистрация пользователя
        if lower_text in ('/register', '📝 зарегистрироваться', 'зарегистрироваться', 'регистрация'):
            self._handle_registration_request(chat_id, user_id, message.get('from', {}))
            return

        # 2. Проверка статуса заявки
        if lower_text in ('⏳ статус заявки', 'статус заявки', '/status'):
            rec = self.get_user_record(user_id)
            if self.is_approved(user_id):
                self.client.send_message(
                    chat_id,
                    "✅ <b>Ваша регистрация одобрена!</b> Вы имеете полный доступ к поиску квитанций.",
                    reply_markup=self.get_main_keyboard(user_id)
                )
            elif rec and rec.get('status') == 'PENDING':
                self.client.send_message(
                    chat_id,
                    "⏳ <b>Ваша заявка находится на рассмотрении у администратора.</b>\nОжидайте уведомления.",
                    reply_markup=self.get_main_keyboard(user_id)
                )
            elif rec and rec.get('status') == 'REJECTED':
                self.client.send_message(
                    chat_id,
                    "❌ <b>Ваша заявка была отклонена.</b> Вы можете отправить повторную заявку с помощью команды <code>/register</code>.",
                    reply_markup=self.get_main_keyboard(user_id)
                )
            else:
                self.client.send_message(
                    chat_id,
                    "ℹ️ Вы ещё не подавали заявку на регистрацию. Нажмите <b>«📝 Зарегистрироваться»</b> или отправьте команду <code>/register</code>.",
                    reply_markup=self.get_main_keyboard(user_id)
                )
            return

        # 3. Список заявок / пользователей (для администратора)
        if lower_text in ('/users', '/pending', '👥 заявки', 'заявки', 'пользователи'):
            if self.is_admin(user_id):
                self._send_users_list_to_admin(chat_id, user_id)
            else:
                self.client.send_message(chat_id, "⛔ Доступно только администраторам.", reply_markup=self.get_main_keyboard(user_id))
            return

        # 4. Прямые команды одобрения / отклонения текстом: /approve <id> или /reject <id>
        if lower_text.startswith('/approve ') or lower_text.startswith('/reject '):
            if not self.is_admin(user_id):
                self.client.send_message(chat_id, "⛔ Доступно только администраторам.")
                return
            action, target_str = text.split(maxsplit=1)
            try:
                target_uid = int(target_str.strip())
            except ValueError:
                self.client.send_message(chat_id, "⚠️ Укажите корректный цифровой Telegram ID: <code>/approve 12345678</code>")
                return

            now_ts = time.time()
            if action.lower() == '/approve':
                with write_transaction() as con:
                    con.execute("UPDATE telegram_users SET status = 'APPROVED', reviewed_at = ?, reviewed_by = ? WHERE telegram_id = ?",
                                (now_ts, user_id, target_uid))
                self.client.send_message(chat_id, f"✅ Пользователь <code>{target_uid}</code> успешно <b>одобрен</b>!")
                try:
                    self.client.send_message(
                        target_uid,
                        "🎉 <b>Поздравляем! Ваша регистрация подтверждена.</b>\nТеперь вам доступен поиск квитанций.",
                        reply_markup=self.get_main_keyboard(target_uid)
                    )
                except Exception:
                    pass
            else:
                with write_transaction() as con:
                    con.execute("UPDATE telegram_users SET status = 'REJECTED', reviewed_at = ?, reviewed_by = ? WHERE telegram_id = ?",
                                (now_ts, user_id, target_uid))
                self.client.send_message(chat_id, f"❌ Пользователь <code>{target_uid}</code> <b>отклонен</b>.")
                try:
                    self.client.send_message(
                        target_uid,
                        "❌ <b>Ваша заявка на регистрацию отклонена администратором.</b>",
                        reply_markup=self.get_main_keyboard(target_uid)
                    )
                except Exception:
                    pass
            return

        # 5. Команды старта и помощи
        if lower_text in ('/start', '/help', '❓ помощь', 'помощь'):
            self._send_help(chat_id, user_id)
            return

        # 6. Авторизация администратора по паролю
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

        # 7. Выход из режима администратора
        if lower_text == '/logout':
            self.authenticated_users.discard(user_id)
            self.client.send_message(
                chat_id,
                "👋 Вы вышли из режима администратора.",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # 8. Статистика и сверка (только для одобренных операторов и администраторов)
        if lower_text in ('/stats', '/reconcile', '📊 статистика', 'статистика', 'сверка'):
            if not self.is_approved(user_id):
                self.client.send_message(
                    chat_id,
                    "🔒 <b>Служебный раздел</b>\n\n"
                    "Просмотр статистики доступен только сотрудникам ТОО «КРЭК».\n"
                    "Для входа используйте: <code>/login ваш_пароль</code>",
                    reply_markup=self.get_main_keyboard(user_id)
                )
                return
            self._send_stats(chat_id, user_id)
            return

        # 9. Поиск квитанции (подсказка)
        if lower_text in ('🔍 найти квитанцию', 'найти квитанцию', '/search', '/kvit'):
            self.client.send_message(
                chat_id,
                "🔍 <b>Поиск квитанции:</b>\n\n"
                "• Отправьте <b>номер лицевого счёта</b> (например: <code>800146</code> или <code>103997</code>)\n"
                "• Или используйте команду: <code>/kvit 800146</code>\n"
                "• Или укажите точный адрес: <code>/address ул. Абая 10, кв 5</code>\n\n"
                "<i>Бот сразу найдёт и пришлёт PDF-квитанцию в чат!</i>",
                reply_markup=self.get_main_keyboard(user_id)
            )
            return

        # 10. Поиск по команде /address
        if lower_text.startswith('/address'):
            query = text[len('/address'):].strip()
            self._search_by_address(chat_id, user_id, query)
            return

        # 11. Поиск по команде /kvit или /search с аргументом
        if lower_text.startswith('/kvit ') or lower_text.startswith('/search '):
            query = text.split(maxsplit=1)[1].strip()
            self._search_account_or_address(chat_id, user_id, query)
            return

        # 12. Прямой ввод текста: поиск квитанции по номеру счёта или адресу для любого пользователя
        self._search_account_or_address(chat_id, user_id, text)

    def _send_help(self, chat_id: int, user_id: int):
        """Отправляет справочное сообщение с описанием команд."""
        is_adm = self.is_admin(user_id)
        is_appr = self.is_approved(user_id)

        if is_adm:
            role_badge = "👑 <b>Статус:</b> Администратор"
        elif is_appr:
            role_badge = "👤 <b>Статус:</b> Оператор / Сотрудник"
        else:
            role_badge = "⚡ <b>Официальный бот ТОО «КРЭК»</b>"

        msg = [
            "📄 <b>Электронные квитанции ТОО «КРЭК»</b>",
            role_badge,
            "────────────────────────",
            "🔍 <b>Как получить квитанцию:</b>",
            "• Просто <b>отправьте номер вашего лицевого счёта</b> (например: <code>800146</code> или <code>103997</code>)",
            "• Или отправьте команду поиска по адресу: <code>/address ул. Абая 10, кв 5</code>",
            "",
            "<i>Бот мгновенно найдёт и вышлет официальный PDF-файл квитанции прямо в этот чат.</i>"
        ]

        if is_appr or is_adm:
            msg.extend([
                "",
                "🚀 <b>Для сотрудников (Загрузка квитанций):</b>",
                "• Отправьте PDF-файл пачки квитанций в этот чат для автоматической нарезки и привязки к счетам.",
                "• <code>/stats</code> — статистика базы и процент покрытия квитанциями"
            ])

        if is_adm:
            msg.extend([
                "",
                "👑 <b>Команды администратора:</b>",
                "• <code>/users</code> — список заявок операторов",
                "• <code>/approve &lt;ID&gt;</code> — одобрить оператора",
                "• <code>/reject &lt;ID&gt;</code> — отклонить заявку"
            ])

        if not is_appr and not is_adm:
            msg.extend([
                "",
                "🔐 <b>Сотрудникам:</b> для входа используйте команду <code>/login &lt;пароль&gt;</code>"
            ])

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
                "SELECT DISTINCT period FROM receipts WHERE period IS NOT NULL AND period != '' ORDER BY period DESC"
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
            {"command": "register", "description": "Заявка на регистрацию в боте"},
            {"command": "status", "description": "Проверить статус регистрации"},
            {"command": "search", "description": "Поиск квитанции по счету или адресу"},
            {"command": "stats", "description": "Статистика базы и сверка"},
            {"command": "login", "description": "Авторизация администратора"},
            {"command": "help", "description": "Справка по возможностям"}
        ]
        self.client.set_my_commands(commands)

    def run_polling(self):
        """Цикл long polling обновлений."""
        token = (self.token or config.TELEGRAM_BOT_TOKEN or '').strip()
        if not token:
            logger.warning("[Telegram] TELEGRAM_BOT_TOKEN не настроен в .env. Бот отключен.")
            return

        self.token = token
        self.client = TelegramClient(self.token, timeout=config.TELEGRAM_POLLING_TIMEOUT)

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

    def start_in_thread(self) -> Optional[threading.Thread]:
        """Запускает long polling в отдельном фоновом потоке-демоне."""
        token = (self.token or config.TELEGRAM_BOT_TOKEN or '').strip()
        if not token:
            logger.info("[Telegram] TELEGRAM_BOT_TOKEN не задан в .env — Telegram-бот выключен.")
            return None
        self.token = token
        self.client = TelegramClient(self.token, timeout=config.TELEGRAM_POLLING_TIMEOUT)
        self._thread = threading.Thread(target=self.run_polling, name="TelegramBotThread", daemon=True)
        self._thread.start()
        return self._thread

    def stop(self):
        """Останавливает цикл polling."""
        self._running = False


telegram_bot_service = TelegramBotService()
