# ============================================================================
#  Hello World — простейший тест фреймворка GNU Make (HW3, п.11)
#
#  Цель: убедиться, что make установлен и понять базовый синтаксис:
#    target: prerequisites
#    <TAB>recipe
#
#  Запуск:
#    make            # построить hello.txt и вывести его на экран
#    make clean      # удалить сгенерированные файлы
#    make again      # пересобрать с нуля (демонстрация повторного запуска)
# ============================================================================

.PHONY: all clean again

all: hello.txt
	@echo "--- содержимое hello.txt ---"
	@cat hello.txt
	@echo "----------------------------"
	@echo "GNU Make version: $(MAKE_VERSION)"

# Правило: файл hello.txt зависит от самого Makefile (изменили рецепт -> пересоберём).
hello.txt: Makefile
	echo "Hello, world! Это тестовый пайплайн на GNU Make." > $@
	echo "Собрано: $$(date '+%Y-%m-%d %H:%M:%S')"          >> $@

again: clean all

clean:
	rm -f hello.txt
