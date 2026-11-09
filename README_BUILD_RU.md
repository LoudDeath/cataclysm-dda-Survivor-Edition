# Сборка Survivor Edition для Windows x64

Проверенные ранее для рабочего проекта версии закреплены в [edition/toolchain.lock.json](edition/toolchain.lock.json). Для этого отдельного снимка выполнены проверки исходников. Полная сборка игры из снимка на чистой машине ещё не выполнена.

## Инструменты

1. Установите Visual Studio Build Tools 18 с набором MSVC x64/x86 14.51.36231 и Windows SDK 10.0.26100.0. Установите Git и Python 3.12 или новее.
2. Распакуйте [CMake 3.31.8 для Windows x64](https://github.com/Kitware/CMake/releases/tag/v3.31.8) в папку .tools так, чтобы файл находился в .tools/cmake-3.31.8-windows-x86_64/bin/cmake.exe.
3. Восстановите vcpkg в .tools/vcpkg по коммиту из файла фиксации версий. Запустите его bootstrap-vcpkg.bat. Скрипт сборки использует манифест msvc-full-features/vcpkg.json и статический triplet x64-windows-static.
4. Установите polib 1.2.0 командой ниже. URL и SHA-256 исходного wheel указаны в [edition/polib.lock.json](edition/polib.lock.json).

## Команды PowerShell из корня проекта

```powershell
git clone https://github.com/microsoft/vcpkg.git .tools/vcpkg
git -C .tools/vcpkg checkout 6d7bf7ef2193e2d1c5798a5ff8811d533104c861
& ./.tools/vcpkg/bootstrap-vcpkg.bat -disableMetrics
python -m pip install --target .tools/python-packages polib==1.2.0

python scripts/restore_dependency_sources.py
./scripts/build.ps1 -Target Dependencies -Jobs 1
python scripts/compile_translations.py --source edition/localization/edition-ru-complete.po
./scripts/build.ps1 -Target Game -Jobs 2
python scripts/check_runtime.py --all-mods
```

Если Build Tools установлены в другом каталоге, передайте его в параметре -ToolchainRoot обоим вызовам build.ps1. Скрипт восстановления проверяет хеши архивов и разворачивает точные порты с патчами. Для начальной установки инструментов и сборки нужен доступ к сети. Для установки и сборки предусмотрите около 25 ГБ свободного места.

Игра собирается в cataclysm-tiles.exe в корне проекта. Для отдельного профиля при ручной проверке передайте --userdir с путём к новой папке. Проверка check_runtime.py создаёт отдельный временный профиль.
