# -*- coding: utf-8 -*-
"""
Шаблоны панели мониторинга посещаемости веб-портала ТОО «КРЭК» (/admin/stats).
Реализует эстетичный HeroUI дашборд с KPI-карточками, SVG-графиками динамики,
топом популярных страниц, распределением мобильных/ПК устройств и лентой визитов.
"""

import html
from typing import Any, Dict, Optional

from templates.admin_cms_views import _admin_nav_bar
from templates.icons import icon


def render_admin_stats_dashboard(
    stats: Dict[str, Any],
    csrf_token: str = '',
    username: str = 'admin',
    message: Optional[str] = None,
    error: Optional[str] = None
) -> str:
    """Генерирует главный дашборд посещаемости сайта для администратора."""
    msg_html = f'<div class="msg-box" style="background:#ecfdf5;color:#065f46;border:1.5px solid #a7f3d0;padding:12px 18px;border-radius:10px;margin-bottom:20px;font-weight:600;display:flex;align-items:center;gap:10px;">{icon("check_circle", 18, "#059669")} {html.escape(message)}</div>' if message else ''
    err_html = f'<div class="msg-box" style="background:#fff1f2;color:#9f1239;border:1.5px solid #fecdd3;padding:12px 18px;border-radius:10px;margin-bottom:20px;font-weight:600;display:flex;align-items:center;gap:10px;">{icon("alert_triangle", 18, "#e11d48")} {html.escape(error)}</div>' if error else ''

    # Значения KPI
    u_today = stats.get('unique_today', 0)
    v_today = stats.get('views_today', 0)
    u_yesterday = stats.get('unique_yesterday', 0)
    v_yesterday = stats.get('views_yesterday', 0)
    u_week = stats.get('unique_week', 0)
    v_week = stats.get('views_week', 0)
    u_month = stats.get('unique_month', 0)
    v_month = stats.get('views_month', 0)
    mob_pct = stats.get('mobile_share_pct', 0.0)
    bot_today = stats.get('bot_views_today', 0)

    # 1. Построение SVG-графика динамики по дням
    daily_trend = stats.get('daily_trend', [])
    chart_bars_html = []
    max_views = max([d.get('views', 0) for d in daily_trend] + [1])

    chart_width = 860
    chart_height = 180
    num_days = len(daily_trend)
    if num_days > 0:
        bar_gap = 10
        total_gaps = (num_days + 1) * bar_gap
        bar_width = max(16, int((chart_width - total_gaps) / num_days))

        for idx, item in enumerate(daily_trend):
            v_val = item.get('views', 0)
            u_val = item.get('visitors', 0)
            lbl = html.escape(item.get('label', ''))
            bar_h = max(4, int((v_val / max_views) * (chart_height - 40))) if max_views > 0 else 4
            x = bar_gap + idx * (bar_width + bar_gap)
            y = (chart_height - 30) - bar_h

            # Высота для уникальных посетителей
            u_bar_h = max(2, int((u_val / max_views) * (chart_height - 40))) if max_views > 0 else 2
            u_y = (chart_height - 30) - u_bar_h

            chart_bars_html.append(f'''
            <g class="chart-group" tabindex="0">
                <title>{item.get("date")}: {u_val} уникальных посетителей, {v_val} просмотров</title>
                <!-- Общие просмотры -->
                <rect x="{x}" y="{y}" width="{bar_width}" height="{bar_h}" rx="4" fill="url(#blueGrad)" opacity="0.85">
                    <animate attributeName="height" from="0" to="{bar_h}" dur="0.5s" fill="freeze" />
                </rect>
                <!-- Уникальные посетители -->
                <rect x="{x + 2}" y="{u_y}" width="{max(4, bar_width - 4)}" height="{u_bar_h}" rx="3" fill="#38bdf8">
                    <animate attributeName="height" from="0" to="{u_bar_h}" dur="0.6s" fill="freeze" />
                </rect>
                <!-- Подпись дня -->
                <text x="{x + bar_width/2}" y="{chart_height - 10}" text-anchor="middle" font-size="11" fill="#64748b" font-family="'Inter',sans-serif">{lbl}</text>
                <!-- Число над столбцом -->
                <text x="{x + bar_width/2}" y="{max(14, y - 6)}" text-anchor="middle" font-size="10" font-weight="600" fill="#1e293b" font-family="'Inter',sans-serif">{v_val if v_val > 0 else ''}</text>
            </g>
            ''')

    chart_svg = f'''
    <div style="width:100%;overflow-x:auto;padding-bottom:8px;">
        <svg viewBox="0 0 {chart_width} {chart_height}" width="100%" height="{chart_height}" style="min-width:650px;display:block;">
            <defs>
                <linearGradient id="blueGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                    <stop offset="0%" stop-color="#2563eb" />
                    <stop offset="100%" stop-color="#3b82f6" />
                </linearGradient>
            </defs>
            <!-- Фоновая сетка -->
            <line x1="0" y1="{chart_height - 30}" x2="{chart_width}" y2="{chart_height - 30}" stroke="#e2e8f0" stroke-width="1.5" />
            <line x1="0" y1="{(chart_height - 30) // 2}" x2="{chart_width}" y2="{(chart_height - 30) // 2}" stroke="#f1f5f9" stroke-dasharray="4 4" />
            {''.join(chart_bars_html)}
        </svg>
    </div>
    ''' if daily_trend else '<div style="padding:40px;text-align:center;color:#64748b;">Нет накопленных данных за выбранный период</div>'

    # 2. Популярные страницы
    top_pages = stats.get('top_pages', [])
    top_pages_rows = []
    if top_pages:
        for idx, page in enumerate(top_pages, 1):
            p_path = html.escape(page.get('path', '/'))
            p_views = page.get('views', 0)
            p_visitors = page.get('visitors', 0)
            p_pct = page.get('pct', 0.0)

            # Названия страниц для удобства
            title_alias = {
                '/': 'Главная страница',
                '/search': 'Поиск квитанций',
                '/kvit/': 'Сервис квитанций',
                '/tu': 'Технические условия',
                '/tarif': 'Тарифы и нормы',
                '/appeals': 'Подача обращений граждан',
                '/contacts': 'Контакты и реквизиты',
                '/zakupki': 'Закупки и тендеры',
                '/notices': 'Объявления потребителям',
                '/reports': 'Финансовая отчетность',
                '/history': 'История компании',
                '/leadership': 'Руководство',
                '/vacancies': 'Вакансии компании',
            }.get(p_path, '')

            alias_badge = f'<span style="font-size:12px;color:#64748b;font-weight:400;margin-left:6px;">({title_alias})</span>' if title_alias else ''

            top_pages_rows.append(f'''
            <tr style="border-bottom:1px solid #f1f5f9;">
                <td style="padding:10px 14px;font-weight:600;color:#64748b;width:30px;">#{idx}</td>
                <td style="padding:10px 14px;">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <a href="{p_path}" target="_blank" style="color:#2563eb;text-decoration:none;font-weight:600;font-size:13.5px;" title="Открыть страницу">
                            <code>{p_path}</code>
                        </a>
                        {alias_badge}
                    </div>
                    <div style="background:#f1f5f9;height:5px;border-radius:3px;margin-top:6px;overflow:hidden;">
                        <div style="background:#3b82f6;height:100%;width:{min(100, max(3, int(p_pct)))}%;border-radius:3px;"></div>
                    </div>
                </td>
                <td style="padding:10px 14px;text-align:right;font-weight:700;color:#1e293b;font-size:14px;">{p_views:,}</td>
                <td style="padding:10px 14px;text-align:right;color:#64748b;font-size:13.5px;">{p_visitors:,}</td>
                <td style="padding:10px 14px;text-align:right;font-weight:600;color:#2563eb;font-size:13px;">{p_pct}%</td>
            </tr>
            ''')
    else:
        top_pages_rows.append('<tr><td colspan="5" style="padding:24px;text-align:center;color:#64748b;">Данные пока не сформированы</td></tr>')

    # 3. Распределение устройств
    devices = stats.get('device_stats', {})
    d_mob = devices.get('mobile', 0)
    d_desk = devices.get('desktop', 0)
    d_tab = devices.get('tablet', 0)
    d_total = d_mob + d_desk + d_tab
    mob_pct_calc = round((d_mob / d_total * 100), 1) if d_total > 0 else 0.0
    desk_pct_calc = round((d_desk / d_total * 100), 1) if d_total > 0 else 0.0
    tab_pct_calc = round((d_tab / d_total * 100), 1) if d_total > 0 else 0.0

    # 4. Браузеры
    browser_stats = stats.get('browser_stats', [])
    browser_rows = []
    total_br_views = sum(b.get('count', 0) for b in browser_stats) or 1
    for b_item in browser_stats:
        b_name = html.escape(b_item.get('browser', 'Other'))
        b_cnt = b_item.get('count', 0)
        b_pct = round((b_cnt / total_br_views) * 100, 1)
        browser_rows.append(f'''
        <div style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-bottom:1px dashed #f1f5f9;font-size:13px;">
            <span style="font-weight:600;color:#334155;">{b_name}</span>
            <div style="display:flex;align-items:center;gap:10px;">
                <span style="color:#64748b;">{b_cnt:,}</span>
                <span style="background:#eff6ff;color:#2563eb;padding:2px 8px;border-radius:9999px;font-weight:600;font-size:11.5px;min-width:44px;text-align:center;">{b_pct}%</span>
            </div>
        </div>
        ''')

    # 5. Последние визиты
    recent_visits = stats.get('recent_visits', [])
    recent_rows = []
    if recent_visits:
        for rv in recent_visits:
            rv_time = rv.get('time_str', '')
            rv_path = html.escape(rv.get('path', ''))
            rv_ip = html.escape(rv.get('ip_masked', ''))
            rv_dev = html.escape(rv.get('device_type', 'desktop'))
            rv_browser = html.escape(rv.get('browser', 'Other'))
            rv_is_bot = rv.get('is_bot', False)

            if rv_is_bot:
                badge = '<span style="background:#fef2f2;color:#ef4444;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;">Робот / Бот</span>'
            elif rv_dev == 'mobile':
                badge = '<span style="background:#f0fdf4;color:#16a34a;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;">Смартфон</span>'
            else:
                badge = '<span style="background:#eff6ff;color:#2563eb;padding:2px 8px;border-radius:6px;font-size:11px;font-weight:600;">ПК</span>'

            recent_rows.append(f'''
            <tr style="border-bottom:1px solid #f8fafc;font-size:13px;">
                <td style="padding:8px 12px;color:#64748b;font-family:Consolas,monospace;">{rv_time}</td>
                <td style="padding:8px 12px;font-weight:600;color:#1e293b;"><code>{rv_path}</code></td>
                <td style="padding:8px 12px;color:#64748b;font-family:Consolas,monospace;">{rv_ip}</td>
                <td style="padding:8px 12px;">{badge}</td>
                <td style="padding:8px 12px;color:#475569;">{rv_browser}</td>
            </tr>
            ''')
    else:
        recent_rows.append('<tr><td colspan="5" style="padding:20px;text-align:center;color:#64748b;">Ожидание первых визитов...</td></tr>')

    return f'''
    <div class="card" style="max-width:1160px;margin:24px auto;">
        {_admin_nav_bar('stats', role='admin', username=username)}

        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:14px;">
            <div>
                <h1 style="font-size:22px;color:#1e293b;margin:0 0 4px;display:flex;align-items:center;gap:8px;">
                    {icon('trending_up', 22, '#2563eb')} Статистика посещаемости портала
                </h1>
                <p class="subtitle" style="margin:0;">Оперативные данные об уникальных посетителях, просмотрах страниц, географии и устройствах потребителей.</p>
            </div>
            <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
                <form action="/admin/stats/import-nginx" method="post" style="margin:0;" onsubmit="return confirm('Импортировать исторические логи из веб-сервера Nginx? Это может занять несколько секунд.');">
                    <input type="hidden" name="csrf_token" value="{csrf_token}">
                    <button type="submit" class="btn btn-outline btn-sm" style="display:inline-flex;align-items:center;gap:6px;" title="Синхронизировать данные из /var/log/nginx/access.log">
                        {icon('refresh', 14, '#2563eb')} Импорт из Nginx
                    </button>
                </form>
                <a href="/admin/stats" class="btn btn-sm" style="display:inline-flex;align-items:center;gap:6px;">
                    {icon('refresh', 14, '#fff')} Обновить
                </a>
            </div>
        </div>

        {msg_html}
        {err_html}

        <!-- СЕТКА KPI КАРТОЧЕК -->
        <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(170px, 1fr));gap:14px;margin-bottom:24px;">
            <!-- Сегодня -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#eff6ff;color:#2563eb;display:flex;align-items:center;justify-content:center;">
                    {icon('users', 18, '#2563eb')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Сегодня</span>
                <div style="font-size:26px;font-weight:800;color:#1e293b;margin:6px 0 2px;">{u_today:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_today:,} просмотров</div>
            </div>

            <!-- Вчера -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f1f5f9;color:#475569;display:flex;align-items:center;justify-content:center;">
                    {icon('calendar', 18, '#475569')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Вчера</span>
                <div style="font-size:26px;font-weight:800;color:#1e293b;margin:6px 0 2px;">{u_yesterday:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_yesterday:,} просмотров</div>
            </div>

            <!-- За 7 дней -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f0fdf4;color:#16a34a;display:flex;align-items:center;justify-content:center;">
                    {icon('trending_up', 18, '#16a34a')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">За 7 дней</span>
                <div style="font-size:26px;font-weight:800;color:#16a34a;margin:6px 0 2px;">{u_week:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_week:,} просмотров</div>
            </div>

            <!-- За месяц (30 дней) -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#faf5ff;color:#9333ea;display:flex;align-items:center;justify-content:center;">
                    {icon('bar_chart', 18, '#9333ea')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">За 30 дней</span>
                <div style="font-size:26px;font-weight:800;color:#9333ea;margin:6px 0 2px;">{u_month:,}</div>
                <div style="font-size:12.5px;color:#64748b;">{v_month:,} просмотров</div>
            </div>

            <!-- Смартфоны -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#fff7ed;color:#ea580c;display:flex;align-items:center;justify-content:center;">
                    {icon('phone', 18, '#ea580c')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Мобильные</span>
                <div style="font-size:26px;font-weight:800;color:#ea580c;margin:6px 0 2px;">{mob_pct}%</div>
                <div style="font-size:12.5px;color:#64748b;">доля смартфонов</div>
            </div>

            <!-- Боты за сегодня -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;padding:16px;box-shadow:0 1px 3px rgba(0,0,0,0.04);position:relative;overflow:hidden;">
                <div style="position:absolute;top:12px;right:12px;width:34px;height:34px;border-radius:8px;background:#f8fafc;color:#64748b;display:flex;align-items:center;justify-content:center;">
                    {icon('shield_check', 18, '#64748b')}
                </div>
                <span style="font-size:12px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">Роботы/Боты</span>
                <div style="font-size:26px;font-weight:800;color:#64748b;margin:6px 0 2px;">{bot_today:,}</div>
                <div style="font-size:12.5px;color:#64748b;">отсеяно за сегодня</div>
            </div>
        </div>

        <!-- ГРАФИК ДИНАМИКИ ПО ДНЯМ -->
        <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:22px;margin-bottom:24px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:10px;">
                <div>
                    <h3 style="margin:0 0 4px;font-size:16px;color:#1e293b;">Динамика визитов по дням</h3>
                    <p style="margin:0;font-size:12.5px;color:#64748b;">Синий столбец — общее число просмотров страниц, голубой — уникальные посетители.</p>
                </div>
                <div style="display:flex;gap:14px;align-items:center;font-size:12px;color:#64748b;">
                    <span style="display:inline-flex;align-items:center;gap:5px;">
                        <span style="width:10px;height:10px;background:#2563eb;border-radius:2px;display:inline-block;"></span> Просмотры
                    </span>
                    <span style="display:inline-flex;align-items:center;gap:5px;">
                        <span style="width:10px;height:10px;background:#38bdf8;border-radius:2px;display:inline-block;"></span> Уникальные посетители
                    </span>
                </div>
            </div>

            {chart_svg}
        </div>

        <!-- ДВЕ КОЛОНКИ: ТОП СТРАНИЦ И УСТРОЙСТВА/БРАУЗЕРЫ -->
        <div style="display:grid;grid-template-columns:2fr 1fr;gap:20px;margin-bottom:24px;" class="stats-two-cols">
            <!-- ТОП-10 СТРАНИЦ -->
            <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                <h3 style="margin:0 0 14px;font-size:16px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                    {icon('list', 16, '#2563eb')} Популярные страницы (Топ-10)
                </h3>
                <div style="overflow-x:auto;">
                    <table style="width:100%;border-collapse:collapse;font-size:13.5px;">
                        <thead>
                            <tr style="background:#f8fafc;border-bottom:1.5px solid #e2e8f0;color:#64748b;text-align:left;font-size:12px;text-transform:uppercase;">
                                <th style="padding:8px 14px;">#</th>
                                <th style="padding:8px 14px;">Страница</th>
                                <th style="padding:8px 14px;text-align:right;">Просмотры</th>
                                <th style="padding:8px 14px;text-align:right;">Уникальные</th>
                                <th style="padding:8px 14px;text-align:right;">Доля</th>
                            </tr>
                        </thead>
                        <tbody>
                            {''.join(top_pages_rows)}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- УСТРОЙСТВА И БРАУЗЕРЫ -->
            <div style="display:flex;flex-direction:column;gap:18px;">
                <!-- Устройства -->
                <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                    <h3 style="margin:0 0 14px;font-size:15px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                        {icon('phone', 16, '#ea580c')} Типы устройств
                    </h3>

                    <div style="margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Смартфоны</span>
                            <span style="color:#ea580c;font-weight:700;">{mob_pct_calc}% ({d_mob:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#ea580c;height:100%;width:{mob_pct_calc}%;"></div>
                        </div>
                    </div>

                    <div style="margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Компьютеры и ноутбуки</span>
                            <span style="color:#2563eb;font-weight:700;">{desk_pct_calc}% ({d_desk:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#2563eb;height:100%;width:{desk_pct_calc}%;"></div>
                        </div>
                    </div>

                    <div>
                        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px;">
                            <span style="color:#334155;font-weight:600;">Планшеты</span>
                            <span style="color:#10b981;font-weight:700;">{tab_pct_calc}% ({d_tab:,})</span>
                        </div>
                        <div style="background:#f1f5f9;height:7px;border-radius:4px;overflow:hidden;">
                            <div style="background:#10b981;height:100%;width:{tab_pct_calc}%;"></div>
                        </div>
                    </div>
                </div>

                <!-- Браузеры -->
                <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
                    <h3 style="margin:0 0 10px;font-size:15px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                        {icon('code', 16, '#2563eb')} Популярные браузеры
                    </h3>
                    <div style="display:flex;flex-direction:column;">
                        {''.join(browser_rows) if browser_rows else '<div style="color:#64748b;font-size:13px;padding:8px 0;">Данные накапливаются</div>'}
                    </div>
                </div>
            </div>
        </div>

        <!-- ПОСЛЕДНИЕ ВИЗИТЫ В РЕАЛЬНОМ ВРЕМЕНИ -->
        <div style="background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,0.03);">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
                <h3 style="margin:0;font-size:16px;color:#1e293b;display:flex;align-items:center;gap:8px;">
                    {icon('clock', 16, '#2563eb')} Последние визиты в реальном времени
                </h3>
                <span style="font-size:12px;color:#64748b;">Отображаются последние 15 переходов с защитой IP-адресов</span>
            </div>

            <div style="overflow-x:auto;">
                <table style="width:100%;border-collapse:collapse;font-size:13px;">
                    <thead>
                        <tr style="background:#f8fafc;border-bottom:1.5px solid #e2e8f0;color:#64748b;text-align:left;font-size:11.5px;text-transform:uppercase;">
                            <th style="padding:8px 12px;">Время</th>
                            <th style="padding:8px 12px;">Страница</th>
                            <th style="padding:8px 12px;">Хэш IP</th>
                            <th style="padding:8px 12px;">Тип</th>
                            <th style="padding:8px 12px;">Браузер</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(recent_rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    '''
