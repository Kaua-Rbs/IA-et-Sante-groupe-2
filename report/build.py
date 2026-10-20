#!/usr/bin/env python3
"""Build the report without modifying project sources or datasets."""

import argparse
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
OUTPUT = ROOT.parent / "output" / "pdf" / "rapport-fil-rouge.pdf"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--engine", choices=("auto", "latexmk", "pdflatex", "tectonic"), default="auto"
    )
    parser.add_argument("--tectonic", help="Explicit path to Tectonic")
    args = parser.parse_args()

    tectonic = args.tectonic or shutil.which("tectonic")
    bundled = Path("/usr/lib/chatgpt/resources/tectonic/tectonic")
    if not tectonic and bundled.is_file():
        tectonic = str(bundled)
    engines = {
        "latexmk": shutil.which("latexmk"),
        "pdflatex": shutil.which("pdflatex"),
        "tectonic": tectonic,
    }
    engine = args.engine
    if engine == "auto":
        engine = next((name for name, path in engines.items() if path), None)
    if not engine or not engines.get(engine):
        parser.error("Install latexmk and a TeX distribution, or Tectonic.")
    if engine == "pdflatex" and not shutil.which("bibtex"):
        parser.error("BibTeX is required when using pdfLaTeX.")

    BUILD.mkdir(exist_ok=True)
    for pattern in ("*.tex", "*.bib", "*.cls", "*.bst"):
        for source in ROOT.glob(pattern):
            shutil.copy2(source, BUILD / source.name)
    for directory in ("sections", "tables", "figures"):
        if (ROOT / directory).is_dir():
            shutil.copytree(ROOT / directory, BUILD / directory, dirs_exist_ok=True)
    # Avoid mixing auxiliary files from different engines.
    engine_file = BUILD / ".engine"
    if engine_file.exists() and engine_file.read_text() != engine:
        for suffix in ("aux", "bbl", "blg", "out", "fdb_latexmk", "fls"):
            (BUILD / f"main.{suffix}").unlink(missing_ok=True)
    engine_file.write_text(engine)

    def run(command):
        subprocess.run(command, cwd=BUILD, check=True)

    executable = engines[engine]
    if engine == "tectonic":
        run([executable, "--keep-logs", "--keep-intermediates", "main.tex"])
    elif engine == "latexmk":
        run([executable, "-pdf", "-interaction=nonstopmode", "-halt-on-error", "main.tex"])
    else:
        command = [executable, "-interaction=nonstopmode", "-halt-on-error", "main.tex"]
        run(command)
        run([shutil.which("bibtex"), "main"])
        run(command)
        run(command)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(BUILD / "main.pdf", OUTPUT)
    print(f"PDF: {OUTPUT}")


if __name__ == "__main__":
    main()
