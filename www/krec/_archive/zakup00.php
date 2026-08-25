<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN"
    "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">

<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ru" lang="ru">
<head>
<meta name="description" content="ТОО КРЭК (Карагандинская Региональная Энергетическая Компания) - Закупки"/>
<title>ТОО КРЭК - Закупки</title>
<style>
    .container {
        display: flex;
        flex-wrap: wrap;
        gap: 20px;
    }
    .section {
        flex: 1;
        min-width: 200px;
    }
    .section h1 {
        font-size: 18px;
        margin-bottom: 10px;
    }
    .section p {
        margin: 5px 0;
    }
</style>
</head>
<body>
<?php
    include ('header.html');
?>
<h1>Закупки</h1>
<div class="container">
    <div class="section">
        <h1>План закупок</h1>
        <p><a href="plan2022.php">2022</a></p>
        <p><a href="plan2023.php">2023</a></p>
    </div>
    <div class="section">
        <h1>Объявления на тендер</h1>
        <p><a href="tender2017.php">2017</a></p>
        <p><a href="tender2018.php">2018</a></p>
        <p><a href="tender2019.php">2019</a></p>
        <p><a href="tender2020.php">2020</a></p>
        <p><a href="tender2021.php">2021</a></p>
        <p><a href="tender2022.php">2022</a></p>
    </div>
    <div class="section">
        <h1>Итоги тендера</h1>
        <p><a href="itender2017.php">2017</a></p>
        <p><a href="itender2018.php">2018</a></p>
        <p><a href="itender2019.php">2019</a></p>
        <p><a href="itender2020.php">2020</a></p>
        <p><a href="itender2021.php">2021</a></p>
        <p><a href="itender2022.php">2022</a></p>
    </div>
    <div class="section">
        <h1>Ценовые предложения</h1>
        <p><a href="zapros.php">Запрос</a></p>
        <p><a href="cp2.php">Протокол</a></p>
        <p><a href="cp3.php">Итоги</a></p>
    </div>
    <div class="section">
        <h1>Закуп из одного источника</h1>
        <p><a href="zakup2020.php">2020</a></p>
        <p><a href="zakup2021.php">2021</a></p>
        <p><a href="zakup2022.php">2022</a></p>
    </div>
</div>
<?php
    include ('footer.html');
?>
</body>
</html>
