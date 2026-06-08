#!/usr/bin/env python3
"""
make2dot.py — строит граф зависимостей (DAG) GNU Make из его собственной
              отладочной трассировки и сохраняет его в формате Graphviz DOT.


Источник графа — встроенный (родной для GNU Make) безопасный режим трассировки:

    make -Bnd <цель>
        -B  --always-make   считать все цели устаревшими (полный граф, а не
                            только "то, что реально нужно пересобрать сейчас")
        -n  --just-print    НИЧЕГО не выполнять — только показать, что было бы
                            выполнено (поэтому minimap2/samtools/freebayes и
                            прочие внешние программы не запускаются)
        -d  --debug         подробный отладочный вывод, в т.ч. строки вида
                            "Considering target file 'X'." с отступами,
                            которые как раз и кодируют дерево зависимостей.

Использование:
    make -Bnd all 2>/dev/null | python3 make2dot.py > dag.dot
    dot -Tpng dag.dot -o dag.png

Или одной командой:
    python3 make2dot.py --make-target all --out dag

"""
import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CONSIDER_RE = re.compile(r"^(?P<indent>\s*)Considering target file '(?P<name>.+)'\.$")
REMAKE_RE = re.compile(r"^(?P<indent>\s*)Must remake target '(?P<name>.+)'\.$")
PHONY = {"all", "qc", "fastqc", "dirs", "clean", "help"}


def find_pipeline_dir() -> Path:
    here = Path(__file__).resolve().parent
    candidates = [here.parent, here, here.parent.parent]
    for c in candidates:
        if (c / "Makefile").is_file():
            return c
    return here.parent


def run_make_trace(make_target: str, makefile_dir: Path):
    env = dict(os.environ)
    env["LANG"] = "C"
    env["LC_ALL"] = "C"
    env["LC_MESSAGES"] = "C"

    proc = subprocess.run(
        ["make", "-Bnd", make_target],
        cwd=str(makefile_dir),
        capture_output=True, text=True, env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def parse_trace(lines):
    nodes = []
    edges = []
    rebuilt = set()
    stack = []  

    for raw in lines:
        m = CONSIDER_RE.match(raw)
        if m:
            indent = len(m.group("indent"))
            name = m.group("name")
            while stack and stack[-1][0] >= indent:
                stack.pop()
            if stack:
                parent = stack[-1][1]
                edges.append((parent, name))
            nodes.append(name)
            stack.append((indent, name))
            continue

        m = REMAKE_RE.match(raw)
        if m:
            rebuilt.add(m.group("name"))

    return nodes, edges, rebuilt


def short_label(name: str) -> str:
    base = Path(name).name
    if name.startswith("../") or "/" in name:
        return base
    return name


def node_style(name: str) -> str:
    if name in PHONY:
        return 'shape=ellipse, style=filled, fillcolor="#FFE9A8"'  # phony-цели
    if name.endswith((".fna", ".fastq", ".fa")) or "ncbi_dataset" in name or "SRR" in name and name.endswith(".fastq"):
        return 'shape=note, style=filled, fillcolor="#D6EAF8"'      # исходные данные
    if name.endswith(".vcf"):
        return 'shape=box, style="filled,bold", fillcolor="#ABEBC6"'  # финальный результат
    if name.endswith((".sh",)) or name == "Makefile":
        return 'shape=component, style=filled, fillcolor="#E8DAEF"'   # скрипты/сама сборка
    return 'shape=box, style=filled, fillcolor="#F2F3F4"'             # промежуточные файлы


def to_dot(nodes, edges, rebuilt, title="QC & variant-calling pipeline (GNU Make DAG)"):
    seen = set()
    out = []
    out.append("digraph make_dag {")
    out.append('  rankdir=LR;')
    out.append(f'  label="{title}\\n(сгенерировано из `make -Bnd` через make2dot.py)";')
    out.append('  labelloc="t"; fontsize=16;')
    out.append('  node [fontname="Helvetica", fontsize=11];')
    out.append('  edge [color="#5D6D7E"];')

    for n in nodes:
        if n in seen:
            continue
        seen.add(n)
        label = short_label(n)
        style = node_style(n)
        penwidth = ', penwidth=2, color="#1A5276"' if n in rebuilt else ""
        out.append(f'  "{n}" [label="{label}", {style}{penwidth}];')

    seen_edges = set()
    for parent, child in edges:
        if (parent, child) in seen_edges:
            continue
        seen_edges.add((parent, child))
        # рисуем стрелку от зависимости к цели (т.е. "что строится из чего"),
        # это совпадает с направлением потока данных в блок-схеме алгоритма
        out.append(f'  "{child}" -> "{parent}";')

    out.append("}")
    return "\n".join(out)


def _dump_diagnostics(lines, limit=25):
    print("--- первые строки трассировки make (для диагностики) ---", file=sys.stderr)
    for l in lines[:limit]:
        print(f"    {l}", file=sys.stderr)
    print("--- конец фрагмента ---", file=sys.stderr)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--make-target", default="all", help="цель make для трассировки (по умолчанию: all)")
    ap.add_argument("--out", default="dag", help="имя выходных файлов без расширения (out.dot, out.png)")
    ap.add_argument("--makefile-dir", default=None,
                    help="каталог с Makefile (по умолчанию определяется автоматически)")
    ap.add_argument("--from-stdin", action="store_true",
                    help="не запускать make самостоятельно, читать трассировку из stdin "
                         "(удобно вместе с `make -Bnd all > trace.txt` + `... < trace.txt`)")
    args = ap.parse_args()

    if args.from_stdin:
        lines = sys.stdin.read().splitlines()
    else:
        makefile_dir = Path(args.makefile_dir) if args.makefile_dir else find_pipeline_dir()
        if not (makefile_dir / "Makefile").is_file():
            print(f"ОШИБКА: в каталоге '{makefile_dir}' не найден файл Makefile.", file=sys.stderr)
            print("Укажите каталог явно: --makefile-dir /путь/к/framework/pipeline", file=sys.stderr)
            sys.exit(1)

        print(f"Запускаю: make -Bnd {args.make_target}   (рабочий каталог: {makefile_dir})")
        rc, out, err = run_make_trace(args.make_target, makefile_dir)
        lines = out.splitlines()

        if rc != 0:
            print(f"ОШИБКА: `make -Bnd {args.make_target}` завершился с кодом {rc}.", file=sys.stderr)
            print("Скорее всего, неверный --make-target или Makefile в другом месте. Сообщение make:", file=sys.stderr)
            print(f"    {err.strip().splitlines()[-1] if err.strip() else '(make ничего не написал в stderr)'}", file=sys.stderr)
            print("Доступные цели смотрите через `make help` в каталоге Makefile.", file=sys.stderr)
            sys.exit(1)

    nodes, edges, rebuilt = parse_trace(lines)

    if not nodes:
        print("ВНИМАНИЕ: не нашлось ни одной строки 'Considering target file ...' — граф пуст.", file=sys.stderr)
        print("Самые частые причины:", file=sys.stderr)
        print("  1) другая версия GNU Make печатает отладочные строки в ином формате;", file=sys.stderr)
        print("  2) системная локаль переводит сообщения make на другой язык", file=sys.stderr)
        print("     (мы уже принудительно просим LANG=C/LC_ALL=C для вызова make,", file=sys.stderr)
        print("     но если вы передаёте трассировку через --from-stdin — соберите", file=sys.stderr)
        print("     её сами командой `LANG=C LC_ALL=C make -Bnd all > trace.txt`);", file=sys.stderr)
        print("  3) make запущен не в том каталоге / не нашёл Makefile.", file=sys.stderr)
        _dump_diagnostics(lines)
        sys.exit(1)

    dot_src = to_dot(nodes, edges, rebuilt)

    dot_path = Path(f"{args.out}.dot")
    dot_path.write_text(dot_src, encoding="utf-8")
    print(f"DOT-файл записан: {dot_path}  (узлов: {len(set(nodes))}, рёбер: {len(set(edges))})")

    render_png(dot_path, Path(f"{args.out}.png"))


def render_png(dot_path: Path, png_path: Path):
    dot_bin = shutil.which("dot")
    if dot_bin is None:
        print(f"DOT-файл готов: {dot_path}", file=sys.stderr)
        print("PNG не собран: программа `dot` (Graphviz) не найдена в PATH.", file=sys.stderr)
        print("Сам граф это не портит — dag.dot можно открыть и так "
              "(например, через https://dreampuf.github.io/GraphvizOnline/ "
              "или расширение Graphviz Preview в VS Code).", file=sys.stderr)
        print("", file=sys.stderr)
        print("Установка Graphviz:", file=sys.stderr)
        print("  Ubuntu/Debian : sudo apt-get install -y graphviz", file=sys.stderr)
        print("  Fedora/RHEL   : sudo dnf install -y graphviz", file=sys.stderr)
        print("  macOS         : brew install graphviz", file=sys.stderr)
        print("  Windows       : winget install --id Graphviz.Graphviz -e", file=sys.stderr)
        print("                  (или скачать инсталлятор: https://graphviz.org/download/)", file=sys.stderr)
        print("                  При установке отметьте опцию 'Add Graphviz to the system PATH'.", file=sys.stderr)
        print("                  Если этого не было — добавьте вручную в PATH каталог вида", file=sys.stderr)
        print(r"                  C:\Program Files\Graphviz\bin  и откройте новый терминал.", file=sys.stderr)
        return

    try:
        subprocess.run([dot_bin, "-Tpng", str(dot_path), "-o", str(png_path)], check=True,
                       capture_output=True, text=True)
        print(f"PNG-картинка собрана: {png_path}  (через {dot_bin})")
    except subprocess.CalledProcessError as e:
        print(f"`dot` найден ({dot_bin}), но завершился с ошибкой при рендеринге:", file=sys.stderr)
        print(e.stderr or e, file=sys.stderr)


if __name__ == "__main__":
    main()
