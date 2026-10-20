# Déploiement Ansible

Playbooks et rôles qui installent KYST sur un serveur Linux à base Debian (paquets `apt`) : conteneurs Podman sans droits root, pare-feu, journalisation. L'instance de démonstration [kyst.tech](https://kyst.tech) est déployée ainsi.

## Rôles

Le playbook [`deploy-server.yml`](playbooks/deploy-server.yml) applique, dans l'ordre :

| Rôle | Rôle sur le serveur |
| :--- | :--- |
| `common` | Paquets de base, bannière de connexion (MOTD) |
| [`journald`](roles/journald/README.md) | Journal persistant, rétention d'un an, scellement : traçabilité RGPD |
| `firewall` | Règles `iptables` assemblées à partir de fragments, politique `INPUT DROP` |
| [`podman`](roles/podman/README.md) | Podman sans droits root pour l'utilisateur `podman` |
| [`kyst`](roles/kyst/README.md) | API, front et PostgreSQL ; images, modèles, mises à jour automatiques, données de démonstration |

Le playbook [`create-ansible-user.yml`](playbooks/create-ansible-user.yml) prépare un nouveau serveur.

## Prérequis

Sur la machine qui lance les playbooks :

- Python 3.13 et [`uv`](https://docs.astral.sh/uv/) : les dépendances sont déclarées dans [`pyproject.toml`](pyproject.toml) et verrouillées dans `uv.lock` ;
- [`just`](https://just.systems/man/en/), pour les recettes ci-dessous ;
- `lolcat` (version Ruby ou C), pour colorer la bannière (le texte vient de `pyfiglet`, installé dans l'environnement) ;
- les modèles entraînés dans `artifacts/ml-models/` à la racine du dépôt (voir le [rôle `kyst`](roles/kyst/README.md#déployer)).

Sur les serveurs gérés : un compte `ansible` avec `sudo` sans mot de passe, créé par `just playbook-create-ansible-user`. L'inventaire est dans [`hosts`](hosts) (modèle : [`hosts.example`](hosts.example)).

Les secrets générés au premier déploiement sont gardés sur la machine de contrôle, dans `credentials/<hôte>/` (ignoré par Git).

## Utilisation

| Recette | Rôle |
| :--- | :--- |
| `just` | Liste les recettes |
| `just playbook-deploy-infra` | Lance le playbook principal ; les arguments sont transmis à `ansible-playbook` (ex. `-e kyst_version=1.2.0`) |
| `just playbook-create-ansible-user` | Crée le compte `ansible` sur un nouveau serveur |
| `just lint` | Vérifie les playbooks et rôles avec `ruff` et [ansible-lint](https://ansible.readthedocs.io/projects/lint/) |
| `just todo` | Cherche les commentaires `TODO` et `noqa` |
| `just venv` | Crée l'environnement `.venv` et installe les dépendances |

L'extension VS Code [Ansible](https://marketplace.visualstudio.com/items?itemName=redhat.ansible) est recommandée. Documentation : [Ansible](https://docs.ansible.com/ansible/latest/index.html), [liste des modules](https://docs.ansible.com/ansible/latest/collections/all_plugins.html).
