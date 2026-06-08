# Установка фреймворка пайплайнов — GNU Make

Выбранный фреймворк построения пайплайнов — **GNU Make** ("Old school" /
"классика"). Это не специализированный биоинформатический workflow-движок
(как Snakemake/Nextflow), а универсальный инструмент сборки на основе
**декларативного графа зависимостей файлов** (DAG): «файл X собирается из
файлов Y и Z командой …». Идея пайплайна-как-Makefile — давний и вполне
рабочий приём в биоинформатике (см. например `bioinformatics-makefiles`,
доклады на Software Carpentry и т.д.).

## 1. Проверить, установлен ли make

```bash
make --version
# GNU Make 4.3
# Built for x86_64-pc-linux-gnu
```

Если команда найдена — всё готово, переходите к Hello World (`framework/hello_world`).

## 2. Установка (если make не установлен)

### Вариант А — из репозитория дистрибутива (самый простой, рекомендуется)

```bash
# Debian/Ubuntu
sudo apt-get update
sudo apt-get install -y make

# Fedora/RHEL/CentOS
sudo dnf install -y make

# Arch Linux
sudo pacman -S make

# macOS (через Homebrew; на macOS уже есть BSD make, но GNU make ставится как gmake)
brew install make
```

### Вариант Б — сборка из исходников (даёт самую свежую версию GNU Make)

```bash
wget https://ftp.gnu.org/gnu/make/make-4.4.1.tar.gz
tar xzf make-4.4.1.tar.gz
cd make-4.4.1
./configure --prefix=$HOME/.local
make            # классический "bootstrap": make собирает сам себя через sh build.sh
make install
export PATH="$HOME/.local/bin:$PATH"
make --version
```

## 3. Проверка установки

```bash
cd framework/hello_world
make            # должен вывести "Hello, world! Это тестовый пайплайн на GNU Make."
make clean      # удаляет сгенерированные файлы
```

Если вы видите приветствие — фреймворк готов к работе.

