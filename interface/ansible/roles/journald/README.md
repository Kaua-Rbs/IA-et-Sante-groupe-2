# journald

Garde sur le serveur les journaux du système et des conteneurs, pour assurer la traçabilité demandée par le RGPD (art. 5.2 et 32) et par l'AI Act (art. 12, 19 et 26).

- **Journal persistant** (`Storage=persistent`) : les journaux survivent aux redémarrages, dans `/var/log/journal/`. Le rôle [`podman`](../podman/README.md) y envoie les logs des conteneurs (`log_driver = "journald"`) : ils ne disparaissent plus quand un conteneur est recréé, par exemple à chaque déploiement ou mise à jour automatique.
- **Rétention** : `journald_retention` (1 an par défaut), dans la limite de `journald_max_use` (8 Go) sur le disque. Si cette limite est atteinte, les entrées les plus anciennes sont supprimées plus tôt : surveiller `journalctl --disk-usage`.
- **Scellement** (`journald_seal`, activé par défaut) : toutes les 15 minutes (`journald_seal_interval`), journald signe les entrées écrites. Une modification ou une suppression d'entrées anciennes devient détectable. La clé de vérification est générée au premier déploiement et copiée sur la machine de contrôle uniquement, dans `credentials/<hôte>/journald/verification_key` (ignoré par Git). La conserver aussi hors de cette machine : sans elle, la vérification n'est plus possible.

## Consulter et vérifier

En tant que `root`, ou membre du groupe `systemd-journal` (c'est le cas de l'utilisateur `podman`) :

```bash
journalctl -t kyst-api --since today                 # API : trace d'accès, connexions
journalctl -t kyst-api -g '"auth.login_failed"'      # échecs de connexion
journalctl -t postgres -t kyst-app                   # base de données, front
journalctl _COMM=sshd                                # connexions SSH au serveur
journalctl --disk-usage                              # place occupée
journalctl --verify --verify-key="$(cat credentials/<hôte>/journald/verification_key)"  # intégrité
```

La dernière commande se lance sur le serveur, la clé étant copiée depuis la machine de contrôle le temps de la vérification.

Les journaux ne quittent pas le serveur : une copie sur une autre machine (`systemd-journal-remote`, syslog distant) protégerait aussi contre la perte du serveur.
