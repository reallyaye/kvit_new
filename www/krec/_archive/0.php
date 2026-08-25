<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
<meta name="description" content="ТОО КРЭК (Карагандинская Региональная Энергетическая Компания) - Отчеты"/>
<title>ТОО КРЭК - Отчеты</title>
<?php
    include ('header.html');
?>
<style>
  .container {
    display: flex;
    margin: 20px;
  }

  .left-column {
    width: 30%;
    padding-right: 20px;
    border-right: 2px solid #ccc;
    height: 800px; /* Указываем фиксированную высоту */
    overflow-y: scroll; /* Разрешаем прокрутку */
  }

  .right-column {
    width: 70%;
    height: 800px;
  }

  .tree ul {
    list-style-type: none;
    margin: 0;
    padding: 0;
  }

  .tree li {
    margin: 5px 0;
  }

  .tree li ul {
    padding-left: 15px;
  }

  .tree a {
    text-decoration: none;
    color: black;
  }

  .tree a:hover {
    text-decoration: underline;
  }

  iframe {
    width: 100%;
    height: 100%;
    border: none;
  }

  .toggle-button {
    cursor: pointer;
    color: black;
    display: inline-block;
    margin-bottom: 5px;
  }

  .nested {
    display: none;
    margin-left: 15px;
    list-style-type: disc;
  }

  /* Фиксация правой колонки */
  .right-column {
    position: sticky;
    top: 0; /* Фиксируем на верхней части экрана */
  }
</style>

<script>
  // Функция для переключения видимости вложенных элементов
  function toggleVisibility(event) {
    var nestedList = event.target.nextElementSibling;
    if (nestedList.style.display === "none" || nestedList.style.display === "") {
      nestedList.style.display = "block";
      event.target.textContent = "▼ Отчет перед потребителями за 2024 год"; // Изменение на "свернуть"
    } else {
      nestedList.style.display = "none";
      event.target.textContent = "▶ Отчет перед потребителями за 2024 год"; // Изменение на "раскрыть"
    }
  }
</script>

</head>
<body>
<h1>Отчеты</h1>
<div class="container">
    <div class="left-column">
        <div class="tree">
            <ul>
                <!-- Отчеты за 2024 год -->
                <li><span class="toggle-button">▶ <b>2024 год</b></span>
                    <ul class="nested">
                        <li><b>Отчеты о исполнении инвестиционной программы</b>
                            <ul>
                                <li><a href="../files/invest-1-2024.pdf" target="report-frame">Отчет Инвестиционной программы 1 квартал 2024 года</a></li>
                                <li><a href="../files/invest-2-2024.pdf" target="report-frame">Отчет Инвестиционной программы 2 квартал 2024 года</a></li>
                                <li><a href="../files/invest-2-2024.pdf" target="report-frame">Отчет Инвестиционной программы 3 квартал 2024 года</a></li>
                                <li><a href="../files/invest-4-2024.pdf" target="report-frame">Отчет Инвестиционной программы 4 квартал 2024 года</a></li>
                            </ul>
                        </li>
                        <li><b>Тарифная смета</b>
                            <ul>
                                <li><a href="../files/isp_ts_2024_1.pdf" target="report-frame">Отчет об исполнении тарифной сметы за 2024 год 1 полугодие</a></li>
                                <li><a href="../files/activity_report_2024_1_1.pdf" target="report-frame">Отчет об исполнении инвестиционной программы за 2024 год 1 полугодие</a></li>
                            </ul>
                        </li>
                        <li><b>Отчет о деятельности</b>
                            <ul>
								<li><a href="../files/activity_report_2024_1.pdf" target="report-frame">Отчет перед потребителями за 1 полугодие 2024 года об исполнении тарифной сметы</a></li>
								<li>
								  <span class="toggle-button">▶ Отчет перед потребителями за 2024 год об исполнении тарифной сметы</span>
								  <ul class="nested">
									<li><a href="../files/1.fhd.2024.pdf" target="report-frame">Отчет ФХД за 2024 год</a></li>
									<li><a href="../files/2.isp.ts.2024.pdf" target="report-frame">Исполнение ТС за 2024 год</a></li>
									<li><a href="../files/3.isp.sm.2024.pdf" target="report-frame">Исполнение ИП за 2024 год</a></li>
									<li><a href="../files/4.prib.ub.2024.pdf" target="report-frame">Отчет о прибылях и убытках</a></li>
</ul></li></ul></li></ul></li></ul>
			<div class="line"></div> 
                <!-- Отчеты за 2023 год -->
                <ul><li><span class="toggle-button">▶ <b>2023 год</b></span>
                    <ul class="nested">
                        <li><b>Отчеты о исполнении инвестиционной программы</b>
                            <ul>
                                <li><a href="../files/invest-1-2023.pdf" target="report-frame">Отчет Инвестиционной программы 1 квартал 2023 года</a></li>
                                <li><a href="../files/invest-07023.pdf" target="report-frame">Отчет Инвестиционной программы 2 квартал 2023 года</a></li>
                                <li><a href="../files/invest-11023.pdf" target="report-frame">Отчет Инвестиционной программы 3 квартал 2023 года</a></li>
                                <li><a href="../files/invest-20224.pdf" target="report-frame">Отчет Инвестиционной программы 4 квартал 2023 года</a></li>
                            </ul>
                        </li>
                        <li><b>Тарифная смета</b>
                            <ul>
                                <li><a href="../files/tarif-1-2023.pdf" target="report-frame">Отчет об исполнении тарифной сметы за 1-ое полугодие 2023 года</a></li>
								<li><a href="../files/tarif-1-2023.pdf" target="report-frame">Отчет об исполнении инвестиционной программы за 1-ое полугодие 2023 года</a></li>
                            </ul>
                        </li>
                        <li><b>Отчет о деятельности</b>
                            <ul>
                                <li><a href="../files/invest-1-2023.pdf" target="report-frame">Отчет перед потребителями за 1 полугодие 2023 года об исполнении тарифной сметы</a></li>
								<li><a href="../files/invest-1-2023.pdf" target="report-frame">Отчет перед потребителями за 2023 год об исполнении тарифной сметы</a></li>
                            </ul>
                        </li>
                    </ul>
                </li></ul>
							
<div class="line"></div> 
                <!-- Отчеты за 2022 год -->
                <ul><li><span class="toggle-button">▶ <b>2022 год</b></span>
                    <ul class="nested">
                        <li><b>Отчеты о исполнении инвестиционной программы</b>
                            <ul>
                                <li><a href="../files/invest12022.pdf" target="report-frame">Отчет инвестиционной программы и тарифной сметы за 1 квартал 2022 года</a></li>
                                <li><a href="../files/invest22022.pdf" target="report-frame">Отчет инвестиционной программы и тарифной сметы за 1 квартал 2022 года</a></li>
                                <li><a href="../files/invest32022.pdf" target="report-frame">Отчет инвестиционной программы и тарифной сметы за 1 квартал 2022 года</a></li>
                                <li><a href="../files/invest42022.pdf" target="report-frame">Отчет инвестиционной программы и тарифной сметы за 1 квартал 2022 года</a></li>
                            </ul>
                        </li>
                        <li><b>Тарифная смета</b>
                            <ul>
                                <li><a href="../files/report12022.pdf" target="report-frame">Отчет об исполнении тарифной сметы за 1-ое полугодие 2022 года</a></li>
								<li><a href="../files/invest12022.pdf" target="report-frame">Отчет об исполнении инвестиционной программы за 1-ое полугодие 2022 года</a></li>
                            </ul>
                        </li>
                        <li><b>Отчет о деятельности</b>
                            <ul>
                                <li><a href="../files/tarif-2022.pdf" target="report-frame">Отчет об исполнении тарифной сметы за 2022 год</a></li>
								<li><a href="../files/report2022_all.pdf" target="report-frame">Отчет перед потребителями за 2022 год об исполнении тарифной сметы и инвестиционной программы</a></li>
<!--../files/additions_2022.zip -->
                            </ul>
                        </li>
                    </ul>
                </li></ul>

            </ul>
        </div>
    </div>

    <!-- Правая колонка - iframe для отображения отчета -->
    <div class="right-column">
        <iframe name="report-frame" src="" title="Выберите отчет" frameborder="0"></iframe>
    </div>
</div>

<?php
    include ('footer.html');
?>
<script>
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.toggle-button').forEach(button => {
      button.addEventListener('click', () => {
        const nested = button.nextElementSibling;
        const label = button.textContent.replace(/^▲ |▶ /, '');
        if (nested.style.display === "block") {
          nested.style.display = "none";
          button.textContent = "▶ " + label;
        } else {
          nested.style.display = "block";
          button.textContent = "▲ " + label;
        }
      });
    });
  });
</script>

</body>
</html>
