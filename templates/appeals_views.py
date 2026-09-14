import html
import json
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
      <div class="appeals-intro"><h1>Электронная приёмная обращений потребителей</h1><p>Подача обращений, вопросов и заявлений в ТОО «Карагандинская Региональная Энергетическая Компания» (ТОО «КРЭК»).</p><a class="appeals-track-link" href="/appeals/status">Проверить статус и ответ →</a></div>
      <div class="appeals-grid">
        <div class="appeals-card appeals-form-card">
          <h2>Форма подачи обращения</h2>
          <p class="appeals-help">Поля, отмеченные звёздочкой (*), обязательны. Каждому обращению присваивается уникальный номер для отслеживания статуса на сайте.</p>
          <form id="appeal-form" action="/api/appeals" method="post" novalidate>
            <input type="hidden" name="consent_version" value="v1.0-2026-kz">
            <label>Категория обращения *<select name="category" required><option value="">Выберите тематику обращения…</option>{options}</select></label>
            <div class="appeals-fields">
              <label>ФИО заявителя (или наименование организации) *<input name="applicant_name" class="ym-disable-keys" maxlength="255" autocomplete="name" required placeholder="Иванов Иван Иванович"></label>
              <label>Контактный телефон *<input name="phone" class="ym-disable-keys" type="tel" maxlength="64" autocomplete="tel" required placeholder="+7 (___) ___-__-__"></label>
              <label>Адрес электронной почты (для получения ответа)<input name="email" class="ym-disable-keys" type="email" maxlength="254" autocomplete="email" placeholder="example@mail.kz"></label>
              <label>Номер лицевого счёта (при наличии)<input name="account_number" class="ym-disable-keys" maxlength="64" inputmode="numeric" placeholder="Например: 12345678"></label>
            </div>
            <label>Адрес объекта электроснабжения (обязательно при отключениях и ТУ)<input name="service_address" class="ym-disable-keys" maxlength="500" autocomplete="street-address" placeholder="Район, населённый пункт, улица, дом, кв."></label>
            <label>Суть обращения *<textarea name="message" class="ym-disable-keys" minlength="10" maxlength="5000" rows="6" required placeholder="Подробно опишите суть вопроса, дату происшествия или требуемые действия…"></textarea></label>
            <div class="appeals-consent-box" style="background:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:16px; margin-bottom:20px;">
              <label class="appeals-consent" style="margin-bottom:6px;">
                <input name="consent" type="checkbox" value="1" required>
                <span>Подтверждаю согласие на сбор, обработку и хранение персональных данных в соответствии со статьей 8 Закона Республики Казахстан «О персональных данных и их защите» *</span>
              </label>
              <details style="font-size:12.5px; color:#64748b; margin-top:8px; line-height:1.5;">
                <summary style="cursor:pointer; color:#2563eb; font-weight:600;">Существенные условия согласия согласно ст. 8 Закона РК № 94-V (нажмите, чтобы развернуть)</summary>
                <div style="margin-top:10px; padding-top:8px; border-top:1px dashed #cbd5e1;">
                  <p style="margin:4px 0;"><strong>Оператор:</strong> ТОО «Карагандинская Региональная Энергетическая Компания» (БИН 031140001297, г. Караганда, район имени Казыбек би, 108 учетный квартал, строение 7).</p>
                  <p style="margin:4px 0;"><strong>Цель сбора и обработки:</strong> Приём, учёт и объективное рассмотрение обращения потребителя услуг субъекта естественной монополии по передаче электроэнергии, предоставление официального мотивированного ответа.</p>
                  <p style="margin:4px 0;"><strong>Перечень собираемых данных:</strong> ФИО заявителя (субъекта), контактный телефон, email, номер лицевого счёта (при наличии), адрес объекта, текст обращения.</p>
                  <p style="margin:4px 0;"><strong>Срок действия согласия:</strong> Действует в течение 3 (трёх) лет с даты регистрации обращения (в пределах сроков исковой давности) до момента автоматического безвозвратного обезличивания.</p>
                  <p style="margin:4px 0;"><strong>Передача третьим лицам и трансграничная передача:</strong> Передача третьим лицам не осуществляется, за исключением доставки email-уведомлений заявителю через почтовый шлюз (Mail.ru SMTP / ООО «ВК», РФ) по ст. 16 Закона РК № 94-V.</p>
                  <p style="margin:4px 0;"><strong>Сведения о распространении:</strong> Персональные данные потребителей <u>не распространяются</u> в общедоступных источниках.</p>
                  <p style="margin:4px 0;"><strong>Порядок отзыва согласия:</strong> Письменным заявлением нарочно/почтой в канцелярию ТОО «КРЭК» или на email: <a href="mailto:dpo@krec.kz" style="color:#2563eb;">dpo@krec.kz</a> / <a href="mailto:info@krec.kz" style="color:#2563eb;">info@krec.kz</a>. Полный текст: <a href="/privacy" target="_blank" style="color:#2563eb; text-decoration:underline;">Политика конфиденциальности</a>.</p>
                </div>
              </details>
            </div>
            <div class="appeals-honeypot" aria-hidden="true"><label>Не заполняйте это поле<input name="website" tabindex="-1" autocomplete="off"></label></div>
            <div id="appeal-result" class="appeals-result" role="status" aria-live="polite"></div>
            <button id="appeal-submit" class="appeals-submit" type="submit">Отправить обращение</button>
          </form>
        </div>
        <aside>
          <div class="appeals-card"><h3>Порядок рассмотрения</h3><ol class="appeals-steps">
            <li><strong>Регистрация обращения</strong><span>В течение 1 рабочего дня с присвоением уникального регистрационного номера.</span></li>
            <li><strong>Срок рассмотрения</strong><span>До 15 рабочих дней в соответствии со ст. 24 Закона РК «О естественных монополиях» и ст. 76 АППК РК.</span></li>
            <li><strong>Ответ потребителю</strong><span>Направляется на указанную электронную почту заявителя или почтовым отправлением.</span></li>
          </ol></div>
          <div class="appeals-card appeals-office"><h3>Канцелярия предприятия</h3><p>Письменное заявление можно подать лично:</p><p><strong>г. Караганда, 108 уч. квартал, строение 7</strong></p><p>Канцелярия: <strong>+7 (7212) 90-03-50</strong></p><small>Пн–Пт с 08:00 до 17:00 (обед 12:00–13:00)</small></div>
        </aside>
      </div>
    </section>
    <style>
      .appeals-page{{max-width:1120px;margin:0 auto;padding:16px 20px 54px;color:#172033}}.appeals-intro{{padding:0 0 28px;border-bottom:1px solid #dbe3ef;margin-bottom:32px}}.appeals-intro h1{{font-size:18px;margin:0 0 5px}}.appeals-intro p,.appeals-help,.appeals-card p,.appeals-card small{{color:#64748b}}.appeals-track-link{{display:inline-block;margin-top:6px;color:#2563eb;font-weight:700}}.appeals-grid{{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:30px;align-items:start}}.appeals-card{{background:#fff;border:1px solid #d9e1ec;border-radius:15px;padding:28px 32px;box-shadow:0 3px 12px rgba(15,23,42,.04);margin-bottom:20px}}.appeals-card h2{{font-size:23px;margin:0 0 8px}}.appeals-card h3{{font-size:18px;margin:0 0 18px;padding-bottom:13px;border-bottom:1px solid #e5eaf1}}.appeals-help{{font-size:14px;line-height:1.55;margin:0 0 25px}}#appeal-form>label,.appeals-fields label{{display:flex;flex-direction:column;gap:8px;font-weight:600;font-size:14px;margin-bottom:20px}}.appeals-fields{{display:grid;grid-template-columns:1fr 1fr;gap:0 16px}}#appeal-form input,#appeal-form select,#appeal-form textarea{{width:100%;box-sizing:border-box;border:1px solid #cbd5e1;border-radius:10px;padding:13px 14px;font:inherit;background:#fff;color:#172033}}#appeal-form input:focus,#appeal-form select:focus,#appeal-form textarea:focus{{outline:2px solid #bfdbfe;border-color:#2563eb}}.appeals-consent{{flex-direction:row!important;align-items:flex-start;gap:11px!important;font-weight:500!important}}.appeals-consent input{{width:auto!important;margin-top:3px}}.appeals-honeypot{{position:absolute!important;left:-10000px!important;width:1px;height:1px;overflow:hidden}}.appeals-submit{{border:0;border-radius:10px;background:#1367d1;color:#fff;font-weight:700;padding:14px 22px;cursor:pointer}}.appeals-submit:disabled{{opacity:.6;cursor:wait}}.appeals-result{{display:none;border-radius:10px;padding:12px 14px;margin:0 0 16px;font-size:14px}}.appeals-result.ok{{display:block;background:#ecfdf5;color:#166534;border:1px solid #bbf7d0}}.appeals-result.error{{display:block;background:#fef2f2;color:#991b1b;border:1px solid #fecaca}}.appeals-result a{{display:inline-block;margin-top:8px;color:inherit;font-weight:700;text-decoration:underline}}.appeals-steps{{list-style:none;padding:0;margin:0;counter-reset:step}}.appeals-steps li{{counter-increment:step;position:relative;padding:0 0 24px 55px;min-height:35px}}.appeals-steps li:before{{content:counter(step);position:absolute;left:0;top:0;width:27px;height:27px;border-radius:50%;background:#eff6ff;color:#2563eb;display:grid;place-items:center;font-weight:700}}.appeals-steps strong,.appeals-steps span{{display:block}}.appeals-steps span{{color:#64748b;font-size:14px;line-height:1.55;margin-top:5px}}.appeals-office p{{font-size:14px;line-height:1.55}}@media(max-width:800px){{.appeals-grid{{grid-template-columns:1fr}}.appeals-fields{{grid-template-columns:1fr}}.appeals-card{{padding:22px 18px}}}}
    </style>
    <script>
    (() => {{
      const form=document.getElementById('appeal-form'),result=document.getElementById('appeal-result'),button=document.getElementById('appeal-submit');
      if(!form)return;
      form.addEventListener('submit',async(event)=>{{event.preventDefault();result.className='appeals-result';result.textContent='';if(!form.reportValidity())return;button.disabled=true;button.textContent='Отправляем…';
        try{{const response=await fetch(form.action,{{method:'POST',headers:{{'Accept':'application/json'}},body:new URLSearchParams(new FormData(form))}});const data=await response.json();if(!response.ok)throw new Error(data.message||'Не удалось отправить обращение.');const emailNote=data.confirmation_sent?' Персональная ссылка отправлена на вашу почту.':'';const entry={{number:data.registration_number,code:data.access_code,savedAt:Date.now()}};try{{const stored=JSON.parse(localStorage.getItem('krec_my_appeals_v1')||'[]');const list=Array.isArray(stored)?stored:[];localStorage.setItem('krec_my_appeals_v1',JSON.stringify([entry,...list.filter(item=>item&&item.number!==entry.number)].slice(0,20)));}}catch(storageError){{}}result.textContent='';const message=document.createElement('div');message.textContent=`Обращение зарегистрировано и добавлено в раздел «Мои обращения».${{emailNote}}`;const link=document.createElement('a');const access=new URLSearchParams({{number:data.registration_number,code:data.access_code}});link.href=`/appeals/status#${{access.toString()}}`;link.textContent='Открыть моё обращение →';result.append(message,link);result.className='appeals-result ok';form.reset();}}
        catch(error){{result.textContent=error.message||'Произошла ошибка. Попробуйте ещё раз.';result.className='appeals-result error';}}
        finally{{button.disabled=false;button.textContent='Отправить обращение';}}
      }});
    }})();
    </script>'''
    return portal_layout(content=content, title='Подать обращение — ТОО «КРЭК»', active_nav='appeals', is_admin=is_admin, current_slug='appeals')


def render_appeal_status_page(is_admin=False):
    category_map = json.dumps(APPEAL_CATEGORIES, ensure_ascii=False)
    status_map = json.dumps(APPEAL_STATUSES, ensure_ascii=False)
    content = f'''
    <section class="appeal-status-page">
      <div class="appeal-status-card">
        <a class="appeal-status-back" href="/appeals">← К форме обращения</a>
        <h1>Мои обращения</h1>
        <div id="saved-appeals" class="saved-appeals" hidden><div id="saved-appeals-list" class="saved-appeals-list"></div><button id="saved-appeals-clear" type="button">Удалить список с этого устройства</button><p>На общем компьютере удалите список после работы.</p></div>
        <div id="saved-appeals-empty" class="saved-appeals-empty" hidden>На этом устройстве пока нет сохранённых обращений. <a href="/appeals">Подать обращение</a></div>
        <form id="appeal-status-form" action="/api/appeals/status" method="post" hidden aria-hidden="true">
          <input type="hidden" name="registration_number">
          <input type="hidden" name="credential">
          <button id="appeal-status-submit" type="submit" tabindex="-1"></button>
        </form>
        <div id="appeal-status-error" class="appeal-status-error" role="alert"></div>
        <div id="appeal-status-result" class="appeal-status-result" aria-live="polite"></div>
      </div>
    </section>
    <style>
      .appeal-status-page{{max-width:760px;margin:0 auto;padding:34px 20px 70px;color:#172033}}.appeal-status-card{{background:#fff;border:1px solid #d9e1ec;border-radius:16px;padding:32px;box-shadow:0 4px 18px rgba(15,23,42,.06)}}.appeal-status-back{{color:#2563eb;font-weight:600}}.appeal-status-card h1{{margin:24px 0 8px;font-size:28px}}.saved-appeals{{margin:22px 0 0;padding:18px;background:#eff6ff;border:1px solid #bfdbfe;border-radius:12px}}.saved-appeals-list{{display:grid;gap:9px}}.saved-appeal-link{{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 15px;background:#fff;border:1px solid #dbeafe;border-radius:9px;color:#1d4ed8;font-weight:700;text-decoration:none}}.saved-appeal-link:hover{{border-color:#93c5fd;background:#f8fbff}}.saved-appeal-link span:last-child{{font-size:13px;color:#64748b;font-weight:500}}#saved-appeals-clear{{margin-top:14px;padding:0;border:0;background:none;color:#b91c1c;text-decoration:underline;cursor:pointer;font:inherit;font-size:13px}}.saved-appeals p{{margin:10px 0 0;color:#64748b;font-size:13px}}.saved-appeals-empty{{margin-top:22px;padding:18px;border:1px dashed #cbd5e1;border-radius:12px;color:#64748b;line-height:1.6}}.saved-appeals-empty a{{color:#2563eb;font-weight:650}}.appeal-status-error{{display:none;margin-top:18px;padding:12px;border-radius:9px;background:#fef2f2;color:#991b1b}}.appeal-status-result{{display:none;margin-top:22px;border-top:1px solid #e2e8f0;padding-top:22px}}.appeal-status-result.show{{display:block}}.appeal-status-summary{{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-bottom:20px}}.appeal-status-summary div,.appeal-public-answer{{background:#f8fafc;border-radius:10px;padding:15px}}.appeal-status-summary small{{display:block;color:#64748b;margin-bottom:5px}}.appeal-public-answer{{white-space:pre-wrap;line-height:1.65;border-left:4px solid #2563eb}}.appeal-awaiting{{padding:15px;background:#fffbeb;color:#854d0e;border-radius:10px}}@media(max-width:700px){{.appeal-status-summary{{grid-template-columns:1fr}}.appeal-status-card{{padding:23px 18px}}}}
    </style>
    <script>
    (() => {{
      const form=document.getElementById('appeal-status-form'),button=document.getElementById('appeal-status-submit'),error=document.getElementById('appeal-status-error'),result=document.getElementById('appeal-status-result'),savedBox=document.getElementById('saved-appeals'),savedList=document.getElementById('saved-appeals-list'),savedEmpty=document.getElementById('saved-appeals-empty'),clearSaved=document.getElementById('saved-appeals-clear');
      const categories={category_map},statuses={status_map};
      const formatDate=(value)=>value?new Intl.DateTimeFormat(document.documentElement.lang==='kk'?'kk-KZ':'ru-RU',{{dateStyle:'medium',timeStyle:'short'}}).format(new Date(value*1000)):'—';
      const storageKey='krec_my_appeals_v1';
      const readSaved=()=>{{try{{const value=JSON.parse(localStorage.getItem(storageKey)||'[]');return Array.isArray(value)?value.filter(item=>item&&typeof item.number==='string'&&typeof item.code==='string').slice(0,20):[];}}catch(storageError){{return [];}}}};
      const writeSaved=(items)=>{{try{{localStorage.setItem(storageKey,JSON.stringify(items.slice(0,20)));}}catch(storageError){{}}}};
      const loadAppeal=(number,code,updateHash=true)=>{{if(button.disabled)return;const params=new URLSearchParams({{number,code}});if(updateHash)window.history.replaceState(null,'',`${{window.location.pathname}}${{window.location.search}}#${{params.toString()}}`);form.elements.registration_number.value=number;form.elements.credential.value=code;form.requestSubmit();}};
      const renderSaved=()=>{{const items=readSaved();savedList.textContent='';savedBox.hidden=!items.length;savedEmpty.hidden=Boolean(items.length);if(!items.length)return;items.forEach(item=>{{const link=document.createElement('a'),number=document.createElement('span'),date=document.createElement('span'),params=new URLSearchParams({{number:item.number,code:item.code}});link.className='saved-appeal-link';link.href=`/appeals/status#${{params.toString()}}`;link.addEventListener('click',(event)=>{{event.preventDefault();loadAppeal(item.number,item.code);}});number.textContent=item.number;date.textContent=item.savedAt?new Intl.DateTimeFormat(document.documentElement.lang==='kk'?'kk-KZ':'ru-RU').format(new Date(item.savedAt)):'Открыть';link.append(number,date);savedList.append(link);}});}};
      clearSaved.addEventListener('click',()=>{{try{{localStorage.removeItem(storageKey);}}catch(storageError){{}}renderSaved();}});
      form.addEventListener('submit',async(event)=>{{event.preventDefault();error.style.display='none';result.className='appeal-status-result';result.textContent='';button.disabled=true;
        try{{const response=await fetch(form.action,{{method:'POST',headers:{{'Accept':'application/json'}},body:new URLSearchParams(new FormData(form))}});const data=await response.json();if(!response.ok)throw new Error(data.message||'Не удалось проверить обращение.');
          const summary=document.createElement('div');summary.className='appeal-status-summary';
          [['Номер',data.registration_number],['Статус',statuses[data.status]||data.status],['Категория',categories[data.category]||data.category],['Подано',formatDate(data.submitted_at)]].forEach(([label,value])=>{{const box=document.createElement('div'),small=document.createElement('small'),strong=document.createElement('strong');small.textContent=label;strong.textContent=value;box.append(small,strong);summary.append(box);}});result.append(summary);
          const answer=document.createElement('div');if(data.response_text){{const title=document.createElement('h2');title.textContent='Ответ на ваше обращение';answer.className='appeal-public-answer';answer.textContent=data.response_text;result.append(title,answer);}}else{{answer.className='appeal-awaiting';answer.textContent='Ответ ещё не подготовлен. Зайдите позже.';result.append(answer);}}result.className='appeal-status-result show';result.scrollIntoView({{block:'nearest'}});
        }}catch(exc){{error.textContent=exc.message||'Произошла ошибка.';error.style.display='block';}}finally{{button.disabled=false;}}
      }});
      const personalLink=new URLSearchParams(window.location.hash.slice(1));
      const savedNumber=personalLink.get('number'),savedCode=personalLink.get('code');
      if(savedNumber&&savedCode){{const current={{number:savedNumber,code:savedCode,savedAt:Date.now()}};writeSaved([current,...readSaved().filter(item=>item.number!==savedNumber)]);loadAppeal(savedNumber,savedCode,false);}}
      renderSaved();
    }})();
    </script>'''
    return portal_layout(content=content, title='Статус обращения — ТОО «КРЭК»', active_nav='appeals', is_admin=is_admin, current_slug='appeals')


def _format_datetime(timestamp):
    try:
        return datetime.fromtimestamp(float(timestamp)).strftime('%d.%m.%Y %H:%M')
    except (TypeError, ValueError, OSError):
        return '—'


def render_admin_appeals_list(data, stats, filters, csrf_token, message=None, error=None, username='admin', alerts_list=None, role='admin'):
    del csrf_token
    alerts = (f'<div class="ok">{html.escape(message)}</div>' if message else '') + (f'<div class="err">{html.escape(error)}</div>' if error else '')

    active_alerts_html = ''
    if alerts_list:
        items = []
        for a in alerts_list:
            is_crit = a.get('severity') == 'CRITICAL'
            bg = '#fef2f2' if is_crit else '#fffbeb'
            border = '#f87171' if is_crit else '#fcd34d'
            text_color = '#991b1b' if is_crit else '#92400e'
            icon = '🚨' if is_crit else '⚠️'
            items.append(
                f'<div style="background:{bg};border:1px solid {border};color:{text_color};padding:12px 16px;border-radius:10px;margin-bottom:10px;font-size:14px;display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:18px;">{icon}</span><div><strong>{html.escape(a.get("title", ""))}</strong>: {html.escape(a.get("message", ""))}</div></div>'
            )
        active_alerts_html = f'<div class="appeal-system-alerts" style="margin-bottom:20px;">{"".join(items)}</div>'

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
    return f'''{_admin_nav_bar('appeals', role, username)}<div class="appeal-admin">{alerts}{active_alerts_html}<h1>Обращения граждан</h1><p>Реестр обращений, поступивших через сайт</p><div class="appeal-stats">{cards}</div><form method="get" action="/admin/appeals" class="appeal-filter"><input class="input" name="search" value="{html.escape(filters.get('search', ''))}" placeholder="Номер, ФИО, email, телефон или лицевой счёт"><select class="input" name="status">{status_options}</select><button class="btn btn-primary" type="submit">Найти</button></form><div class="appeal-table"><table><thead><tr><th>Номер</th><th>Дата</th><th>Заявитель</th><th>Категория</th><th>Статус</th></tr></thead><tbody>{rows_html}</tbody></table></div>{pagination}</div><style>.appeal-admin{{max-width:1200px;margin:26px auto;padding:0 18px}}.appeal-admin>p{{color:#64748b}}.appeal-stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}}.appeal-stat{{background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:14px}}.appeal-stat small{{display:block;color:#64748b}}.appeal-stat strong{{display:block;font-size:25px;margin-top:4px}}.appeal-filter{{display:flex;gap:10px;background:#fff;border:1px solid #e2e8f0;padding:14px;border-radius:12px;margin-bottom:16px}}.appeal-filter input{{flex:1}}.appeal-table{{overflow:auto;background:#fff;border:1px solid #e2e8f0;border-radius:12px}}.appeal-table table{{width:100%;border-collapse:collapse}}.appeal-table th,.appeal-table td{{padding:13px;text-align:left;border-bottom:1px solid #eef2f7;font-size:14px}}.appeal-table th{{color:#64748b;font-size:12px;text-transform:uppercase}}.appeal-table a{{font-weight:700;color:#2563eb}}.appeal-empty{{text-align:center!important;padding:35px!important;color:#64748b}}.appeal-pagination{{display:flex;gap:6px;margin-top:18px}}@media(max-width:700px){{.appeal-stats{{grid-template-columns:1fr 1fr}}.appeal-filter{{flex-direction:column}}}}</style>'''


def render_admin_appeal_detail(appeal, csrf_token, message=None, error=None, username='admin', role='admin'):
    alerts = (f'<div class="ok">{html.escape(message)}</div>' if message else '') + (f'<div class="err">{html.escape(error)}</div>' if error else '')
    status_options = ''.join(f'<option value="{key}"{" selected" if appeal["status"] == key else ""}>{html.escape(label)}</option>' for key, label in APPEAL_STATUSES.items())
    fields = [('Заявитель', appeal['applicant_name']), ('Телефон', appeal['phone']), ('Email', appeal['email']), ('Лицевой счёт', appeal['account_number'] or '—'), ('Адрес объекта', appeal['service_address']), ('Категория', APPEAL_CATEGORIES.get(appeal['category'], appeal['category'])), ('Поступило', _format_datetime(appeal['submitted_at']))]
    details = ''.join(f'<div><small>{label}</small><strong>{html.escape(str(value))}</strong></div>' for label, value in fields)
    email_state = 'Отправлен на email' if appeal.get('response_sent') else 'На email не отправлен'
    return f'''{_admin_nav_bar('appeals', role, username)}
    <div class="appeal-detail">{alerts}<a href="/admin/appeals">← Все обращения</a><h1>{html.escape(appeal['registration_number'])}</h1>
      <div class="appeal-detail-grid">
        <section><div class="appeal-meta">{details}</div><h3>Суть обращения</h3><div class="appeal-message">{html.escape(appeal['message'])}</div></section>
        <aside><h3>Обработка</h3>
          <form method="post" action="/admin/appeals/update">
            <input type="hidden" name="csrf_token" value="{html.escape(csrf_token)}"><input type="hidden" name="id" value="{appeal['id']}">
            <label>Статус<select class="input" name="status">{status_options}</select></label>
            <label>Внутренний комментарий <small>Виден только сотрудникам</small><textarea class="input" name="admin_comment" maxlength="5000" rows="5">{html.escape(appeal['admin_comment'] or '')}</textarea></label>
            <button class="btn" name="action" value="save" type="submit">Сохранить изменения</button>
            <hr><label>Ответ заявителю <small>Будет виден заявителю по его коду доступа</small><textarea class="input" name="response_text" maxlength="10000" rows="8">{html.escape(appeal.get('response_text') or '')}</textarea></label>
            <p class="response-state">{email_state}</p><button class="btn btn-primary" name="action" value="respond" type="submit">Отправить ответ заявителю</button>
          </form>
        </aside>
      </div>
    </div>
    <style>.appeal-detail{{max-width:1100px;margin:26px auto;padding:0 18px}}.appeal-detail>a{{color:#2563eb}}.appeal-detail-grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}}.appeal-detail section,.appeal-detail aside{{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;align-self:start}}.appeal-meta{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}.appeal-meta small,.appeal-meta strong{{display:block}}.appeal-meta small,.appeal-detail label small{{color:#64748b;margin-bottom:4px}}.appeal-message{{white-space:pre-wrap;line-height:1.6;background:#f8fafc;padding:16px;border-radius:10px}}.appeal-detail label{{display:block;margin-bottom:14px}}.appeal-detail label small{{display:block;font-weight:400;margin-top:3px}}.appeal-detail select,.appeal-detail textarea{{display:block;width:100%;box-sizing:border-box;margin-top:6px}}.appeal-detail hr{{border:0;border-top:1px solid #e2e8f0;margin:22px 0}}.response-state{{font-size:13px;color:#64748b}}@media(max-width:750px){{.appeal-detail-grid{{grid-template-columns:1fr}}.appeal-meta{{grid-template-columns:1fr}}}}</style>'''
