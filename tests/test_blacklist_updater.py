import ipaddress
import logging
import os
import tempfile
from unittest.mock import patch

from scripts.update_blacklists import (
    build_blocklist_conf,
    fetch_feed,
    is_whitelisted,
    load_manual_blocklist,
    load_whitelist,
)


def test_load_whitelist():
    logger = logging.getLogger("test")
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("# comment\n192.168.1.0/24 0;\n8.8.8.8 0;\ninvalid_line\n")
        path = f.name

    try:
        wl = load_whitelist(path, logger)
        assert ipaddress.ip_network("192.168.1.0/24") in wl
        assert ipaddress.ip_network("8.8.8.8/32") in wl
        assert len(wl) == 2
    finally:
        os.remove(path)


def test_load_manual_blocklist():
    logger = logging.getLogger("test")
    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8") as f:
        f.write("# manual\n45.148.10.247 1;\n185.220.101.0/24 1;\n")
        path = f.name

    try:
        bl = load_manual_blocklist(path, logger)
        assert ipaddress.ip_network("45.148.10.247/32") in bl
        assert ipaddress.ip_network("185.220.101.0/24") in bl
        assert len(bl) == 2
    finally:
        os.remove(path)


def test_is_whitelisted():
    wl = {ipaddress.ip_network("212.154.0.0/16"), ipaddress.ip_network("8.8.8.8/32")}
    assert is_whitelisted(ipaddress.ip_network("212.154.10.5/32"), wl) is True
    assert is_whitelisted(ipaddress.ip_network("8.8.8.8/32"), wl) is True
    assert is_whitelisted(ipaddress.ip_network("45.148.10.247/32"), wl) is False


def test_fetch_feed_skips_private_and_comments():
    logger = logging.getLogger("test")
    mock_content = b"""
    # Spamhaus DROP test
    45.148.10.0/24 ; SBL12345
    10.0.0.0/8 ; should be skipped (private)
    127.0.0.1/32 ; should be skipped (loopback)
    invalid_token
    185.220.101.50/32 ; SBL67890
    """

    class MockResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self):
            return mock_content

    with patch("urllib.request.urlopen", return_value=MockResponse()):
        nets = fetch_feed("Test Feed", "https://example.com/feed.txt", logger)
        assert ipaddress.ip_network("45.148.10.0/24") in nets
        assert ipaddress.ip_network("185.220.101.50/32") in nets
        assert ipaddress.ip_network("10.0.0.0/8") not in nets
        assert ipaddress.ip_network("127.0.0.1/32") not in nets
        assert len(nets) == 2


def test_build_blocklist_conf_dry_run():
    logger = logging.getLogger("test")
    with tempfile.TemporaryDirectory() as tmp_dir:
        # создаем структуру nginx/lists
        lists_dir = os.path.join(tmp_dir, "nginx", "lists")
        os.makedirs(lists_dir, exist_ok=True)
        with open(os.path.join(lists_dir, "manual_blocklist.conf"), "w", encoding="utf-8") as f:
            f.write("45.148.10.247 1;\n")

        success = build_blocklist_conf(tmp_dir, dry_run=True, no_reload=True, logger=logger)
        assert success is True
