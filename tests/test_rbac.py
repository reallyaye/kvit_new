# -*- coding: utf-8 -*-
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from database.connection import write_transaction
from database.migrations import migrate_db
from services.security.auth_service import auth_service


class TestRBACAndAuth(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Гарантируем чистую SQLite базу для тестов
        migrate_db()

    def setUp(self):
        # Очищаем тестовых пользователей кроме admin
        with write_transaction() as con:
            con.execute("DELETE FROM users WHERE username != 'admin'")
            con.execute("DELETE FROM audit_logs")

    def test_admin_seeding_and_credentials(self):
        """Проверка автоматической инициализации admin и проверки пароля."""
        admin_hash = getattr(config, 'ADMIN_PASSWORD_HASH', '')
        self.assertTrue(bool(admin_hash))

        users = auth_service.list_users()
        admin_user = next((u for u in users if u['username'] == 'admin'), None)
        self.assertIsNotNone(admin_user)
        self.assertEqual(admin_user['role'], 'admin')

    def test_create_and_manage_operator(self):
        """Проверка создания, блокировки и удаления оператора отдела сбыта."""
        # 1. Создание оператора
        op = auth_service.create_user(
            username='sbyt_test1',
            password='TestPassword123!',
            full_name='Тестовый Оператор Сбыта',
            role='operator'
        )
        self.assertEqual(op['username'], 'sbyt_test1')
        self.assertEqual(op['role'], 'operator')

        # 2. Проверка авторизации
        user_info = auth_service.verify_credentials('sbyt_test1', 'TestPassword123!')
        self.assertIsNotNone(user_info)
        self.assertEqual(user_info['role'], 'operator')
        self.assertEqual(user_info['full_name'], 'Тестовый Оператор Сбыта')

        # 3. Неверный пароль
        self.assertIsNone(auth_service.verify_credentials('sbyt_test1', 'WrongPassword'))

        # 4. Смена пароля
        auth_service.update_user_password('sbyt_test1', 'NewSecurePassword456!')
        self.assertIsNotNone(auth_service.verify_credentials('sbyt_test1', 'NewSecurePassword456!'))

        # 5. Блокировка
        auth_service.toggle_user_active('sbyt_test1', False)
        self.assertIsNone(auth_service.verify_credentials('sbyt_test1', 'NewSecurePassword456!'))
        auth_service.toggle_user_active('sbyt_test1', True)
        self.assertIsNotNone(auth_service.verify_credentials('sbyt_test1', 'NewSecurePassword456!'))

        # 6. Удаление
        auth_service.delete_user('sbyt_test1')
        self.assertIsNone(auth_service.verify_credentials('sbyt_test1', 'NewSecurePassword456!'))

    def test_admin_protection(self):
        """Запрет на удаление или блокировку главного администратора."""
        with self.assertRaises(ValueError):
            auth_service.delete_user('admin')
        with self.assertRaises(ValueError):
            auth_service.toggle_user_active('admin', False)

    def test_session_role_tracking(self):
        """Сессия корректно сохраняет и возвращает роль пользователя."""
        op_token = auth_service.create_session(username='sbyt_anna', role='operator')
        admin_token = auth_service.create_session(username='admin', role='admin')

        op_data = auth_service.get_session_user(op_token)
        self.assertIsNotNone(op_data)
        self.assertEqual(op_data['username'], 'sbyt_anna')
        self.assertEqual(op_data['role'], 'operator')

        admin_data = auth_service.get_session_user(admin_token)
        self.assertIsNotNone(admin_data)
        self.assertEqual(admin_data['username'], 'admin')
        self.assertEqual(admin_data['role'], 'admin')

    def test_audit_logging(self):
        """Проверка фиксации действий в журнал аудита."""
        auth_service.log_audit('sbyt_anna', '192.168.1.50', 'UPLOAD_RECEIPTS', 'Загружено 15 квитанций')
        auth_service.log_audit('admin', '192.168.1.10', 'CREATE_USER', 'Создан оператор sbyt_anna')

        logs = auth_service.list_audit_logs(10)
        self.assertGreaterEqual(len(logs), 2)
        actions = [item['action'] for item in logs]
        self.assertIn('UPLOAD_RECEIPTS', actions)
        self.assertIn('CREATE_USER', actions)

    def test_audit_filtering_and_stats(self):
        """Проверка фильтрации записей аудита и вычисления агрегированной статистики."""
        auth_service.log_audit('admin', '127.0.0.1', 'LOGIN', 'Успешный вход')
        auth_service.log_audit('operator1', '10.0.0.5', 'LOGIN_FAILED', 'Неверный пароль')
        auth_service.log_audit('operator1', '10.0.0.5', 'UPLOAD_RECEIPTS', 'Загружено 100 квитанций')
        auth_service.log_audit('admin', '127.0.0.1', 'PAGE_SAVE', 'Обновлена страница contacts')

        # 1. Фильтр по пользователю
        admin_logs = auth_service.list_audit_logs(username='admin')
        self.assertTrue(all(item['username'] == 'admin' for item in admin_logs))
        self.assertEqual(len(admin_logs), 2)

        # 2. Фильтр по действию
        upload_logs = auth_service.list_audit_logs(action='UPLOAD_RECEIPTS')
        self.assertEqual(len(upload_logs), 1)
        self.assertEqual(upload_logs[0]['username'], 'operator1')

        # 3. Поиск по деталям или IP
        search_logs = auth_service.list_audit_logs(search='contacts')
        self.assertEqual(len(search_logs), 1)
        self.assertEqual(search_logs[0]['action'], 'PAGE_SAVE')

        # 4. Проверка статистики
        stats = auth_service.get_audit_stats()
        self.assertGreaterEqual(stats['total'], 4)
        self.assertGreaterEqual(stats['logins'], 1)
        self.assertGreaterEqual(stats['failed_logins'], 1)
        self.assertGreaterEqual(stats['uploads'], 1)
        self.assertIn('admin', stats['users'])
        self.assertIn('operator1', stats['users'])
        self.assertIn('UPLOAD_RECEIPTS', stats['actions'])

    def test_render_admin_audit_page(self):
        """Проверка генерации HTML страницы журнала аудита."""
        from templates.admin_cms_views import render_admin_audit_log
        auth_service.log_audit('admin', '127.0.0.1', 'LOGIN', 'Вход в систему')
        logs = auth_service.list_audit_logs(10)
        stats = auth_service.get_audit_stats()
        filters_map = {'username': '', 'action': '', 'search': '', 'limit': 50}
        html_out = render_admin_audit_log(logs, stats, filters_map, csrf_token='test_csrf_token')
        self.assertIn('Журнал аудита действий пользователей', html_out)
        self.assertIn('LOGIN', html_out)
        self.assertIn('127.0.0.1', html_out)
        self.assertIn('admin', html_out)

    def test_create_and_manage_assistant(self):
        """Проверка создания, аутентификации, сессии и управления административным помощником."""
        # 1. Создание помощника
        asst = auth_service.create_user(
            username='pomoshnik_asel',
            password='AselPassword789!',
            full_name='Аселя (Канцелярия / Приёмная)',
            role='assistant'
        )
        self.assertEqual(asst['username'], 'pomoshnik_asel')
        self.assertEqual(asst['role'], 'assistant')

        # 2. Проверка учетных данных
        creds = auth_service.verify_credentials('pomoshnik_asel', 'AselPassword789!')
        self.assertIsNotNone(creds)
        self.assertEqual(creds['role'], 'assistant')
        self.assertEqual(creds['full_name'], 'Аселя (Канцелярия / Приёмная)')

        # 3. Сессия возвращает роль assistant
        token = auth_service.create_session(username='pomoshnik_asel', role='assistant')
        sess_user = auth_service.get_session_user(token)
        self.assertIsNotNone(sess_user)
        self.assertEqual(sess_user['username'], 'pomoshnik_asel')
        self.assertEqual(sess_user['role'], 'assistant')

        # 4. Блокировка и удаление
        auth_service.toggle_user_active('pomoshnik_asel', False)
        self.assertIsNone(auth_service.verify_credentials('pomoshnik_asel', 'AselPassword789!'))
        auth_service.toggle_user_active('pomoshnik_asel', True)
        self.assertIsNotNone(auth_service.verify_credentials('pomoshnik_asel', 'AselPassword789!'))

        auth_service.delete_user('pomoshnik_asel')
        self.assertIsNone(auth_service.verify_credentials('pomoshnik_asel', 'AselPassword789!'))

    def test_invalid_role_rejected(self):
        """Проверка отклонения некорректных ролей при создании пользователя."""
        with self.assertRaises(ValueError) as ctx:
            auth_service.create_user('bad_role_user', 'Pass123456!', role='superhacker')
        self.assertIn('Недопустимая роль', str(ctx.exception))

    def test_assistant_ui_components(self):
        """Проверка отображения роли 'assistant' в UI: бейдж, форма создания, навбар и страница отказа в доступе."""
        from templates.admin_cms_views import _admin_nav_bar, render_access_denied_page, render_admin_users

        # Навбар для помощника
        nav_html = _admin_nav_bar('appeals', role='assistant', username='asel')
        self.assertIn('Канцелярия / Приёмная', nav_html)
        self.assertIn('Обращения', nav_html)
        self.assertNotIn('Сотрудники', nav_html)
        self.assertNotIn('Страницы сайта', nav_html)

        # Таблица сотрудников с бейджем помощника
        users = [
            {'username': 'admin', 'full_name': 'Главный Админ', 'role': 'admin', 'is_active': 1},
            {'username': 'asel', 'full_name': 'Аселя Помощник', 'role': 'assistant', 'is_active': 1},
            {'username': 'sbyt1', 'full_name': 'Оператор 1', 'role': 'operator', 'is_active': 1},
        ]
        users_html = render_admin_users(users, [], csrf_token='csrf_test', current_username='admin')
        self.assertIn('Административный помощник', users_html)
        self.assertIn('value="assistant"', users_html)

        # Страница доступа
        denied_html = render_access_denied_page(role='assistant', username='asel')
        self.assertIn('Административный помощник', denied_html)
        self.assertIn('/admin/appeals', denied_html)


if __name__ == '__main__':
    unittest.main()
