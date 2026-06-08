#!/usr/bin/env bash
#
# parse_flagstat.sh — извлекает общий % картированных (mapped) ридов
#                     из вывода `samtools flagstat`.
#
# Зачем отдельным скриптом: пункт задания требует отдельный "скрипт разбора
# результатов samtools flagstat для получения % картированных ридов",
# независимый от основного пайплайна — его можно использовать как
# самостоятельно (для любого .txt с результатом flagstat), так и вызывать
# из qc_pipeline.sh / Makefile.
#
# Использование:
#   ./parse_flagstat.sh <flagstat_output.txt>
#
# Вывод (stdout): одно число — процент картированных ридов, без знака '%'
#   например: 99.83
#
# Пример строки, которую мы ищем в выводе samtools flagstat:
#   1097662 + 0 mapped (99.83% : N/A)
#
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo "Использование: $0 <flagstat_output.txt>" >&2
    exit 2
fi

FILE="$1"

if [[ ! -f "$FILE" ]]; then
    echo "ERROR: файл не найден: $FILE" >&2
    exit 1
fi

LINE=$(grep -m1 -E '^[0-9]+ \+ [0-9]+ mapped \(' "$FILE" || true)

if [[ -z "$LINE" ]]; then
    echo "ERROR: в файле '$FILE' не найдена строка вида 'N + N mapped (XX.XX% ...)'." >&2
    echo "Похоже, это не стандартный вывод samtools flagstat." >&2
    exit 1
fi

PCT=$(echo "$LINE" | sed -E 's/.*\(([0-9]+(\.[0-9]+)?)%.*/\1/')

if [[ -z "$PCT" ]]; then
    echo "ERROR: не удалось распарсить процент из строки: $LINE" >&2
    exit 1
fi

echo "$PCT"
