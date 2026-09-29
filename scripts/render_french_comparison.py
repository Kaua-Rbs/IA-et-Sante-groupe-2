"""Génère le PDF français depuis le Markdown traduit et les résultats agrégés.

Dépendance documentaire facultative : reportlab==5.0.1.
À lancer depuis la racine du dépôt ; ne relance aucune expérience.
"""
import argparse
from html import escape
from pathlib import Path
import re

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle, Image

METHODS = ['baseline', 'annealing', 'tabu', 'genetic', 'hybrid', 'aco']
LABELS = ['Glouton', 'Recuit simulé', 'Tabou', 'Génétique', 'Tabou x recuit', 'ACO']


def verifier_tableaux(anglais, francais):
    """Les six tableaux de résultats doivent garder exactement les mêmes nombres."""
    for n in [7, 8, 9, 10, 11, 14]:
        nombres = []
        for texte in (anglais, francais):
            section = re.search(rf'^## {n}\. .*?(?=^## |\Z)', texte, re.M | re.S).group()
            tableau = re.search(r'^\|.*(?:\n\|.*)*', section, re.M).group()
            nombres.append(re.findall(r'\d+(?:[.,]\d+)?', tableau.replace(',', '.')))
        assert nombres[0] == nombres[1], f'Valeurs différentes dans la section {n}'


def graphique(csv, destination):
    data = pd.read_csv(csv)
    fig, axes = plt.subplots(2, 1, figsize=(7.5, 7), layout='constrained')
    for ax, taille in zip(axes, [100, 300]):
        vue = data[data.group.eq('large') & data.cases.eq(taille) & data.scenario.eq('outage')]
        moyennes = vue.groupby(['method', 'policy']).completed.mean().unstack().reindex(METHODS)
        ecarts = moyennes['reactive'] - moyennes['static']
        ecarts.index = LABELS
        ecarts.plot.bar(ax=ax, color=['#176B87' if x >= 0 else '#E79A36' for x in ecarts], rot=25)
        ax.axhline(0, color='#333333', linewidth=.8)
        ax.set_ylim(min(-.2, ecarts.min() - .4), max(.2, ecarts.max() + .4))
        for i, valeur in enumerate(ecarts):
            ax.text(i, valeur + (.06 if valeur >= 0 else -.06), f'{valeur:+.2f}'.replace('.', ','),
                    ha='center', va='bottom' if valeur >= 0 else 'top', fontsize=9)
        ax.set_title(f'{taille} cas : scénario avec fermeture temporaire')
        ax.set_ylabel('Variation des cas terminés\n(réactif - statique)')
        ax.set_xlabel('')
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, pos: f'{x:g}'.replace('.', ',')))
        ax.grid(axis='y', alpha=.2)
    fig.savefig(destination, dpi=180)
    plt.close(fig)


def rendre(texte, destination, figure):
    fonts = Path('/usr/share/fonts/truetype/dejavu')
    for nom, fichier in [('DejaVu', 'DejaVuSans.ttf'), ('DejaVu-Bold', 'DejaVuSans-Bold.ttf')]:
        pdfmetrics.registerFont(TTFont(nom, str(fonts / fichier)))
    pdfmetrics.registerFontFamily('DejaVu', normal='DejaVu', bold='DejaVu-Bold',
                                 italic='DejaVu', boldItalic='DejaVu-Bold')
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Corps', fontName='DejaVu', fontSize=9, leading=13, spaceAfter=9))
    styles.add(ParagraphStyle(name='Titre', fontName='DejaVu-Bold', fontSize=17, leading=22,
                             textColor=colors.HexColor('#124B62'), spaceAfter=17))
    styles.add(ParagraphStyle(name='Cellule', fontName='DejaVu', fontSize=7.3, leading=10))

    def enrichir(s):
        s = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', escape(s))
        return s.replace('`', '')

    sections = re.split(r'(?=^## \d+\.)', texte, flags=re.M)[1:]
    assert len(sections) == 15
    contenu = []
    for i, section in enumerate(sections):
        if i:
            contenu.append(PageBreak())
        else:
            contenu.extend([Paragraph('Métaheuristiques et Mesa', styles['Titre']),
                            Paragraph('Comparaison expérimentale | 28 septembre 2026', styles['Corps']),
                            Spacer(1, 18)])
        for bloc in section.strip().split('\n\n'):
            if bloc == '---':
                continue
            if bloc.startswith('## '):
                contenu.append(Paragraph(enrichir(bloc[3:]), styles['Titre']))
            elif bloc.startswith('!['):
                contenu.extend([Image(str(figure), width=495, height=462), Spacer(1, 12)])
            elif bloc.startswith('|'):
                lignes = [l for l in bloc.splitlines() if not re.match(r'^\|[\s|:-]+\|$', l)]
                cellules = [[Paragraph(enrichir(c.strip()), styles['Cellule'])
                             for c in l.strip('|').split('|')] for l in lignes]
                n = len(cellules[0])
                largeurs = {2: [170, 325], 3: [100, 250, 145], 4: [100, 210, 95, 90],
                            5: [110, 115, 90, 90, 90], 6: [75, 112, 77, 77, 77, 77]}[n]
                tableau = Table(cellules, colWidths=largeurs, repeatRows=1, hAlign='LEFT')
                tableau.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#DDEAF0')),
                    ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F3F6F8')]),
                    ('LEFTPADDING', (0, 0), (-1, -1), 5), ('RIGHTPADDING', (0, 0), (-1, -1), 5),
                    ('TOPPADDING', (0, 0), (-1, -1), 5), ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                ]))
                contenu.extend([tableau, Spacer(1, 12)])
            else:
                contenu.append(Paragraph(enrichir(bloc).replace('\n', ' '), styles['Corps']))

    def pied(canvas, doc):
        canvas.setFont('DejaVu', 8)
        canvas.setFillColor(colors.HexColor('#52616B'))
        canvas.drawString(50, 28, 'Métaheuristiques + Mesa | Comparaison expérimentale | 28 sept. 2026')
        canvas.drawRightString(545, 28, str(doc.page))

    destination.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(destination), pagesize=(595.28, 841.89), rightMargin=50, leftMargin=50,
                      topMargin=48, bottomMargin=48,
                      title='Métaheuristiques et Mesa : comparaison expérimentale',
                      author='IA et Santé - Groupe 2').build(contenu, onFirstPage=pied, onLaterPages=pied)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=Path('artifacts/comparison-2026-09-28/metaheuristics-mesa-comparison-fr.pdf'))
    args = parser.parse_args()
    francais = Path('docs/metaheuristics-mesa-comparison-fr.md').read_text()
    anglais = Path('docs/metaheuristics-mesa-comparison.md').read_text()
    verifier_tableaux(anglais, francais)
    figure = Path('docs/comparison-results/generated-completions-fr.png')
    graphique(Path('docs/comparison-results/runs.csv'), figure)
    rendre(francais, args.output, figure)
    print(f'Tableaux vérifiés ; PDF français généré : {args.output}')


if __name__ == '__main__':
    main()
