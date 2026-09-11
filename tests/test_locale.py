from templates.locale import localized_path, set_locale
from templates.portal_layout import portal_layout


def test_localized_path_and_locale_layout():
    assert localized_path('/', 'ru') == '/ru/'
    assert localized_path('/consumers', 'kk') == '/kk/consumers'

    set_locale('kk')
    rendered = portal_layout('<p>content</p>', current_slug='consumers')
    assert '<html lang="kk">' in rendered
    assert 'hreflang="ru"' in rendered
    assert 'https://krec.kz/kk/consumers' in rendered


def test_unknown_locale_falls_back_to_russian():
    assert set_locale('unknown') == 'ru'
    assert localized_path('/kvit/', 'unknown') == '/ru/kvit/'
