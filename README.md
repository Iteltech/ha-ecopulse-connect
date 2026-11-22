<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/ecopulse_connect/brand/dark_logo@2x.png">
    <img src="custom_components/ecopulse_connect/brand/logo@2x.png" alt="EcoPulse" width="420">
  </picture>
</p>

# EcoPulse Connect

Intégration Home Assistant du service de maintenance **EcoPulse**. Elle remplace le package YAML `fleet_telemetry.yaml` :

- envoie toutes les 15 minutes (et au démarrage) l'état de l'installation au serveur EcoPulse : versions HA/OS, CPU/RAM/disque, mises à jour disponibles, sauvegardes, accès à distance (Nabu Casa / URL externe) ;
- exécute les ordres validés dans le tableau de bord EcoPulse, **limités à une liste fixe** : installer une mise à jour, redémarrer Home Assistant, redémarrer l'hôte ;
- fournit des entités de suivi : *Dernier heartbeat*, *Dernier ordre*, *Serveur* (joignable), bouton *Envoyer la télémétrie* ;
- propose des diagnostics téléchargeables (token masqué).

Aucun accès entrant n'est ouvert : c'est Home Assistant qui contacte le serveur.

## Installation (site client)

1. HACS → menu ⋮ → **Custom repositories** → ajouter `https://github.com/iteltech/ha-ecopulse-connect`, type **Integration**.
2. Rechercher **EcoPulse Connect** dans HACS → **Download** → redémarrer Home Assistant.
3. **Settings → Devices & services → Add integration → EcoPulse Connect**.
4. Laisser l'URL du serveur par défaut et coller le **token du site** (affiché une seule fois à la création du site dans le tableau de bord).

Prérequis : Home Assistant 2025.5 ou plus récent. L'intégration *System Monitor* est utilisée si elle est présente ; sinon les mesures CPU/RAM/disque sont lues directement.

## Mises à jour d'EcoPulse Connect

HACS crée l'entité `update.ecopulse_connect_update` sur chaque site. Elle remonte dans le tableau de bord comme n'importe quelle autre mise à jour : on la qualifie, puis on la promeut groupe par groupe (Qualification → Bêta → Clients) avec le même mécanisme que pour Home Assistant Core ou les add-ons. Après l'installation, envoyer un ordre **Redémarrer** au site (HACS le demande pour charger la nouvelle version) ; le tableau de bord affiche alors la nouvelle version de l'agent.

### Publier une version

1. Modifier le code, puis passer `version` dans `custom_components/ecopulse_connect/manifest.json` (ex. `0.2.0`).
2. Commit + push : le workflow *Validate* exécute hassfest, la validation HACS et les tests.
3. GitHub → **Releases → Draft a new release** → tag `v0.2.0` → **Publish**. Le workflow *Release* joint `ecopulse_connect.zip` (version du manifest alignée sur le tag).
4. Dans les heures qui suivent (ou après *Update information* dans HACS), chaque site voit la mise à jour.

Pour une version de test réservée au groupe Qualification, publier la release en **pre-release** : seuls les sites où l'option *Show beta versions* est activée dans HACS la verront.

## Développement

```bash
python -m venv .venv && . .venv/bin/activate
pip install pytest-homeassistant-custom-component
pytest -q
```

## Protocole (résumé)

`POST <url>` avec `Authorization: Bearer <token>` et un corps JSON :

| `type` | Usage | Réponse |
|---|---|---|
| *(absent)* | télémétrie | `{"status":"ok","command":…}` (ordre ou `null`) |
| `result` | résultat d'un ordre : `id`, `status` (`started`/`done`/`failed`/`rejected`), `message` | `{"status":"ok"}` |
| `probe` | test du token pendant la configuration | `{"status":"ok"}` |

La télémétrie inclut `agent: {"name":"ecopulse_connect","version":"x.y.z"}`.

## Licence

MIT
