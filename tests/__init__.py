"""Suite de tests du projet (executable via ``python -m unittest``).

Force le backend matplotlib ``Agg`` avant tout import de ``pyplot`` afin que
les tests graphiques tournent sans affichage.
"""

import matplotlib

matplotlib.use("Agg")
