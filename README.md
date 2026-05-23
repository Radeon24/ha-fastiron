# ha-fastiron

Intégration Home Assistant pour les switches **Ruckus/Brocade ICX** sous **FastIron 9**.

Testée sur : ICX7250-48P / FastIron 09.0.10kT213.

## Fonctionnalités

- **Autodécouverte** des ports au premier ajout (compatible tous modèles ICX, avec ou sans PoE)
- **Binary sensors** : état de liaison physique par port (up/down)
- **Sensors** : vitesse, octets RX/TX, paquets RX/TX, erreurs RX/TX, discards RX/TX, erreurs FCS, consommation PoE, PoE alloué, température switch
- **Switches** : activation/désactivation admin d'un port, activation/désactivation PoE par port
- **Bouton** : redémarrage du switch

## Installation

### Via HACS (recommandé)

1. Ajouter ce dépôt comme dépôt personnalisé dans HACS (type : Intégration)
2. Installer "Ruckus/Brocade FastIron"
3. Redémarrer Home Assistant

### Manuelle

Copier le dossier `custom_components/fastiron/` dans ton dossier `custom_components/` de Home Assistant, puis redémarrer.

## Configuration côté switch

### 1. Activer l'API RESTCONF HTTPS

Connecte-toi au switch en SSH ou console, puis :

```
configure terminal

! Activer le serveur web HTTPS
ip http secure-server

! Désactiver HTTP non sécurisé (recommandé)
no ip http server

! Configurer l'authentification AAA pour l'accès web et RESTCONF
aaa authentication web-server default local

! Créer un compte dédié pour Home Assistant
! IMPORTANT : privilege 0 (super-user) est obligatoire pour l'accès RESTCONF.
! Les autres niveaux de privilège ne sont PAS synchronisés vers la base RESTCONF.
! (remplacer <password> par un mot de passe fort)
username homeassistant privilege 0 password <password>

! Activer RESTCONF
restconf enable
restconf enable-config-sync

end
write memory
```

> **Important** : Après activation de RESTCONF, patienter **10 minutes** pour que la
> synchronisation initiale de configuration s'effectue (`Config Sync Pass` doit passer à 1
> dans `show restconf status`). Seuls les comptes avec `privilege 0` sont synchronisés vers
> la base RESTCONF.

> **Important** : Seul `privilege 0` fonctionne avec RESTCONF. Les autres niveaux (`privilege 4`,
> `privilege 5`, etc.) ne sont pas synchronisés vers la base RESTCONF et retournent 401.

### 2. Vérifier que l'API RESTCONF répond

Depuis un poste ayant accès au switch :

```bash
curl -k -u homeassistant:<password> \
  -H "Accept: application/yang-data+json" \
  https://<ip-switch>/restconf/data/interfaces
```

Une réponse JSON avec la liste des interfaces confirme que l'API est opérationnelle.

### 3. Ajouter l'intégration dans Home Assistant

Dans Home Assistant : **Paramètres → Appareils et services → Ajouter une intégration → FastIron**

Renseigner :
- **Adresse IP** du switch
- **Port** : 443 (par défaut)
- **Nom d'utilisateur** et **Mot de passe** créés ci-dessus
- **Vérifier le certificat SSL** : laisser décoché si le switch utilise un certificat auto-signé (cas standard)

## Entités créées

Pour chaque port découvert, les entités suivantes sont créées :

| Type | Nom | Description |
|------|-----|-------------|
| `binary_sensor` | Port X liaison | Liaison physique up/down |
| `sensor` | Port X vitesse | Vitesse négociée en Mbit/s |
| `sensor` | Port X octets reçus | Compteur cumulatif RX |
| `sensor` | Port X octets envoyés | Compteur cumulatif TX |
| `sensor` | Port X paquets reçus | Compteur paquets RX |
| `sensor` | Port X paquets envoyés | Compteur paquets TX |
| `sensor` | Port X erreurs RX | Compteur erreurs RX |
| `sensor` | Port X erreurs TX | Compteur erreurs TX |
| `sensor` | Port X discards RX | Compteur paquets rejetés RX |
| `sensor` | Port X discards TX | Compteur paquets rejetés TX |
| `sensor` | Port X erreurs FCS | Compteur erreurs FCS |
| `sensor` | Port X consommation PoE | Puissance PoE consommée en W *(ports PoE uniquement)* |
| `sensor` | Port X PoE alloué | Puissance PoE allouée en W *(ports PoE uniquement)* |
| `switch` | Port X activé | Admin state (shutdown / no shutdown) |
| `switch` | Port X PoE | Alimentation PoE *(ports PoE uniquement)* |

Au niveau du switch (entités globales) :

| Type | Nom | Description |
|------|-----|-------------|
| `sensor` | Température | Température interne du switch en °C |
| `button` | Redémarrer | Redémarre le switch sur la partition flash primaire |

Le nom affiché utilise la description configurée sur le port si disponible, sinon le numéro de port court (`1/1/1`).

## Notes techniques

- Protocole : **RESTCONF** (RFC 8040) via HTTPS, Basic Auth
- Certificats auto-signés supportés (vérification SSL désactivable)
- Intervalle de mise à jour configurable (10–3600 s, défaut 30 s)
- Les compteurs RX/TX sont des compteurs 64 bits `TOTAL_INCREASING` : Home Assistant calcule automatiquement les statistiques via ses helpers
- La consommation PoE est retournée en W (float) directement par l'API

## Endpoints RESTCONF utilisés

```
GET   /restconf/data/system/config/hostname
GET   /restconf/data/openconfig-platform:components
GET   /restconf/data/interfaces
PATCH /restconf/data/interfaces/interface=<id>/config
PATCH /restconf/data/interfaces/interface=<id>/ethernet/poe/config
POST  /restconf/operations/boot-sys-flash
```

Source : *RUCKUS FastIron RESTCONF Programmers Guide, 09.0.10*
