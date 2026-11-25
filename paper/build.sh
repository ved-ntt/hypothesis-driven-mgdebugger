#!/usr/bin/env bash
# Build paper.pdf from paper.md (pandoc + xelatex). lmodern is not installed everywhere, so the line
# that loads it is dropped; the font is TeX Gyre Termes.
set -e
cd "$(dirname "$0")"
pandoc paper.md -s -o paper.tex
sed -i '/\\usepackage{lmodern}/d' paper.tex
xelatex -interaction=nonstopmode paper.tex > /dev/null
rm -f paper.aux paper.log paper.out
echo "paper.pdf built"
