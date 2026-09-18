def render_cookie_consent_html() -> str:
    """Рендерит HTML-разметку баннера согласия и модального окна настройки cookies."""
    return '''
<!-- ===== КОРПОРАТИВНЫЙ БАННЕР СОГЛАСИЯ НА COOKIES ===== -->
<div id="krecCookieBanner" class="krec-cookie-banner" style="display:none;" role="region" aria-label="Уведомление о файлах cookie">
    <div class="krec-cookie-container">
        <div class="krec-cookie-text">
            <div class="krec-cookie-title">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#38bdf8" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                <span>Файлы cookie и конфиденциальность данных</span>
            </div>
            <p>Мы используем обязательные cookies для работы портала и аналитические cookies (Яндекс.Метрика) для анализа посещаемости сайта. На страницах поиска квитанций и обращений запись экрана и перехват ввода клавиатуры отключены. Вы можете принять все или продолжить только с техническими cookies. Подробнее: <a href="/privacy" style="color:#60a5fa;text-decoration:underline;">Политика сбора и обработки данных</a>.</p>
        </div>
        <div class="krec-cookie-actions">
            <button type="button" class="krec-cookie-btn krec-cookie-btn-primary" onclick="krecAcceptAllCookies()">Принять все</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-outline" onclick="krecRejectCookies()">Только необходимые</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-subtle" onclick="krecOpenCookieModal()">Настроить</button>
        </div>
    </div>
</div>

<!-- ===== МОДАЛЬНОЕ ОКНО НАСТРОЙКИ COOKIES ===== -->
<div id="krecCookieModal" class="krec-cookie-modal-backdrop" style="display:none;" onclick="if(event.target===this)krecCloseCookieModal()">
    <div class="krec-cookie-modal-content" role="dialog" aria-modal="true" aria-labelledby="krecCookieModalTitle">
        <div class="krec-cookie-modal-header">
            <h3 id="krecCookieModalTitle">Настройки файлов cookie и аналитики</h3>
            <button type="button" class="krec-cookie-close-btn" onclick="krecCloseCookieModal()" aria-label="Закрыть">&times;</button>
        </div>
        <div class="krec-cookie-modal-body">
            <p style="margin-bottom:16px; font-size:13.5px; color:#64748b; line-height:1.5;">В соответствии с Законом Республики Казахстан «О персональных данных и их защите» вы можете настроить категории используемых файлов cookie.</p>

            <div class="krec-cookie-option">
                <div class="krec-cookie-opt-header">
                    <div>
                        <strong>Технические (необходимые) cookies</strong>
                        <span class="krec-badge-req">Всегда активны</span>
                    </div>
                </div>
                <p>Обеспечивают базовое функционирование сайта: выбор языка, сессии, предотвращение атак. Без них сайт не может работать.</p>
            </div>

            <div class="krec-cookie-option">
                <div class="krec-cookie-opt-header">
                    <div>
                        <strong>Аналитические cookies (Яндекс.Метрика)</strong>
                    </div>
                    <label class="krec-switch">
                        <input type="checkbox" id="krecConsentAnalyticsCheckbox">
                        <span class="krec-slider"></span>
                    </label>
                </div>
                <p>Сбор агрегированной обезличенной статистики посещаемости. На страницах поиска квитанций и формы обращений Webvisor (запись действий на экране) отключён принудительно.</p>
            </div>
        </div>
        <div class="krec-cookie-modal-footer">
            <button type="button" class="krec-cookie-btn krec-cookie-btn-outline" onclick="krecCloseCookieModal()">Отмена</button>
            <button type="button" class="krec-cookie-btn krec-cookie-btn-primary" onclick="krecSaveCookieSettings()">Сохранить выбор</button>
        </div>
    </div>
</div>
'''


def render_portal_scripts(current_slug: str = "") -> str:
    """Рендерит клиентские скрипты навигации, переключения языка и защиты персональных данных."""
    slug_clean = (current_slug or "").lower().replace('"', '\\"')
    return f'''
<script>
function toggleMobileNav(e) {{
    if (e) {{
        e.preventDefault();
        e.stopPropagation();
    }}
    const nav = document.getElementById('portalNav');
    const toggle = document.getElementById('mobileNavToggle');
    const backdrop = document.getElementById('mobileNavBackdrop');
    const isOpen = nav.classList.toggle('is-open');
    if (toggle) {{
        toggle.classList.toggle('active', isOpen);
        toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    }}
    if (backdrop) {{
        backdrop.classList.toggle('is-visible', isOpen);
    }}
    document.body.classList.toggle('mobile-menu-active', isOpen);
}}

function closeMobileNav() {{
    const nav = document.getElementById('portalNav');
    const toggle = document.getElementById('mobileNavToggle');
    const backdrop = document.getElementById('mobileNavBackdrop');
    if (nav) nav.classList.remove('is-open');
    if (toggle) {{
        toggle.classList.remove('active');
        toggle.setAttribute('aria-expanded', 'false');
    }}
    if (backdrop) backdrop.classList.remove('is-visible');
    document.body.classList.remove('mobile-menu-active');
}}

function switchAnnouncementLang(lang) {{
    var ruCard = document.getElementById('announcementRu');
    var kzCard = document.getElementById('announcementKz');
    var btnRu = document.getElementById('btnAnnounceRu');
    var btnKz = document.getElementById('btnAnnounceKz');

    if (lang === 'kz') {{
        if (ruCard) ruCard.style.display = 'none';
        if (kzCard) kzCard.style.display = 'block';
        if (btnRu) btnRu.classList.remove('active');
        if (btnKz) btnKz.classList.add('active');
    }} else {{
        if (kzCard) kzCard.style.display = 'none';
        if (ruCard) ruCard.style.display = 'block';
        if (btnKz) btnKz.classList.remove('active');
        if (btnRu) btnRu.classList.add('active');
    }}
    try {{
        localStorage.setItem('krec_announce_lang', lang);
    }} catch(e) {{}}
}}

function switchPortalLang(lang) {{
    var ruBtn = document.getElementById('btnLangRu');
    var kzBtn = document.getElementById('btnLangKz');
    if (ruBtn && kzBtn) {{
        if (lang === 'kz') {{
            ruBtn.classList.remove('active');
            kzBtn.classList.add('active');
        }} else {{
            kzBtn.classList.remove('active');
            ruBtn.classList.add('active');
        }}
    }}
    try {{
        localStorage.setItem('krec_portal_lang', lang);
        document.cookie = 'krec_lang=' + lang + '; path=/; max-age=31536000';
    }} catch(e) {{}}

    if (typeof switchAnnouncementLang === 'function') {{
        switchAnnouncementLang(lang);
    }}
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'Escape') {{
        closeMobileNav();
    }}
}});

window.addEventListener('resize', function() {{
    if (window.innerWidth > 1080) {{
        closeMobileNav();
    }}
}});

document.addEventListener('DOMContentLoaded', function() {{
    try {{
        var saved = localStorage.getItem('krec_portal_lang') || localStorage.getItem('krec_announce_lang');
        if (saved === 'kz') {{
            switchPortalLang('kz');
        }}
    }} catch(e) {{}}
}});

// ===== COOKIE CONSENT & METRIKA SHIELD =====
(function() {{
    var sensitiveSlugs = ['appeals', 'search', 'kvit', 'receipt'];
    var currentSlug = '{slug_clean}';
    var isSensitive = sensitiveSlugs.indexOf(currentSlug) !== -1;

    function getStoredConsent() {{
        try {{
            var raw = localStorage.getItem('krec_cookie_consent');
            if (raw) return JSON.parse(raw);
        }} catch(e) {{}}
        return null;
    }}

    function purgeTrackingData() {{
        var host = window.location.hostname;
        var domains = ['', '.' + host, host];
        var parts = host.split('.');
        if (parts.length >= 2) {{
            domains.push('.' + parts.slice(-2).join('.'));
        }}
        try {{
            var cookies = document.cookie.split(';');
            for (var i = 0; i < cookies.length; i++) {{
                var c = cookies[i].trim();
                var eq = c.indexOf('=');
                var name = eq > -1 ? c.substring(0, eq).trim() : c;
                if (name.indexOf('_ym') === 0 || name.indexOf('yabs') === 0 || name === 'krec_analytics') {{
                    for (var d = 0; d < domains.length; d++) {{
                        var dom = domains[d];
                        var domAttr = dom ? '; domain=' + dom : '';
                        document.cookie = name + '=; path=/; max-age=0; expires=Thu, 01 Jan 1970 00:00:00 GMT' + domAttr;
                    }}
                }}
            }}
            document.cookie = 'krec_analytics=0; path=/; max-age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
        }} catch(e) {{}}

        try {{
            var removeKeys = [];
            for (var k = 0; k < localStorage.length; k++) {{
                var key = localStorage.key(k);
                if (key && (key.indexOf('_ym') === 0 || key.indexOf('yabs') === 0 || key.indexOf('metrika') !== -1)) {{
                    removeKeys.push(key);
                }}
            }}
            for (var j = 0; j < removeKeys.length; j++) {{
                localStorage.removeItem(removeKeys[j]);
            }}
        }} catch(e) {{}}

        try {{
            var sRemoveKeys = [];
            for (var sk = 0; sk < sessionStorage.length; sk++) {{
                var sKey = sessionStorage.key(sk);
                if (sKey && (sKey.indexOf('_ym') === 0 || sKey.indexOf('yabs') === 0 || sKey.indexOf('metrika') !== -1)) {{
                    sRemoveKeys.push(sKey);
                }}
            }}
            for (var sj = 0; sj < sRemoveKeys.length; sj++) {{
                sessionStorage.removeItem(sRemoveKeys[sj]);
            }}
        }} catch(e) {{}}

        if (window.yaCounter51197381) {{
            try {{
                if (typeof window.yaCounter51197381.destructor === 'function') {{
                    window.yaCounter51197381.destructor();
                }}
            }} catch(e) {{}}
            window.yaCounter51197381 = null;
        }}
        window._krecMetrikaInitialized = false;
    }}

    function storeConsent(allowAnalytics) {{
        var val = {{
            analytics: !!allowAnalytics,
            necessary: true,
            timestamp: new Date().toISOString(),
            version: 'v1.0-2026-kz'
        }};
        try {{
            localStorage.setItem('krec_cookie_consent', JSON.stringify(val));
            if (allowAnalytics) {{
                document.cookie = 'krec_analytics=1; path=/; max-age=31536000; SameSite=Lax' + (location.protocol === 'https:' ? '; Secure' : '');
            }} else {{
                purgeTrackingData();
            }}
        }} catch(e) {{}}
        return val;
    }}

    function loadYandexMetrika(enableWebvisor) {{
        if (window.yaCounter51197381 || window._krecMetrikaInitialized) return;
        window._krecMetrikaInitialized = true;

        (function (d, w, c) {{
            (w[c] = w[c] || []).push(function() {{
                try {{
                    w.yaCounter51197381 = new Ya.Metrika2({{
                        id: 51197381,
                        clickmap: !isSensitive,
                        trackLinks: !isSensitive,
                        accurateTrackBounce: true,
                        webvisor: enableWebvisor && !isSensitive
                    }});
                }} catch(e) {{ }}
            }});

            var n = d.getElementsByTagName("script")[0],
                s = d.createElement("script"),
                f = function () {{ n.parentNode.insertBefore(s, n); }};
            s.type = "text/javascript";
            s.async = true;
            s.src = "https://mc.yandex.ru/metrika/tag.js";

            if (w.opera == "[object Opera]") {{
                d.addEventListener("DOMContentLoaded", f, false);
            }} else {{ f(); }}
        }})(document, window, "yandex_metrika_callbacks2");
    }}

    window.krecAcceptAllCookies = function() {{
        storeConsent(true);
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
        loadYandexMetrika(true);
    }};

    window.krecRejectCookies = function() {{
        storeConsent(false);
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
    }};

    window.krecOpenCookieModal = function() {{
        var c = getStoredConsent();
        var chk = document.getElementById('krecConsentAnalyticsCheckbox');
        if (chk) chk.checked = !!(c && c.analytics);
        var modal = document.getElementById('krecCookieModal');
        if (modal) modal.style.display = 'flex';
    }};

    window.krecCloseCookieModal = function() {{
        var modal = document.getElementById('krecCookieModal');
        if (modal) modal.style.display = 'none';
    }};

    window.krecSaveCookieSettings = function() {{
        var chk = document.getElementById('krecConsentAnalyticsCheckbox');
        var allowed = chk ? chk.checked : false;
        storeConsent(allowed);
        krecCloseCookieModal();
        var b = document.getElementById('krecCookieBanner');
        if (b) b.style.display = 'none';
        if (allowed) {{
            loadYandexMetrika(true);
        }}
    }};

    document.addEventListener('DOMContentLoaded', function() {{
        var consent = getStoredConsent();
        if (!consent) {{
            var b = document.getElementById('krecCookieBanner');
            if (b) b.style.display = 'block';
        }} else if (consent.analytics) {{
            loadYandexMetrika(true);
        }}
    }});
}})();
</script>
'''
