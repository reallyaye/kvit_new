import html
import os

from templates.i18n import translate_html
from templates.locale import get_locale, localized_path
from templates.portal_cookies import (
    render_cookie_consent_html,
    render_portal_scripts,
)
from templates.portal_footer import render_portal_footer
from templates.portal_header import render_admin_bar, render_portal_header


def _asset_v(rel_path: str) -> str:
    """Автоматический cache-buster: возвращает timestamp изменения файла."""
    try:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', rel_path.lstrip('/'))
        return str(int(os.path.getmtime(full_path)))
    except Exception:
        return '20260903'


def portal_layout(
    content: str,
    title: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания",
    description: str = "ТОО КРЭК — Карагандинская Региональная Энергетическая Компания. Передача и распределение электроэнергии, электронные квитанции, технические условия.",
    active_nav: str = "home",
    is_admin: bool = False,
    current_slug: str = ""
) -> str:
    """Генерирует базовый HTML-макет информационного портала ТОО «КРЭК»."""
    escaped_title = html.escape(title)
    escaped_desc = html.escape(description)
    style_v = _asset_v('css/style.css')
    heroui_v = _asset_v('css/heroui.css')
    cookie_v = _asset_v('css/cookie_consent.css')
    sw_v = _asset_v('sw.js')
    locale = get_locale()
    canonical_source = '/' if current_slug in ('home', '', None) else f'/{current_slug}'
    canonical_path = localized_path(canonical_source, locale)
    ru_path = localized_path(canonical_source, 'ru')
    kk_path = localized_path(canonical_source, 'kk')
    html_lang = 'kk' if locale == 'kk' else 'ru'

    admin_bar_html = render_admin_bar(is_admin, current_slug)
    header_html = render_portal_header(active_nav, locale, ru_path, kk_path)
    footer_html = render_portal_footer()
    cookie_html = render_cookie_consent_html()
    scripts_html = render_portal_scripts(current_slug)

    return translate_html(f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8" />
<meta http-equiv="X-UA-Compatible" content="IE=edge,chrome=1">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
<meta name="theme-color" content="#0f172a">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="description" content="{escaped_desc}" />
<meta name="robots" content="index,follow">
<link rel="canonical" href="https://krec.kz{canonical_path}">
<link rel="alternate" hreflang="ru" href="https://krec.kz{ru_path}">
<link rel="alternate" hreflang="kk" href="https://krec.kz{kk_path}">
<link rel="alternate" hreflang="x-default" href="https://krec.kz{ru_path}">
<meta property="og:title" content="{escaped_title}">
<meta property="og:description" content="{escaped_desc}">
<meta property="og:url" content="https://krec.kz{canonical_path}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="ТОО «КРЭК»">
<meta property="og:image" content="https://krec.kz/images/logo.png">
<title>{escaped_title}</title>
<link rel="manifest" href="/manifest.json">
<link rel="stylesheet" href="/css/style.css?v={style_v}" type="text/css" />
<link rel="stylesheet" href="/css/heroui.css?v={heroui_v}" type="text/css" />
<link rel="stylesheet" href="/css/cookie_consent.css?v={cookie_v}" type="text/css" />
<link rel="shortcut icon" href="/favicon.ico?v={style_v}" type="image/vnd.microsoft.icon">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "Organization",
  "name": "ТОО «Карагандинская Региональная Энергетическая Компания»",
  "alternateName": "ТОО «КРЭК»",
  "url": "https://krec.kz",
  "logo": "https://krec.kz/images/logo.png",
  "telephone": "+7-7212-90-03-50",
  "email": "info@krec.kz",
  "taxID": "031140001297",
  "address": {{
    "@type": "PostalAddress",
    "streetAddress": "108 уч. квартал, строение 7",
    "addressLocality": "Караганда",
    "addressRegion": "Карагандинская область",
    "postalCode": "100000",
    "addressCountry": "KZ"
  }}
}}
</script>
<script>
if ('serviceWorker' in navigator) {{
    window.addEventListener('load', function() {{
        navigator.serviceWorker.register('/sw.js?v={sw_v}').then(function(reg) {{
            reg.update();
        }}).catch(function() {{}});
    }});
    navigator.serviceWorker.addEventListener('controllerchange', function() {{
        if (!window._swReloaded) {{
            window._swReloaded = true;
            window.location.reload();
        }}
    }});
}}
</script>
</head>
<body>
{admin_bar_html}

<div id="wrap">
{header_html}

<div class="mobile-nav-backdrop" id="mobileNavBackdrop" onclick="closeMobileNav()"></div>

<!-- ===== ОСНОВНОЙ КОНТЕНТ ===== -->
<div class="content-container">
{content}
</div>

{footer_html}

</div><!-- /#wrap -->

{cookie_html}
{scripts_html}
</body>
</html>""")
