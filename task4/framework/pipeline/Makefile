# ============================================================================
#  Makefile — пайплайн "Оценка качества картирования и вызов вариантов" (HW3)
#  Фреймворк: GNU Make ("старая школа" построения пайплайнов)
#
#  Реализует тот же алгоритм, что и scripts/qc_pipeline.sh, но декларативно:
#  каждый шаг — это правило "целевой файл: файлы-зависимости" + рецепт.
#  Make сам строит граф зависимостей (DAG) и запускает только то, что
#  устарело или отсутствует (см. README.md, раздел про визуализацию DAG).
#
#  Запуск (из этой директории):
#    make help     — список целей
#    make          — собрать всё (по умолчанию: цель `all`)
#    make qc       — выполнить только до вердикта OK/not OK
#    make clean    — удалить результаты
#
#  Параметры можно переопределить, например:
#    make THRESHOLD=95 THREADS=4
# ============================================================================

SHELL := /bin/bash

# ---------------------------- параметры пайплайна ---------------------------
REFERENCE ?= ../../ncbi_dataset/ncbi_dataset/data/GCF_000005845.2/ecoli.fna
READS     ?= ../../SRR38921296.fastq/SRR38921296.fastq
SAMPLE    ?= SRR38921296
THREADS   ?= 2
THRESHOLD ?= 90

PARSE_SCRIPT := ../../scripts/parse_flagstat.sh

OUTDIR := results
LOGDIR := $(OUTDIR)/logs

REF_NAME := $(basename $(notdir $(REFERENCE)))

INDEX       := $(OUTDIR)/$(REF_NAME).mmi
SAM         := $(OUTDIR)/$(SAMPLE).sam
BAM         := $(OUTDIR)/$(SAMPLE).bam
SORTED_BAM  := $(OUTDIR)/$(SAMPLE).sorted.bam
FLAGSTAT    := $(OUTDIR)/$(SAMPLE).flagstat.txt
QC_STATUS   := $(OUTDIR)/$(SAMPLE).qc_status.txt
VCF         := $(OUTDIR)/$(SAMPLE).vcf
FASTQC_DONE := $(OUTDIR)/.fastqc.done

.PHONY: all fastqc qc clean help dirs
.DELETE_ON_ERROR:

# ----------------------------------------------------------------------------
all: $(VCF) qc            ## собрать весь пайплайн (выполнит вариант-коллинг, если QC == OK)

help:                     ## показать список целей с описанием
	@echo "Доступные цели:"
	@grep -E '^[a-zA-Z_-]+:.*##' $(MAKEFILE_LIST) | sed -E 's/^([a-zA-Z_-]+):.*## ?/  \1 -- /'
	@echo ""
	@echo "Параметры (переопределяются через make VAR=значение):"
	@echo "  REFERENCE=$(REFERENCE)"
	@echo "  READS=$(READS)"
	@echo "  SAMPLE=$(SAMPLE)  THREADS=$(THREADS)  THRESHOLD=$(THRESHOLD)"

dirs:
	mkdir -p $(OUTDIR) $(LOGDIR)

# ------------------------------- 1. FastQC ----------------------------------
fastqc: $(FASTQC_DONE)    ## контроль качества исходных ридов (FastQC)

$(FASTQC_DONE): $(READS) | dirs
	fastqc -o $(OUTDIR) $(READS) > $(LOGDIR)/fastqc.log 2>&1
	touch $@

# ----------------------- 2. индексация референса ----------------------------
$(INDEX): $(REFERENCE) | dirs
	minimap2 -x map-ont -d $@ $< > $(LOGDIR)/minimap2_index.log 2>&1

# --------------------------- 3. картирование --------------------------------
$(SAM): $(INDEX) $(READS)
	minimap2 -ax map-ont -t $(THREADS) $(INDEX) $(READS) > $@ 2> $(LOGDIR)/minimap2_map.log

# ----------------------------- 4. SAM -> BAM --------------------------------
$(BAM): $(SAM)
	samtools view -bS -@ $(THREADS) -o $@ $< 2> $(LOGDIR)/samtools_view.log

# ------------------------------- 5. flagstat --------------------------------
$(FLAGSTAT): $(BAM)
	samtools flagstat $< > $@
	@echo "----- $(FLAGSTAT) -----"; cat $@; echo "-----------------------"

# -------------------- 6-7. разбор % mapped + вердикт OK/not OK --------------
$(QC_STATUS): $(FLAGSTAT) $(PARSE_SCRIPT)
	pct=$$($(PARSE_SCRIPT) $(FLAGSTAT)); \
	echo "Mapped reads: $$pct%  (порог $(THRESHOLD)%)"; \
	if awk -v m="$$pct" -v t=$(THRESHOLD) 'BEGIN{exit !(m > t)}'; then \
	    status="OK"; \
	else \
	    status="not OK"; \
	fi; \
	echo "$$status" > $@; \
	echo ">>> Вердикт: $$status"; \
	tag=$$(echo "$$status" | tr ' ' '_'); \
	cp $(FLAGSTAT) $(OUTDIR)/$(SAMPLE).flagstat.$${tag}.txt; \
	echo "QC-отчёт переименован и сохранён: $(OUTDIR)/$(SAMPLE).flagstat.$${tag}.txt"

qc: $(QC_STATUS)          ## вывести вердикт OK / not OK
	@echo "QC verdict: $$(cat $(QC_STATUS))"

# ------------------------- 8a. сортировка BAM -------------------------------
$(SORTED_BAM): $(BAM)
	samtools sort -@ $(THREADS) -o $@ $< 2> $(LOGDIR)/samtools_sort.log
	samtools index $@

# ------------------- 8b. вызов вариантов (только если QC == OK) -------------
$(VCF): $(SORTED_BAM) $(QC_STATUS) $(REFERENCE)
	status=$$(cat $(QC_STATUS)); \
	if [ "$$status" = "OK" ]; then \
	    echo "QC = OK -> запускаем freebayes"; \
	    freebayes -f $(REFERENCE) $(SORTED_BAM) > $@ 2> $(LOGDIR)/freebayes.log; \
	    echo "Варианты записаны в $@"; \
	else \
	    echo "QC = '$$status' (порог $(THRESHOLD)%) -> вызов вариантов пропущен" | tee $@; \
	fi

clean:                
	rm -rf $(OUTDIR)
