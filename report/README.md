# Rapport LaTeX

Les sources du rapport sont séparées par chapitre afin que les six membres de l'équipe puissent travailler en parallèle. Chaque changement doit suivre les règles de contribution décrites dans le README principal.

## Prérequis

Sous Ubuntu :

```bash
sudo apt update
sudo apt install latexmk texlive-latex-extra texlive-lang-french biber
```

L'extension VS Code **LaTeX Workshop** est facultative, mais recommandée pour la prévisualisation et la synchronisation entre le source et le PDF.

## Compilation

Depuis ce dossier :

```bash
make
```

Le document est produit dans `build/main.pdf`. Pour supprimer les fichiers générés :

```bash
make clean
```

## Organisation

- `main.tex` définit l'ordre des chapitres ;
- `preamble.tex` centralise les paquets et les réglages ;
- `sections/` contient un fichier par chapitre ou méthode ;
- `figures/` reçoit les figures reproductibles et dépourvues de données confidentielles ;
- `bibliography.bib` contient les références communes.

Le sommaire source saute du chapitre III au chapitre V après une ellipse. Le chapitre IV est donc conservé comme emplacement explicite à définir avec l'encadrement. Il ne faut pas supprimer ce chapitre ou le renommer sans valider d'abord le plan attendu.
