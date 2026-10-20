# soutenance

Présentations du projet, en LaTeX Beamer avec le thème `midcenturymodern` (`beamerthememidcenturymodern.sty`).

## Compiler

Depuis ce dossier, avec LuaLaTeX (requis par le thème) et `biber` (voir les paquets listés dans [report/README.md](../report/README.md)) :

```bash
lualatex Soutenance_intermediaire
biber    Soutenance_intermediaire
lualatex Soutenance_intermediaire
lualatex Soutenance_intermediaire
```

Les chiffres présentés viennent de la documentation du projet : [modèles de prédiction](../docs/modeles-prediction.md) et [intégration dans KYST](../docs/integration-ia-kyst.md). Les termes employés sont définis dans le [glossaire](../docs/glossaire.md).
