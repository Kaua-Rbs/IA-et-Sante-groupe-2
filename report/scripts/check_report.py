#!/usr/bin/env python3
"""Check article structure, citations, pinned sources and included figures."""
from pathlib import Path
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
SECTIONS = [
    'Introduction', 'Literature Review', 'Problem Description',
    'Mathematical Formulation', 'Proposed Hybrid Optimization Approach',
    'Experimental Design', 'Computational Results',
    'Discussion and Managerial Insights', 'Conclusion', 'References',
]


def expand(path):
    # Ignore commented examples; only active inputs belong to the article.
    source = re.sub(r'(?<!\\)%[^\n]*', '', path.read_text())
    return re.sub(r'\\input\{([^}]+)\}',
                  lambda m: expand(ROOT / (m.group(1) + '.tex')), source)


def main():
    article = expand(ROOT / 'main.tex')
    assert re.findall(r'\\section\{([^}]+)\}', article) == SECTIONS
    assert '\\setcounter{section}{1}' in article and '\\appendix' not in article
    labels = re.findall(r'\\label\{([^}]+)\}', article)
    assert len(labels) == len(set(labels)), 'Duplicate labels'
    references = set(re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', article))
    assert not references - set(labels), f'Unknown labels: {references - set(labels)}'
    citations = {key.strip() for keys in re.findall(r'\\cite\w*\{([^}]+)\}', article)
                 for key in keys.split(',')}
    entries = re.findall(r'@\w+\{([^,]+)', (ROOT / 'bibliography.bib').read_text())
    assert len(entries) == len(set(entries)), 'Duplicate bibliography keys'
    assert citations == set(entries), 'Missing or unused bibliography entries'
    abstract = article.split('\\begin{abstract}')[1].split('\\end{abstract}')[0]
    assert 150 <= len(abstract.split()) <= 250
    keywords = article.split('\\begin{keyword}')[1].split('\\end{keyword}')[0]
    assert 4 <= len(keywords.split('\\sep')) <= 6
    contributions = ROOT / 'contributions'
    count = 0
    for group, record in json.loads((contributions / 'manifest.json').read_text()).items():
        for entry in record['files']:
            path = contributions / group / entry['path']
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], path
            count += 1
    room = contributions / 'room-study'
    for name, record in json.loads((room / 'manifest.json').read_text())['files'].items():
        assert hashlib.sha256((room / name).read_bytes()).hexdigest() == record['sha256'], name
        count += 1
    for relative in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}', article):
        assert (ROOT / relative).is_file(), relative
    print(f'11 outline items, {len(entries)} cited references, {count} pinned input hashes: OK')


if __name__ == '__main__':
    main()
