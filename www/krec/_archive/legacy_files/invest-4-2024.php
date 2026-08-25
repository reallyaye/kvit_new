<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
  <meta name="description" content="ТОО КРЭК (Карагандинская Региональная Энергетическая Компания) - Отчет о деятельности за 2022 год"/>
  <title>Отчет инвестиционной программы и тарифной сметы за 4 квартал 2024 года</title>
  <style>
    table {
        width: 100%;
        border-collapse: none;
    }
    td {
        padding: 10px;
        border: none;
        text-align: left;
    }
    .image-container {
        width: 400px; /* Изменен размер контейнера для примера */
        height: auto; /* Изменен размер контейнера для примера */
        overflow: hidden;
        position: relative;
    }
    .image-container img {
        width: 100%; /* Изменен размер картинки по ширине на 100% от контейнера */
        height: 100%; /* Автоматический расчет высоты для сохранения пропорций */
        object-fit: cover; /* Сохранение пропорций и обрезка изображения */
    }
    .hidden {
        display: none; /* Скрыть элементы по умолчанию */
    }
    .toggle-button {
        padding: 10px 20px; /* Размеры кнопок (вертикальный отступ 10px, горизонтальный 20px) */
        font-size: 16px; /* Размер шрифта кнопок */
    }
</style>
<script>
    function toggleVisibility(elementId) {
        var element = document.getElementById(elementId);
        // Получаем текущее состояние display элемента
        var displayStyle = window.getComputedStyle(element).getPropertyValue('display');
        
        // Toggle the 'display' property directly based on the computed style
        if (displayStyle === 'none') {
            element.style.display = 'block';
        } else {
            element.style.display = 'none';
        }
    }
</script>
  <?php include ('header.html'); ?>
</head>
<body>
  <h1>Отчет инвестиционной программы и тарифной сметы за 4 квартал 2024 года</h1>

<button class="toggle-button" onclick="toggleVisibility('iframeContainer')">Открыть отчет</button>
<div id="iframeContainer" class="hidden">
    <iframe height="900" src="../files/invest-4-2024.pdf" width="1200"></iframe>
</div>

<p><button class="toggle-button" onclick="toggleVisibility('tableContainer')">Открыть фотоотчет</button></p>
<div id="tableContainer" class="hidden">
    <table>
        <tr>
            <th colspan="8">Капитальный ремонт с увеличением балансовой стоимости ВЛ 6 кВ ф.№57 от ПС "Тентекская ТЭЦ" (Абайский район)</th>
        </tr>
        <tr>
            <td class="image-container">
                <img src="../images/5.61.jpg">
			</td>
			<td class="image-container">
                <img src="../images/5.62.jpg">
			</td>
			<td class="image-container">
                <img src="../images/5.63.jpg">
			</td>
			<td class="image-container">
                <img src="../images/5.64.jpg">
			</td>
			<td class="image-container">
               <img src="../images/5.65.jpg">
			</td>
			<td class="image-container">
               <img src="../images/5.66.jpg">
			</td>
			<td class="image-container">
                <img src="../images/5.69.jpg">
            </td>
            <td class="image-container">
                <img src="../images/5.70.jpg">
            </td>
			<td class="image-container">
                <img src="../images/5.71.jpg">
            </td>
            <td class="image-container">
                <img src="../images/5.72.jpg">
            </td>
            <td class="image-container">
                <img src="../images/5.73.jpg">
            </td>
			<td class="image-container">
                <img src="../images/5.74.jpg">
            </td> 
        </tr>
    </table>
  <?php include ('footer.html'); ?>
</body>
</html>
