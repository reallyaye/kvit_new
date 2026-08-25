<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
  "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
<body>
<h1>Отчет инвестиционной программы и тарифной сметы за 4 квартал 2025 года</h1>
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
<?php
  include ('header.html');
?>
</head>
<body>
<h1>Отчет инвестиционной программы и тарифной сметы за 4 квартал 2025 года</h1>

<button class="toggle-button" onclick="toggleVisibility('iframeContainer')">Открыть отчет</button>
<div id="iframeContainer" class="hidden">
    <iframe height="900" src="../files/invest-4-2025.pdf" width="1200"></iframe>
</div>

<p><button class="toggle-button" onclick="toggleVisibility('tableContainer')">Открыть фотоотчет</button></p>
<div id="tableContainer" class="hidden">
    <table>
        <tr>
            <th colspan="8">Измеритель сопротивления заземления UNI-TUT 572. Для измерителя заземления ИС-20 штырь заземления РЛПА 305177.004</th>
        </tr>
        <tr>
            <td class="image-container">
				<img src="../images/unitut_72.jpg"> 
			</td>
            <td class="image-container"></td>
            <td class="image-container"></td>
            <td class="image-container"></td>
            <td class="image-container"></td>
            <td class="image-container"></td>
            <td class="image-container"></td>
        </tr>
        <tr>
            <th colspan="8">Цифровой мегомметр UT513A</th>
        </tr>
        <tr>
            <td class="image-container">
    <img src="../images/ut513a.jpg">
</td>
   	</tr>
		<tr>
			<th colspan="8">Измеритель трансформаторов тока и напряжения РЕТОМ21</th>
		</tr>
		<tr>
		<td class="image-container">
		<img src="../images/retom_21.jpg">
		</td>
		<td class="image-container">
		<img src="../images/retom_21_1.jpg">
		</td>
	</tr>
		<tr>
			<th colspan="8">Тепловизор HIKMICRO M20W</th>
		</tr>
		<tr>
		<td class="image-container">
		<img src="../images/hikmicro_m20w.jpg">
		</td>
		<td class="image-container">
		<img src="../images/hikmicro_m20w_1.jpg">
		</td>
		<td class="image-container">
		<img src="../images/hikmicro_m20w_2.jpg">
		</td>
	</tr>
		<tr>
			<th colspan="8">Автомашина ГАЗ 27527</th>
		</tr>
		<tr>
		<td class="image-container">
        <img src="../images/sobol_27527.jpg">
		</td>
		<td class="image-container">
        <img src="../images/sobol_27527_1.jpg">
		</td>
		<td class="image-container">
        <img src="../images/sobol_27527_2.jpg">
		</td>
    
    </table>
</div>

<?php
  include ('footer.html');
?>
</body>
</html>
