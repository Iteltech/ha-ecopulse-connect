<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="custom_components/ecopulse_connect/brand/dark_logo@2x.png">
    <img src="custom_components/ecopulse_connect/brand/logo@2x.png" alt="EcoPulse" width="420">
  </picture>
</p>

# EcoPulse Connect

Intégration Home Assistant du service de maintenance **EcoPulse** :

- envoie toutes les 15 minutes l'état de l'installation au serveur EcoPulse : versions HA/OS, CPU/RAM/disque, mises à jour disponibles, sauvegardes, accès à distance
- exécute les ordres validés dans le tableau de bord EcoPulse, **limités à une liste fixe**
- fournit des entités de suivi
- propose des diagnostics téléchargeables

## Installation (site client)

1. HACS → menu ⋮ → **Custom repositories** → ajouter `https://github.com/iteltech/ha-ecopulse-connect`, type **Integration**
2. Rechercher **EcoPulse Connect** dans HACS → **Download** → redémarrer Home Assistant
3. **Settings → Devices & services → Add integration → EcoPulse Connect**
4. Laisser l'URL du serveur par défaut et coller le **token du site**

Prérequis : Home Assistant 2025.5 ou plus récent

## Licence

MIT
