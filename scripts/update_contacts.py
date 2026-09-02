import json

contacts_html = '''<div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 20px;">
    <div style="flex: 1; min-width: 320px;">
        <h1>Наш адрес</h1>
        <p><strong>Адрес:</strong> Республика Казахстан, 100012, г. Караганда, 108 учетный квартал, 7</p>
        <p><strong>Приёмная:</strong> <a href="tel:+77212900350">+7 (7212) 90-03-50</a></p>
        <p><strong>Оперативно-диспетчерская служба (ОДС):</strong><br/>
           <a href="tel:+77212900358">+7 (7212) 90-03-58</a>, <a href="tel:+77212900359">+7 (7212) 90-03-59</a> <span style="color:#64748b; font-size:13px;">(круглосуточно)</span>
        </p>
        <p><strong>По вопросам оплаты и квитанций:</strong> <a href="tel:+77212900353">+7 (7212) 90-03-53</a></p>
        <p><strong>E-mail:</strong> <a href="mailto:info.krec@mail.ru">info.krec@mail.ru</a></p>
        <p><strong>Руководитель организации:</strong> Директор Кельбуганов Руслан Абильбекович</p>
        <p><strong>Главный инженер организации:</strong> Смольяков Александр Александрович</p>
        <script type="text/javascript" charset="utf-8" src="https://api-maps.yandex.ru/services/constructor/1.0/js/?sid=K4CZTUki7kDpPDiXo3e6SJysorMzLlf1&amp;width=600&amp;height=450"></script>
        <div class="space"></div>
    </div>
    <div style="flex: 1; min-width: 320px;">
        <h1>Приемные дни и службы</h1>
        <p><b>Группа учета и распределения электроэнергии (ОРиКЭ)</b></p>
        <p>2 этаж, кабинет "ОРиКЭ" | Вторник, Четверг с 8.00 до 17.00 (обед с 12.00 до 13.00)</p>
        <p>Телефон: <a href="tel:+77212900355">+7 (7212) 90-03-55</a></p>
        <div class="line"></div>
        <p><b>Производственно-техническая служба (ПТС)</b></p>
        <p>3 этаж, кабинет "ПТС" | Вторник, Четверг с 8.00 до 17.00 (обед с 12.00 до 13.00)</p>
        <p>Телефон: <a href="tel:+77212900352">+7 (7212) 90-03-52</a></p>
        <div class="line"></div>
        <p><b>Служба воздушных линий и подстанций (ВЛ и ПС)</b></p>
        <p>3 этаж, кабинет "ВЛ и ПС" | Вторник, Четверг с 8.00 до 17.00 (обед с 12.00 до 13.00)</p>
        <p>Телефон: <a href="tel:+77212900352">+7 (7212) 90-03-52</a></p>
        <div class="line"></div>
        <p><b>Отдел материально-технического снабжения (ОМТС)</b></p>
        <p>1 этаж, кабинет 106</p>
        <div class="line"></div>
    </div>
</div>'''

for path in ['data/extracted_portal_pages.json', 'docs/data/extracted_portal_pages.json']:
    with open(path, 'r', encoding='utf-8') as f:
        d = json.load(f)
    d['contacts']['html'] = contacts_html
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(d, f, ensure_ascii=False, indent=2)

print('Updated contacts in JSON files successfully.')
