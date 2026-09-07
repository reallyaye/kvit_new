import html
import urllib.parse
from datetime import datetime

from services.appeals import APPEAL_CATEGORIES, APPEAL_STATUSES
from templates.admin_cms_views import _admin_nav_bar
from templates.portal_layout import portal_layout


def render_appeals_page(is_admin=False):
    options = ''.join(
        f'<option value="{html.escape(key)}">{html.escape(label)}</option>'
        for key, label in APPEAL_CATEGORIES.items()
    )
    content = f'''
    <section class="appeals-page">
      <div class="appeals-intro"><h1>Официальный канал ТОО «КРЭК»</h1><p>Подача заявлений, вопросов, предложений и жалоб по вопросам электроснабжения, начислений и подключения к сетям.</p></div>
      <div class="appeals-grid">
        <div class="appeals-card appeals-form-card">
          <h2>Форма подачи обращения</h2>
          <p class="appeals-help">Все поля, отмеченные звёздочкой (*), обязательны. Обращение будет зарегистрировано с присвоением входящего номера.</p>
          <form id="appeal-form" action="/api/appeals" method="post" novalidate>
            <label>Категория обращения *<select name="category" required><option value="">Выберите тематику обращения…</option>{options}</select></label>
            <div class="appeals-fields">
              <label>ФИО заявителя (или наименование организации) *<input name="applicant_name" maxlength="255" autocomplete="name" required placeholder="Иванов Иван Иванович"></label>
              <label>Контактный телефон *<input name="phone" type="tel" maxlength="64" autocomplete="tel" required placeholder="+7 (___) ___-__-__"></label>
              <label>Адрес электронной почты (для ответа) *<input name="email" type="email" maxlength="254" autocomplete="email" required placeholder="example@mail.kz"></label>
              <label>Номер лицевого счёта (при наличии)<input name="account_number" maxlength="64" inputmode="numeric" placeholder="Например: 12345678"></label>
            </div>
            <label>Адрес объекта электроснабжения *<input name="service_address" maxlength="500" autocomplete="street-address" required placeholder="Район, населённый пункт, улица, дом, кв."></label>
            <label>Суть обращения *<textarea name="message" minlength="10" maxlength="5000" rows="6" required placeholder="Подробно опишите суть вопроса, дату происшествия или требуемые действия…"></textarea></label>
            <label class="appeals-consent"><input name="consent" type="checkbox" value="1" required><span>Даю согласие на обработку персональных данных в соответствии с законодательством Республики Казахстан *</span></label>
            <div class="appeals-honeypot" aria-hidden="true"><label>Не заполняйте это поле<input name="website" tabindex="-1" autocomplete="off"></label></div>
            <div id="appeal-result" class="appeals-result" role="status" aria-live="polite"></div>
            <button id="appeal-submit" class="appeals-submit" type="submit">Отправить обращение</button>
          </form>
        </div>
        <aside>
          <div class="appeals-card"><h3>Порядок рассмотрения</h3><ol class="appeals-steps">
            <li><strong>Регистрация обращения</strong><span>В течение 1 рабочего дня с присвоением входящего номера.</span></li>
            <li><strong>Срок рассмотрения</strong><span>До 15 календарных дней со дня поступления согласно законодательству РК.</span></li>
            <li><strong>Официальный ответ</strong><span>Направляется на указанную электронную почту заявителя.</span></li>
          </ol></div>
          <div class="appeals-card appeals-office"><h3>Канцелярия предприятия</h3><p>Письменное заявление можно подать лично:</p><p><strong>г. Караганда, 108 уч. квартал, строение 7</strong></p><p>Канцелярия: <strong>+7 (7212) 90-03-50</strong></p><small>Пн–Пт с 08:00 до 17:00 (обед 12:00–13:00)</small></div>
        </aside>
      </div>
    </section>
    <style>
      .appeals-page{{max-width:1120px;margin:0 auto;padding:16px 20px 54px;color:#172033}}.appeals-intro{{padding:0 0 28px;border-bottom:1px solid #dbe3ef;margin-bottom:32px}}.appeals-intro h1{{font-size:18px;margin:0 0 5px}}.appeals-intro p,.appeals-help,.appeals-card p,.appeals-card small{{color:#64748b}}.appeals-grid{{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:30px;align-items:start}}.appeals-card{{background:#fff;border:1px solid #d9e1ec;border-radius:15px;padding:28px 32px;box-shadow:0 3px 12px rgba(15,23,42,.04);margin-bottom:20px}}.appeals-card h2{{font-size:23px;margin:0 0 8px}}.appeals-card h3{{font-size:18px;margin:0 0 18px;padding-bottom:13px;border-bottom:1px solid #e5eaf1}}.appeals-help{{font-size:14px;line-height:1.55;margin:0 0 25px}}#appeal-form>label,.appeals-fields label{{display:flex;flex-direction:column;gap:8px;font-weight:600;font-size:14px;margin-bottom:20px}}.appeals-fields{{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}}#appeal-form input,#appeal-form select,#appeal-form textarea{{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:13px 14px;font:inherit;background:#fff;color:#172033}}#appeal-form input:focus,#appeal-form select:focus,#appeal-form textarea:focus{{outline:2px solid #bfdbfe;border-color:#2563eb}}.appeals-consent{{flex-direction:row!important;align-items:flex-start;gap:11px!important;font-weight:500!important}}.appeals-consent input{{width:auto!important;margin-top:3px}}.appeals-honeypot{{position:absolute!important;left:-10000px!important;width:1px;height:1px;overflow:hidden}}.appeals-submit{{border:0;border-radius:10px;background:#1367d1;color:#fff;font-weight:700;padding:14px 22px;cursor:pointer}}.appeals-submit:disabled{{opacity:.6;cursor:wait}}.appeals-result{{display:none;border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:14px}}.appeals-result.ok{{display:block;background:#ecfdf5;color:#166534;border:1px solid #bbf7d0}}.appeals-result.error{{display:block;background:#fef2f2;color:#991b1b;border:1px solid #fecaca}}.appeals-steps{{list-style:none;padding:0;margin:0;counter-reset:step}}.appeals-steps li{{counter-increment:step;position:relative;padding:0 0 24px 55px;min-height:35px}}.appeals-steps li:before{{content:counter(step);position:absolute;left:0;top:0;width:27px;height:27px;border-radius:50%;background:#eff6ff;color:#2563eb;display:grid;place-items:center;font-weight:700}}.appeals-steps strong,.appeals-steps span{{display:block}}.appeals-steps span{{color:#64748b;font-size:14px;line-height:1.55;margin-top:5px}}.appeals-office p{{font-size:14px;line-height:1.55}}@media(max-width:800px){{.appeals-grid{{grid-template-columns:1fr}}.appeals-fields{{grid-template-columns:1fr}}.appeals-card{{padding:22px 18px}}}}
    </style>
    <script>
    (() => {{
      const form=document.getElementById('appeal-form'),result=document.getElementById('appeal-result'),button=document.getElementById('appeal-submit');
      if(!form)return;
      form.addEventListener('submit',async(event)=>{{event.preventDefault();result.className='appeals-result';result.textContent='';if(!form.reportValidity())return;button.disabled=true;button.textContent='Отправляем…';
        try{{const response=await fetch(form.action,{{method:'POST',headers:{{'Accept':'application/json'}},body:new URLSearchParams(new FormData(form))}});const data=await response.json();if(!response.ok)throw new Error(data.message||'Не удалось отправить обращение.');const emailNote=data.confirmation_sent?' Подтверждение отправлено на вашу почту.':'';result.textContent=`Обращение зарегистрировано. Ваш номер: ${{data.registration_number}}.${{emailNote}}`;result.className='appeals-result ok';form.reset();}}
        catch(error){{result.textContent=error.message||'Произошла ошибка. Попробуйте ещё раз.';result.className='appeals-result error';}}
        finally{{button.disabled=false;button.textContent='Отправить обращение';}}
      }});
    }})();
    </script>'''
    return portal_layout(content=content, title='Подать обращение — ТОО «КРЭК»', active_nav='appeals', is_admin=is_admin, current_slug='appeals')


def _format_datetime(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime('%d.%m.%Y %H:%M')
    except (TypeError, ValueError, OSError):
        return '—'


def render_admin_appeals_list(data, stats, filters, csrf_token, message=None, error=None, username='admin'):
    del csrf_token
    alerts = (f'<div class="ok">{html.escape(message)}</div>' if message else '') + (f'<div class="err">{html.escape(error)}</div>' if error else '')
    cards = ''.join(f'<div class="appeal-stat"><small>{html.escape(label)}</small><strong>{stats.get(key, 0)}</strong></div>' for key, label in [('TOTAL', 'Всего'), ('NEW', 'Новые'), ('IN_REVIEW', 'На рассмотрении'), ('ANSWERED', 'Ответ направлен')])
    rows = []
    for appeal in data['items']:
        rows.append(f'''<tr><td><a href="/admin/appeals/view?id={appeal['id']}">{html.escape(appeal['registration_number'])}</a></td><td>{_format_datetime(appeal['submitted_at'])}</td><td>{html.escape(appeal['applicant_name'])}<br><small>{html.escape(appeal['email'])}</small></td><td>{html.escape(APPEAL_CATEGORIES.get(appeal['category'], appeal['category']))}</td><td><span class="tag">{html.escape(APPEAL_STATUSES.get(appeal['status'], appeal['status']))}</span></td></tr>''')
    rows_html = ''.join(rows) or '<tr><td colspan="5" class="appeal-empty">Обращения не найдены</td></tr>'
    status_options = '<option value="">Все статусы</option>' + ''.join(f'<option value="{key}"{" selected" if filters.get("status") == key else ""}>{html.escape(label)}</option>' for key, label in APPEAL_STATUSES.items())
    pagination = ''
    if data['pages'] > 1:
        links = []
        for page in range(1, data['pages'] + 1):
            params = {'status': filters.get('status', ''), 'search': filters.get('search', ''), 'page': page}
            links.append(f'<a class="btn btn-sm" href="/admin/appeals?{urllib.parse.urlencode(params)}">{page}</a>')
        pagination = '<div class="appeal-pagination">' + ''.join(links) + '</div>'
    return f'''{_admin_nav_bar('appeals', 'admin', username)}<div class="appeal-admin">{alerts}<h1>Обращения граждан</h1><p>Реестр обращений, поступивших через сайт</p><div class="appeal-stats">{cards}</div><form method="get" action="/admin/appeals" class="appeal-filter"><input class="input" name="search" value="{html.escape(filters.get('search', ''))}" placeholder="Номер, ФИО, email, телефон или лицевой счёт"><select class="input" name="status">{status_options}</select><button class="btn btn-primary" type="submit">Найти</button></form><div class="appeal-table"><table><thead><tr><th>Номер</th><th>Дата</th><th>Заявитель</th><th>Категория</th><th>Статус</th></tr></thead><tbody>{rows_html}</tbody></table></div>{pagination}</div><style>.appeal-admin{{max-width:1200px;margin:26px auto;padding:0 18px}}.appeal-admin>p{{color:#64748b}}.appeal-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}.appeal-stat{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px}}.appeal-stat small{{display:block;color:#64748b}}.appeal-stat strong{{display:block;font-size:25px;margin-top:4px}}.appeal-filter{{display:flex;gap:10px;background:#fff;border:1px solid #e2e8f0;padding:14px;border-radius:12px;margin-bottom:16px}}.appeal-filter input{{flex:1}}.appeal-table{{overflow:auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px}}.appeal-table table{{width:100%;border-collapse:collapse}}.appeal-table th,.appeal-table td{{padding:13px;text-align:left;border-bottom:1px solid #eef2f7;font-size:14px}}.appeal-table th{{color:#64748b;font-size:12px;text-transform:uppercase}}.appeal-table a{{font-weight:700;color:#2563eb}}.appeal-empty{{text-align:center!important;padding:35px!important;color:#64748b}}.appeal-pagination{{display:flex;gap:6px;margin-top:18px}}@media(max-width:700px){{.appeal-stats{{grid-template-columns:1fr 1fr}}.appeal-filter{{flex-direction:column}}}}</style>'''


def render_admin_appeal_detail(appeal, csrf_token, message=None, error=None, username='admin'):
    alerts = (f'<div class="ok">{html.escape(message)}</div>' if message else '') + (f'<div class="err">{html.escape(error)}</div>' if error else '')
    status_options = ''.join(f'<option value="{key}"{" selected" if appeal["status"] == key else ""}>{html.escape(label)}</option>' for key, label in APPEAL_STATUSES.items())
    fields = [('Заявитель', appeal['applicant_name']), ('Телефон', appeal['phone']), ('Email', appeal['email']), ('Лицевой счёт', appeal['account_number'] or '—'), ('Адрес объекта', appeal['service_address']), ('Категория', APPEAL_CATEGORIES.get(appeal['category'], appeal['category'])), ('Поступило', _format_datetime(appeal['submitted_at']))]
    details = ''.join(f'<div><small>{label}</small><strong>{html.escape(str(value))}</strong></div>' for label, value in fields)
    return f'''{_admin_nav_bar('appeals', 'admin', username)}<div class="appeal-detail">{alerts}<a href="/admin/appeals">← Все обращения</a><h1>{html.escape(appeal['registration_number'])}</h1><div class="appeal-detail-grid"><section><div class="appeal-meta">{details}</div><h3>Суть обращения</h3><div class="appeal-message">{html.escape(appeal['message'])}</div></section><aside><h3>Обработка</h3><form method="post" action="/admin/appeals/update"><input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><input type="hidden" name="id" value="{appeal['id']}"><label>Статус<select class="input" name="status">{status_options}</select></label><label>Комментарий<textarea class="input" name="admin_comment" maxlength="5000" rows="7">{html.escape(appeal['admin_comment'] or '')}</textarea></label><button class="btn btn-primary" type="submit">Сохранить</button></form></aside></div></div><style>.appeal-detail{{max-width:1000px;margin:26px auto;padding:0 18px}}.appeal-detail>a{{color:#2563eb}}.appeal-detail-grid{{display:grid;grid-template-columns:1.3fr .7fr;gap:18px}}.appeal-detail section,.appeal-detail aside{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;align-self:start}}.appeal-meta{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}.appeal-meta small,.appeal-meta strong{{display:block}}.appeal-meta small{{color:#64748b;margin-bottom:4px}}.appeal-message{{white-space:pre-wrap;line-height:1.6;background:#f8fafc;padding:16px;border-radius:10px}}.appeal-detail label{{display:block;margin-bottom:14px}}.appeal-detail select,.appeal-detail textarea{{display:block;width:100%;box-sizing:border-box;margin-top:6px}}@media(max-width:750px){{.appeal-detail-grid{{grid-template-columns:1fr}}.appeal-meta{{grid-template-columns:1fr}}}}</style>'''
