from templates.layout import layout
from templates.locale import localized_path, set_locale
from templates.portal_layout import portal_layout
from templates.search_views import render_search_form


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


def test_kazakh_translation_is_applied_to_receipt_ui():
    set_locale('kk')
    rendered = layout(render_search_form([]))
    assert 'Квитанция алу' in rendered
    assert 'Жиі қойылатын сұрақтар' in rendered
    assert 'Жеке шот' in rendered
