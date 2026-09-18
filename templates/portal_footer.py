def render_portal_footer() -> str:
    """Рендерит большой корпоративный футер веб-портала ТОО «КРЭК»."""
    return '''
<footer class="krec-footer" id="krecFooter">
    <div class="krec-footer-top">
        <div class="krec-footer-container">
            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Потребителям</h4>
                <ul class="krec-footer-links">
                    <li><a href="/kvit/">Электронная квитанция</a></li>
                    <li><a href="/consumers">Сервисный центр потребителей</a></li>
                    <li><a href="/tarif">Тариф на передачу э/э</a></li>
                    <li><a href="/price">Цены на электроснабжение</a></li>
                    <li><a href="/pd_byt_potr">Типовой публичный договор</a></li>
                    <li><a href="/appeals">Обратиться в КРЭК</a></li>
                    <li><a href="/notices">Объявления и новости</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Подключение и сеть</h4>
                <ul class="krec-footer-links">
                    <li><a href="/tu">Порядок подключения к сетям</a></li>
                    <li><a href="/tu">Технические условия (ТУ)</a></li>
                    <li><a href="/lists">Необходимые документы</a></li>
                    <li><a href="https://gov.ggk.kz" target="_blank" rel="noopener noreferrer">Портал АИС ГГК (gov.ggk.kz) ↗</a></li>
                    <li><a href="/load">Загрузка подстанций 35–110 кВ</a></li>
                    <li><a href="/images/nets.png" target="_blank" rel="noopener noreferrer">Схема электрических сетей ↗</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Компания</h4>
                <ul class="krec-footer-links">
                    <li><a href="/#about">О компании ТОО «КРЭК»</a></li>
                    <li><a href="/contacts#res">Районы электрических сетей (6 РЭС)</a></li>
                    <li><a href="/contacts">Контакты и реквизиты</a></li>
                    <li><a href="/privacy">Политика конфиденциальности</a></li>
                    <li><a href="/terms">Условия использования</a></li>
                    <li><a href="javascript:void(0)" onclick="krecOpenCookieModal()">Настройки файлов cookie</a></li>
                    <li><a href="/vacancy">Вакансии предприятия</a></li>
                    <li><a href="/tbquest">Охрана труда и безопасность</a></li>
                </ul>
            </div>

            <div class="krec-footer-col">
                <h4 class="krec-footer-title">Документы и закупки</h4>
                <ul class="krec-footer-links">
                    <li><a href="/reports">Отчетность по инвестпрограмме</a></li>
                    <li><a href="/reports">Отчетность по тарифной смете</a></li>
                    <li><a href="/docs">Нормативно-правовая база</a></li>
                    <li><a href="/zakup">Планы закупок и тендеры</a></li>
                    <li><a href="/price">Прейскурант сервисных услуг</a></li>
                    <li><a href="/privacy#rights">Защита персональных данных</a></li>
                </ul>
            </div>
        </div>
    </div>

    <div class="krec-footer-bottom">
        <div class="krec-footer-container bottom-row">
            <div class="krec-footer-copy">
                <div>&copy; 2005&ndash;2026 ТОО &laquo;Карагандинская Региональная Энергетическая Компания&raquo; (ТОО &laquo;КРЭК&raquo;). Все права защищены.</div>
                <div style="margin-top:4px; font-size:12.5px; color:#cbd5e1;">
                    БИН: <strong>031140001297</strong> &bull; 100000, Карагандинская обл., г. Караганда, район им. Казыбек би, 108 учетный квартал, стр. 7
                </div>
                <div style="margin-top:3px; font-size:12px; color:#94a3b8;">
                    Вопросы по персональным данным: <a href="mailto:dpo@krec.kz" style="color:#93c5fd; text-decoration:none;">dpo@krec.kz</a> &bull; Канцелярия: +7 (7212) 90-03-50
                </div>
                <div style="margin-top:6px; font-size:12px; color:#94a3b8; display:flex; align-items:center; gap:6px;">
                    <svg width="13" height="13" viewBox="0 0 24 24" class="svg-icon-stroke" style="stroke:#94a3b8;"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
                    <span>Разработка и создание портала: <a href="https://t.me/REALLY_DE4D" target="_blank" rel="noopener noreferrer" style="color:#e2e8f0; font-weight:700; text-decoration:none; border-bottom:1px dotted #64748b; transition:all 0.2s;" onmouseover="this.style.color='#60a5fa';this.style.borderBottomColor='#60a5fa'" onmouseout="this.style.color='#e2e8f0';this.style.borderBottomColor='#64748b'">Жүніс Тамерлан</a></span>
                </div>
            </div>
        </div>
    </div>
</footer>
'''
