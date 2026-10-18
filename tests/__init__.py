"""Suite de tests du projet (executable via ``python -m unittest``).

Force le backend matplotlib ``Agg`` via ``MPLBACKEND``, sans importer
matplotlib, afin que les tests graphiques tournent sans affichage. Contient
aussi les tests du squelette de coordination ``hospital_sim``.
"""

import os

os.environ["MPLBACKEND"] = "Agg"
