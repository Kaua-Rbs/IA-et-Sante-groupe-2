LATEXMK := latexmk
MAIN := main.tex

.PHONY: all clean

all:
	mkdir -p build
	$(LATEXMK) -pdf -interaction=nonstopmode -file-line-error $(MAIN)

clean:
	$(LATEXMK) -C $(MAIN)
