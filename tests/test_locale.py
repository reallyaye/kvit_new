import pytest

from templates.i18n import KK_TRANSLATIONS, translate_html
from templates.layout import layout
from templates.locale import localized_path, set_locale
from templates.portal_layout import portal_layout
from templates.portal_views import render_page
from templates.search_views import render_search_form


@pytest.fixture(autouse=True)
def reset_locale_after_test():
    yield
    set_locale('ru')


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


def test_kazakh_catalog_covers_all_public_pages():
    assert len(KK_TRANSLATIONS) >= 1_000


def test_kazakh_translation_matches_multiline_html_text_nodes():
    set_locale('kk')
    rendered = translate_html(
        '<p>Сбор правоустанавливающих документов на объект/участок,\n'
        'удостоверения личности/свидетельства о регистрации, ситуационного плана '
        'и расчет требуемой мощности.</p>'
    )

    assert 'Нысанға немесе жер учаскесіне құқық белгілейтін құжаттарды' in rendered
    assert 'Сбор правоустанавливающих документов' not in rendered


def test_kazakh_homepage_has_no_russian_fallbacks_in_primary_content():
    set_locale('kk')
    rendered = render_page('home')

    for russian_text in (
        'РЕГИОНАЛЬНЫЙ ОПЕРАТОР РАСПРЕДЕЛИТЕЛЬНЫХ СЕТЕЙ',
        'Получить квитанцию',
        'Узнать тариф',
        'Подключиться к сети',
        'Обращение',
        'Надежная передача и распределение электроэнергии для 98 347 км² территории региона.',
    ):
        assert russian_text not in rendered

    for kazakh_text in (
        'ӨҢІРЛІК ТАРАТУ ЖЕЛІЛЕРІНІҢ ОПЕРАТОРЫ',
        'Квитанция алу',
        'Тарифті білу',
        'Желіге қосылу',
        'Өтініш',
        'Өңірдің 98 347 км² аумағында электр энергиясын сенімді беру және тарату.',
    ):
        assert kazakh_text in rendered


def test_kazakh_pages_do_not_keep_known_russian_fragments():
    set_locale('kk')
    rendered = '\n'.join(
        render_page(slug)
        for slug in ('docs', 'home', 'lists', 'pd_byt_potr', 'tu', 'vacancy')
    )

    for russian_text in (
        'Перейти в Әділет',
        'Смотреть перечень документов',
        'Опубликован в номере газеты',
        'Карагандинская региональная энергетическая компания',
        'Правоустанавливающие документы на объект',
        'Топографическая съемка',
        'Управление автомобильным краном',
    ):
        assert russian_text not in rendered
