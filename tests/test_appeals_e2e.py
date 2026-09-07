# -*- coding: utf-8 -*-
"""
End-to-End (E2E) браузерный / HTTP интеграционный тест жизненного цикла обращений граждан:
1. Загрузка публичной страницы формы подачи обращений (/appeals).
2. Защита от спама: отказ при заполненном поле-ловушке (honeypot 'website').
3. Валидация серверной части: отказ при некорректных входных данных.
4. Успешная регистрация обращения через /api/appeals с получением уникального номера ЭП-*.
5. Защита панели управления: редирект неавторизованного пользователя с /admin/appeals на /login.
6. Авторизация администратора через /login с установкой сессионной cookie.
7. Отображение зарегистрированного обращения в списке /admin/appeals.
8. Просмотр детальной карточки /admin/appeals/view?id=... и получение CSRF-токена.
9. Обновление статуса обращения на IN_REVIEW с комментарием администратора.
10. Верификация сохранения нового статуса и комментария в БД и UI.
"""

import re
import urllib.parse
import urllib.request

from services.appeals import appeal_service


def _http_request(url, method="GET", data=None, headers=None, follow_redirects=True):
    """Вспомогательная функция для HTTP-запросов с поддержкой cookies и отслеживанием редиректов."""
    if headers is None:
        headers = {}

    req = urllib.request.Request(url, data=data, headers=headers, method=method)

    class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            if not follow_redirects:
                return None
            return super().redirect_request(req, fp, code, msg, headers, newurl)

    opener = urllib.request.build_opener(NoRedirectHandler)

    try:
        with opener.open(req, timeout=10) as response:
            body = response.read().decode("utf-8", errors="replace")
            return {
                "status": response.status,
                "headers": dict(response.headers),
                "body": body,
                "url": response.url,
            }
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        return {
            "status": exc.code,
            "headers": dict(exc.headers),
            "body": body,
            "url": exc.url,
        }


def test_appeals_full_e2e_lifecycle(e2e_server):
    base_url = e2e_server["base_url"]
    admin_password = e2e_server["admin_password"]

    # ─────────────────────────────────────────────────────────────
    # Шаг 1: Загрузка публичной страницы формы /appeals
    # ─────────────────────────────────────────────────────────────
    res = _http_request(f"{base_url}/appeals")
    assert res["status"] == 200
    assert 'id="appeal-form"' in res["body"]
    assert 'name="applicant_name"' in res["body"]
    assert 'name="phone"' in res["body"]
    assert 'name="email"' in res["body"]
    assert 'name="service_address"' in res["body"]
    assert 'name="message"' in res["body"]
    assert 'name="website"' in res["body"]  # Honeypot
    assert 'name="consent"' in res["body"]

    # ─────────────────────────────────────────────────────────────
    # Шаг 2: Проверка защиты от спама (Honeypot)
    # ─────────────────────────────────────────────────────────────
    spam_data = urllib.parse.urlencode(
        {
            "category": "billing",
            "applicant_name": "Спам Бот",
            "phone": "+7 (777) 000-00-00",
            "email": "bot@spam.com",
            "service_address": "Интернет",
            "message": "Реклама и спам",
            "website": "http://spam-link.ru",  # Ловушка заполнена!
            "consent": "1",
        }
    ).encode("utf-8")

    res_spam = _http_request(
        f"{base_url}/api/appeals",
        method="POST",
        data=spam_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url,
        },
    )
    assert res_spam["status"] == 400
    assert "Spam detected" in res_spam["body"]

    # ─────────────────────────────────────────────────────────────
    # Шаг 3: Проверка серверной валидации (неверный телефон/email)
    # ─────────────────────────────────────────────────────────────
    invalid_data = urllib.parse.urlencode(
        {
            "category": "billing",
            "applicant_name": "Тест Невалидный",
            "phone": "123",  # Некорректный номер
            "email": "not-an-email",
            "service_address": "ул. Абая",
            "message": "Тест",
            "consent": "1",
        }
    ).encode("utf-8")

    res_invalid = _http_request(
        f"{base_url}/api/appeals",
        method="POST",
        data=invalid_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url,
        },
    )
    assert res_invalid["status"] == 400
    assert "Validation Error" in res_invalid["body"]

    # ─────────────────────────────────────────────────────────────
    # Шаг 4: Успешная подача реального обращения
    # ─────────────────────────────────────────────────────────────
    valid_data = urllib.parse.urlencode(
        {
            "category": "quality",
            "applicant_name": "Сериков Серик Серикович",
            "phone": "+7 (701) 555-44-33",
            "email": "serikov@example.kz",
            "account_number": "44556677",
            "service_address": "г. Караганда, пр. Бухар Жырау, 45, кв. 12",
            "message": "Прошу направить инспектора для проверки скачков напряжения в электросети.",
            "website": "",  # Пустой honeypot
            "consent": "1",
        }
    ).encode("utf-8")

    res_valid = _http_request(
        f"{base_url}/api/appeals",
        method="POST",
        data=valid_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": base_url,
        },
    )
    assert res_valid["status"] == 201
    import json
    res_json = json.loads(res_valid["body"])
    assert res_json["success"] is True
    reg_number = res_json["registration_number"]
    assert reg_number.startswith("ЭП-")

    # ─────────────────────────────────────────────────────────────
    # Шаг 5: Защита админки от неавторизованного доступа
    # ─────────────────────────────────────────────────────────────
    res_unauth = _http_request(
        f"{base_url}/admin/appeals",
        follow_redirects=False,
    )
    assert res_unauth["status"] in (302, 303)
    assert "/login" in res_unauth["headers"].get("Location", "")

    # ─────────────────────────────────────────────────────────────
    # Шаг 6: Авторизация администратора через /login
    # ─────────────────────────────────────────────────────────────
    login_payload = urllib.parse.urlencode(
        {
            "username": "admin",
            "password": admin_password,
        }
    ).encode("utf-8")

    res_login = _http_request(
        f"{base_url}/login",
        method="POST",
        data=login_payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert res_login["status"] in (302, 303)
    set_cookie = res_login["headers"].get("Set-Cookie", "")
    assert "session=" in set_cookie
    # Извлекаем значение сессионной cookie
    session_cookie = set_cookie.split(";")[0]

    # ─────────────────────────────────────────────────────────────
    # Шаг 7: Доступ к /admin/appeals с сессионной cookie
    # ─────────────────────────────────────────────────────────────
    res_admin_list = _http_request(
        f"{base_url}/admin/appeals",
        headers={"Cookie": session_cookie},
    )
    assert res_admin_list["status"] == 200
    assert "Обращения граждан" in res_admin_list["body"]
    assert reg_number in res_admin_list["body"]
    assert "Сериков Серик Серикович" in res_admin_list["body"]

    # ─────────────────────────────────────────────────────────────
    # Шаг 8: Просмотр детальной карточки /admin/appeals/view?id=...
    # ─────────────────────────────────────────────────────────────
    # Находим id обращения
    appeal_obj = appeal_service.get_by_registration_number(reg_number)
    assert appeal_obj is not None
    appeal_id = appeal_obj["id"]

    res_detail = _http_request(
        f"{base_url}/admin/appeals/view?id={appeal_id}",
        headers={"Cookie": session_cookie},
    )
    assert res_detail["status"] == 200
    assert reg_number in res_detail["body"]
    assert "скачков напряжения" in res_detail["body"]

    # Извлекаем CSRF-токен из формы на детальной странице
    csrf_match = re.search(r'name="csrf_token"\s+value="([a-f0-9]+)"', res_detail["body"])
    assert csrf_match is not None, "CSRF-токен не найден в форме обновления статуса!"
    csrf_token = csrf_match.group(1)

    # ─────────────────────────────────────────────────────────────
    # Шаг 9: Обновление статуса на IN_REVIEW с комментарием
    # ─────────────────────────────────────────────────────────────
    update_data = urllib.parse.urlencode(
        {
            "id": str(appeal_id),
            "status": "IN_REVIEW",
            "admin_comment": "Передано главному инженеру для выезда бригады.",
            "csrf_token": csrf_token,
        }
    ).encode("utf-8")

    res_update = _http_request(
        f"{base_url}/admin/appeals/update",
        method="POST",
        data=update_data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Cookie": session_cookie,
        },
        follow_redirects=False,
    )
    assert res_update["status"] in (302, 303)
    assert f"id={appeal_id}" in res_update["headers"].get("Location", "")

    # ─────────────────────────────────────────────────────────────
    # Шаг 10: Проверка обновленного состояния в UI и БД
    # ─────────────────────────────────────────────────────────────
    res_detail_updated = _http_request(
        f"{base_url}/admin/appeals/view?id={appeal_id}",
        headers={"Cookie": session_cookie},
    )
    assert res_detail_updated["status"] == 200
    assert "Передано главному инженеру" in res_detail_updated["body"]

    # Проверяем также через сервис обращения
    refreshed_appeal = appeal_service.get_by_id(appeal_id)
    assert refreshed_appeal["status"] == "IN_REVIEW"
    assert refreshed_appeal["admin_comment"] == "Передано главному инженеру для выезда бригады."
