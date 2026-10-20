# podman

Installe Podman et le configure pour l'utilisateur `podman`, sans droits root : plages `subuid`/`subgid`, session systemd utilisateur, logs des conteneurs envoyés au journal (`log_driver = "journald"`, voir le rôle [`journald`](../journald/README.md)) et timer `podman-image-prune` qui supprime les anciennes images.

Le rôle [`kyst`](../kyst/README.md) en dépend et en donne un exemple d'utilisation.
