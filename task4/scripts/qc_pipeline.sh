#!/usr/bin/env bash
#
# qc_pipeline.sh — bash-реализация "алгоритма оценки качества картирования"
#                  из ДЗ3 (см. блок-схему в задании):
#
#   FastQC -> minimap2 (картирование) -> samtools view (SAM->BAM)
#          -> samtools flagstat -> разбор % mapped
#          -> [ %mapped > 90% ? ]
#                 Yes: "OK"      -> переименовать/сохранить QC-отчёт
#                                -> samtools sort -> freebayes -> VCF -> Finished
#                 No : "not OK"  -> переименовать/сохранить QC-отчёт -> Finished
#
# Данные: Oxford Nanopore (MinION) WGS E. coli (SRR38921296),
#         референс E. coli K-12 MG1655 GCF_000005845.2 (NC_000913.3)
#         => используем minimap2 с пресетом "map-ont" (длинные ридов с
#            повышенным уровнем ошибок), а не "sr" (короткие illumina-риды,
#            как было в исходном черновике script.sh).
#
# Запуск (из корня репозитория task4):
#   bash scripts/qc_pipeline.sh [REFERENCE] [READS] [SAMPLE] [THREADS]
#
# По умолчанию использует уже скачанные в репозитории данные.
#
set -euo pipefail

# ----------------------------- 0. параметры ----------------------------------
REFERENCE="${1:-ncbi_dataset/ncbi_dataset/data/GCF_000005845.2/ecoli.fna}"
READS="${2:-SRR38921296.fastq/SRR38921296.fastq}"
SAMPLE="${3:-SRR38921296}"
THREADS="${4:-2}"
THRESHOLD=90                      # порог "% картированных ридов" из задания

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &> /dev/null && pwd)"
PARSE_SCRIPT="${SCRIPT_DIR}/parse_flagstat.sh"

OUTDIR="results"
LOGDIR="${OUTDIR}/logs"
mkdir -p "$OUTDIR" "$LOGDIR"

REF_BASENAME="$(basename "$REFERENCE")"
REF_NAME="${REF_BASENAME%.*}"

INDEX="${OUTDIR}/${REF_NAME}.mmi"
SAM="${OUTDIR}/${SAMPLE}.sam"
BAM="${OUTDIR}/${SAMPLE}.bam"
SORTED_BAM="${OUTDIR}/${SAMPLE}.sorted.bam"
FLAGSTAT="${OUTDIR}/${SAMPLE}.flagstat.txt"
QC_RESULT="${OUTDIR}/${SAMPLE}.qc_status.txt"
VCF="${OUTDIR}/${SAMPLE}.vcf"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "${LOGDIR}/pipeline.log"
}

require() {
    command -v "$1" >/dev/null 2>&1 || { echo "ERROR: '$1' не найден в PATH. См. инструкцию по установке инструментов в README."; exit 127; }
}

for tool in fastqc minimap2 samtools freebayes awk; do
    require "$tool"
done

log "==================================================================="
log " QC pipeline запущен"
log "   REFERENCE = $REFERENCE"
log "   READS     = $READS"
log "   SAMPLE    = $SAMPLE"
log "   THREADS   = $THREADS"
log "   THRESHOLD = ${THRESHOLD}% (порог OK/not OK)"
log "==================================================================="

# ----------------------------- 1. FastQC -------------------------------------
log "=== Шаг 1/8: FastQC (контроль качества исходных ридов) ==="
fastqc -o "$OUTDIR" "$READS" >> "${LOGDIR}/fastqc.log" 2>&1
log "FastQC отчёт сохранён в $OUTDIR/ (см. *_fastqc.html, *_fastqc.zip)"

# ------------------------ 2. Индексация референса ----------------------------
log "=== Шаг 2/8: индексация референсного генома (minimap2 -d, пресет map-ont) ==="
if [[ -f "$INDEX" ]]; then
    log "Индекс $INDEX уже существует — пропускаем построение"
else
    minimap2 -x map-ont -d "$INDEX" "$REFERENCE" >> "${LOGDIR}/minimap2_index.log" 2>&1
    log "Индекс сохранён: $INDEX"
fi

# ------------------------------ 3. Картирование -------------------------------
log "=== Шаг 3/8: картирование ридов (minimap2 -ax map-ont) ==="
minimap2 -ax map-ont -t "$THREADS" "$INDEX" "$READS" > "$SAM" 2> "${LOGDIR}/minimap2_map.log"
log "SAM сохранён: $SAM"

# ------------------------------ 4. SAM -> BAM ---------------------------------
log "=== Шаг 4/8: конвертация SAM -> BAM (samtools view) ==="
samtools view -bS -@ "$THREADS" -o "$BAM" "$SAM" 2>> "${LOGDIR}/samtools_view.log"
log "BAM сохранён: $BAM"

# -------------------------------- 5. flagstat ---------------------------------
log "=== Шаг 5/8: оценка картирования (samtools flagstat) ==="
samtools flagstat "$BAM" > "$FLAGSTAT"
log "flagstat сохранён: $FLAGSTAT"
log "--- содержимое flagstat ---"
cat "$FLAGSTAT" | tee -a "${LOGDIR}/pipeline.log"
log "---------------------------"

# ----------------------- 6. Разбор % картированных ридов ----------------------
log "=== Шаг 6/8: разбор % mapped (отдельный скрипт parse_flagstat.sh) ==="
MAPPED_PCT="$("$PARSE_SCRIPT" "$FLAGSTAT")"
log "Mapped reads: ${MAPPED_PCT}%"

# ---------------- 7. Вердикт OK/not OK + переименование/сохранение отчёта -----
log "=== Шаг 7/8: вердикт оценки качества картирования (порог ${THRESHOLD}%) ==="
if awk -v m="$MAPPED_PCT" -v t="$THRESHOLD" 'BEGIN { exit !(m > t) }'; then
    QC_STATUS="OK"
else
    QC_STATUS="not OK"
fi
echo "$QC_STATUS" > "$QC_RESULT"

if [[ "$QC_STATUS" == "OK" ]]; then
    log ">>> ${MAPPED_PCT}% > ${THRESHOLD}%  =>  Write OK"
else
    log ">>> ${MAPPED_PCT}% <= ${THRESHOLD}%  =>  Write not OK"
fi

STATUS_TAG="${QC_STATUS// /_}"                       # "OK" / "not_OK"
RENAMED_REPORT="${OUTDIR}/${SAMPLE}.flagstat.${STATUS_TAG}.txt"
cp "$FLAGSTAT" "$RENAMED_REPORT"
log "QC-отчёт переименован и сохранён как: $RENAMED_REPORT"
log "Статус записан в: $QC_RESULT  (содержимое: '$QC_STATUS')"

# --------------- 8. Сортировка + вызов вариантов (только если OK) -------------
if [[ "$QC_STATUS" == "OK" ]]; then
    log "=== Шаг 8/8: QC = OK -> сортировка BAM и вызов вариантов FreeBayes ==="

    log "-- samtools sort --"
    samtools sort -@ "$THREADS" -o "$SORTED_BAM" "$BAM" 2>> "${LOGDIR}/samtools_sort.log"
    samtools index "$SORTED_BAM"
    log "Отсортированный BAM сохранён: $SORTED_BAM"

    log "-- freebayes (вызов генетических вариантов) --"
    freebayes -f "$REFERENCE" "$SORTED_BAM" > "$VCF" 2> "${LOGDIR}/freebayes.log"
    log "VCF сохранён: $VCF"
else
    log "=== Шаг 8/8: QC = not OK -> сортировка и вызов вариантов ПРОПУЩЕНЫ ==="
    log "    (по алгоритму вариант-коллинг выполняется только при успешном QC)"
fi

log "==================================================================="
log " Finished. QC verdict = '${QC_STATUS}', mapped = ${MAPPED_PCT}%"
log " Результаты: $OUTDIR/   Логи: $LOGDIR/"
log "==================================================================="

echo ""
echo "ИТОГ: ${QC_STATUS}  (mapped = ${MAPPED_PCT}%, порог = ${THRESHOLD}%)"
