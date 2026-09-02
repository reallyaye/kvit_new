# -*- coding: utf-8 -*-
import os
import sys
import unittest
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from database.connection import get_db, write_transaction
from database.migrations import migrate_db
from services.security.auth_service import auth_service, hash_password, verify_password_hash


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
        actions = [l['action'] for l in logs]
        self.assertIn('UPLOAD_RECEIPTS', actions)
        self.assertIn('CREATE_USER', actions)


if __name__ == '__main__':
    unittest.main()
