# Collecteur de preuves organisationnelles

Collecteur Python sans dépendance tierce. Vérifie directement dans Recherche d’entreprises le statut actif et la diffusion ouverte de l’unité et du siège, puis le SIREN dans les mentions du domaine et les extraits sur les pages sources. Le dépôt par HTTPS ne transmet que des données de recherche. Aucune extraction de coordonnées.

## Planification et configuration

La branche par défaut contient le calendrier de 07 h 17 Europe/Paris et workflow_dispatch. GitHub peut retarder le démarrage. Après 60 jours sans activité dans un dépôt public, GitHub peut désactiver le calendrier. https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule

Configurer quatre secrets Actions pour le dépôt : SOURCE_CONFIG (JSON privé des sources et règles autorisées), SITE_SERVICE (accès non interactif Sites), DEPOSIT_KEY (droit de dépôt uniquement), DEPOSIT_URL (URL HTTPS finissant par /api/ingest). Le runner ne reçoit aucun droit d’expédition. Restreindre les droits de modification de la branche par défaut. Aucun job de PR, cache, artefact ou diagnostic contenant les sources opérationnelles.

## Fonctionnement

La liste watch est revérifiée chaque jour. Le collecteur parcourt aussi une tranche tournante de l’annuaire ouvert des activateurs France Num. Les domaines candidats régis par discovery_domains disposent d’une autorisation de collecte documentée en privé. Le lien de l’annuaire doit correspondre au domaine officiel. Aucune qualification sur le seul code d’activité. Ne placer dans la configuration que des URL organisationnelles et des extraits autorisés, sans coordonnées personnelles. Le collecteur respecte robots.txt, les délais d’accès, les refus et les limites de taille. Une anomalie de source surveillée annule le lot. Une reprise au plus sur les lectures 502/503/504. Aucun renvoi automatique du dépôt. Un dépôt contient au plus vingt SIREN.

Exécuter les tests avec `python3 -m unittest discover -s tests -v`. La fixture du répertoire fixtures est fictive.

La découverte automatique accepte aussi un nouveau domaine lié comme site officiel, à licence explicite CC BY ou CC0, avec mention SaaS et professionnelle, SIREN publié sur les mentions légales, signal explicite sur son propre site, et contrôle API final. Les autres domaines passent par les règles de sources approuvées. Toute opposition commerciale explicite, statut fermé ou diffusion insuffisante déclenche un retrait minimal par SIREN.
