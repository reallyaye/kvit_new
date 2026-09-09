import io
from unittest import mock

import config
from server import AppRequestHandler
from services.security.auth_service import AuthService


def _failed_login_handler(ip: str = "203.0.113.40"):
    handler = AppRequestHandler.__new__(AppRequestHandler)
    handler.client_address = (ip, 54321)
    handler.headers = {}
    handler.rfile = io.BytesIO(b"")
    handler._read_bounded_body = lambda _limit: b"username=admin&password=wrong"
    responses = []
    handler.send_html = lambda body, code=200, extra_headers=None: responses.append(
        (body, code, extra_headers or {})
    )
    return handler, responses


def test_recent_failed_login_count_uses_ip_and_window():
    con = mock.MagicMock()
    con.execute.return_value.fetchone.return_value = (4,)

    with mock.patch("services.security.auth_service.get_db", return_value=con):
        count = AuthService(session_store=mock.MagicMock()).count_recent_failed_logins(
            "203.0.113.40", 900, now=1000.0
        )

    assert count == 4
    query, params = con.execute.call_args.args
    assert "action = 'LOGIN_FAILED'" in query
    assert params == ("203.0.113.40", 100.0)
    con.close.assert_called_once()


def test_fifth_failed_login_persistently_blocks_ip():
    handler, responses = _failed_login_handler()

    with mock.patch("server.auth_service.verify_credentials", return_value=None), \
         mock.patch("server.auth_service.log_audit") as log_audit, \
         mock.patch("server.auth_service.count_recent_failed_logins", return_value=5), \
         mock.patch("server.ip_throttler.ban_ip") as ban_ip:
        handler._handle_login()

    ban_ip.assert_called_once_with(
        "203.0.113.40",
        duration_seconds=config.LOGIN_FAILURE_BAN_SECONDS,
        reason=mock.ANY,
    )
    assert [call.args[2] for call in log_audit.call_args_list] == [
        "LOGIN_FAILED",
        "IP_BLOCKED",
    ]
    assert responses[0][1] == 429
    assert responses[0][2]["Retry-After"] == str(config.LOGIN_FAILURE_BAN_SECONDS)


def test_failed_login_below_threshold_is_not_blocked():
    handler, responses = _failed_login_handler()

    with mock.patch("server.auth_service.verify_credentials", return_value=None), \
         mock.patch("server.auth_service.log_audit"), \
         mock.patch("server.auth_service.count_recent_failed_logins", return_value=4), \
         mock.patch("server.ip_throttler.ban_ip") as ban_ip:
        handler._handle_login()

    ban_ip.assert_not_called()
    assert responses[0][1] == 200


def test_nginx_blocks_known_scanner_and_wordpress_probes():
    with open("nginx/nginx.conf", encoding="utf-8") as f:
        nginx_config = f.read()

    assert nginx_config.count("deny 45.148.10.247;") == 2
    assert "wp-login\\.php" in nginx_config
    assert "location = /index.php" in nginx_config
