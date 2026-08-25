<?php
$file = "temp_images/test.txt";
file_put_contents($file, "Проверка записи!");
if (file_exists($file)) {
    echo "Запись в папку работает!";
} else {
    echo "Ошибка записи!";
}
?>
