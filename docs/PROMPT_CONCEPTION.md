# Nœud IA — prompt de conception

> À donner tel quel à l'agent de code (Free Claude Code, puis Claude Code pour les finitions), à la racine du dépôt `ryan18k/IpadAIR`.

## Ton rôle et ta méthode

Tu es l'ingénieur chargé de construire le système décrit ci-dessous, de bout en bout. Le dépôt contient déjà un prototype (`index.html`, `scripts/`) qui a servi à valider ce qui est techniquement possible sur l'appareil cible ; il ne constitue pas une base de code à étendre. Tu repars d'une architecture propre et tu reprends uniquement les enseignements et les morceaux de code qui ont fait leurs preuves, signalés plus bas.

Tu travailles par phases, dans l'ordre indiqué à la fin de ce document. Au début, lis ce document en entier, puis écris dans `docs/PLAN.md` ton plan détaillé : arborescence, interfaces entre modules, choix de bibliothèques avec leurs versions exactes. À la fin de chaque phase, tous les tests doivent passer, tu fais un commit, et tu mets à jour `docs/PLAN.md` en indiquant ce qui est fait et ce qui reste. Si un point de ce document se révèle impossible ou inadapté pendant l'implémentation, n'improvise pas un contournement silencieux : décris le problème dans `docs/DECISIONS.md`, propose une alternative et continue avec l'hypothèse la plus prudente.

Les quotas, les modèles disponibles et les limites des fournisseurs d'IA changent souvent. Toute valeur citée ici est indicative : vérifie-la dans la documentation officielle au moment de l'implémenter et range-la dans la configuration, jamais dans le code.

Aucune tâche métier n'est à implémenter (pas d'analyse crypto, pas de script particulier). Le but est un socle générique, solide et sûr, sur lequel des tâches seront ajoutées plus tard sans toucher au cœur.

## Objectif

Transformer un iPad laissé allumé en permanence en nœud autonome qui exécute du code et des tâches automatiques, et qui sert d'assistant IA accessible depuis le téléphone du propriétaire. Le propriétaire n'utilise jamais d'interface sur l'iPad au quotidien : il interagit uniquement par une messagerie, Telegram pour commencer. Il peut envoyer du texte, des photos, des messages vocaux et des fichiers, et reçoit en retour du texte, et éventuellement des fichiers ou des images.

Le système a deux volets qui partagent le même socle. Le premier est l'assistant : une question arrive, l'iPad choisit un modèle d'IA gratuit adapté, exécute du code si nécessaire et répond. Le second est l'automatisation : l'iPad lance seul des tâches récurrentes, dont le calcul est fait en Python, avec une interprétation facultative par l'IA, puis envoie le résultat.

L'IA doit rester gratuite. Le volume vient de la combinaison de plusieurs fournisseurs gratuits, chacun avec son propre quota. Le fournisseur principal est NVIDIA (build.nvidia.com), le plus généreux, avec un ordre de grandeur de 40 requêtes par minute à vérifier. Les autres servent de relève et de spécialistes.

## Contraintes de la plateforme (vérifiées, non négociables)

L'appareil est un iPad Air 13 pouces M2 (8 Go), sous iPadOS 18.7.8, supervisé par un MDM qu'on ne contrôle pas. Ces constats ont été vérifiés pendant le prototypage :

Il n'y a pas d'App Store, et il est impossible d'installer une application, un profil de configuration ou un VPN. Seuls Safari et Chrome sont disponibles. Chrome utilise le même moteur WebKit et n'offre rien de plus. Tout le système côté iPad est donc une page web statique, hébergée sur GitHub Pages (`https://ryan18k.github.io/IpadAIR/`) et ouverte dans Safari.

Le JavaScript s'exécute seulement quand l'écran est allumé et que l'onglet est au premier plan. Dès que l'écran se verrouille, iOS gèle la page. L'iPad restera branché, avec le verrouillage automatique désactivé et la luminosité au minimum. La page doit demander un Screen Wake Lock, le renouveler quand elle redevient visible, et supporter sans perte un rechargement complet de l'onglet à tout moment : rechargement par iOS, crash, mise à jour du code. Le démarrage doit être entièrement automatique, sans aucune action humaine.

L'iPad n'accepte aucune connexion entrante : il est en 5G derrière un CGNAT, et le VPN est interdit. Toute communication part donc de l'iPad, sous forme de requêtes sortantes, de long polling ou de WebSocket sortant.

Les appels réseau depuis le navigateur sont soumis à CORS. Le test du 22.10.2026 a montré que Gemini (endpoint compatible OpenAI), Groq, Cerebras, Mistral, OpenRouter, Telegram (Bot API et téléchargement de fichiers), CoinGecko et Open-Meteo acceptent les navigateurs. NVIDIA (`integrate.api.nvidia.com`) et GitHub Models les refusent. Ces derniers passent obligatoirement par le relais décrit plus bas.

Python fonctionne avec Pyodide 0.29.0 (Python 3.13), dans un Web Worker. Le démarrage prend environ 4 secondes. numpy, pandas et matplotlib se chargent à la demande, et les requêtes HTTP passent par `pyodide.http.pyfetch`. Il n'y a ni `subprocess`, ni sockets, ni serveur. WebGPU est expérimental sur cette version et a planté pendant les tests : n'en dépends pas. Les modèles locaux sont hors périmètre.

Le stockage disponible comprend localStorage, IndexedDB et l'API Cache. Les données doivent survivre aux rechargements. Considère que Safari peut les effacer dans des cas rares. Une sauvegarde exportable et réimportable de l'état, sans les secrets, est donc requise.

## Architecture

Le système se compose de trois blocs : un relais dans le cloud, le cœur sur l'iPad et les tâches.

### 1. Le relais (Cloudflare Worker)

Le relais est un Cloudflare Worker gratuit, déployé avec Wrangler depuis le dossier `relay/`. Il a deux rôles et rien d'autre.

Son premier rôle est d'être un proxy authentifié vers les fournisseurs d'IA. **Toutes les clés des fournisseurs d'IA sont stockées comme secrets du Worker** (`wrangler secret put`) et n'existent nulle part ailleurs : ni sur l'iPad, ni dans le dépôt. L'iPad appelle le relais avec un identifiant de fournisseur. Le relais choisit l'URL de destination dans une liste blanche fixe, ajoute la bonne clé, transmet la requête en streaming si demandé, et renvoie la réponse avec les en-têtes CORS limités à l'origine de la page. Il ne doit jamais devenir un proxy ouvert : aucune URL arbitraire n'est acceptée.

L'authentification iPad → relais repose sur une signature HMAC-SHA256 de chaque requête, avec un secret partagé, un horodatage et un nonce. Le relais rejette toute requête dont l'horodatage est décalé de plus de 60 secondes, et toute réutilisation d'un nonce dans cet intervalle. Il applique une limite de débit globale pour protéger les quotas en cas de fuite.

Le relais passe par tous les fournisseurs, même ceux qui acceptent CORS. C'est le prix à payer pour que les clés ne soient jamais sur l'iPad. Si le relais est inaccessible, l'IA est indisponible, mais tout le reste continue de fonctionner normalement : exécution Python, tâches de calcul et réponses aux commandes.

Son second rôle est la surveillance. L'iPad envoie un battement de cœur signé toutes les 5 minutes (valeur configurable). Le relais enregistre l'heure du dernier battement dans Workers KV. Un déclencheur planifié (Cron Trigger) vérifie régulièrement ce battement. Après 15 minutes de silence, il envoie une alerte Telegram au propriétaire, puis une notification de reprise quand les battements recommencent. Pour cela, le relais connaît aussi le jeton du bot et l'identifiant du propriétaire, en tant que secrets.

Le relais est minimal, sans dépendance, typé, testé avec Vitest et l'environnement Workers (Miniflare ou `@cloudflare/vitest-pool-workers`), et documenté dans `relay/README.md`, avec une procédure de déploiement pas à pas pour un débutant.

### 2. Le cœur sur l'iPad (page web)

Le cœur est écrit en TypeScript strict et compilé avec Vite. Une GitHub Action exécute le typage, les tests et la compilation à chaque push, puis déploie sur GitHub Pages seulement si tout passe. Une branche qui casse les tests ne doit jamais atteindre l'iPad. Toutes les dépendances externes, y compris les URL de CDN pour Pyodide, sont figées à une version exacte.

Les modules sont indépendants, communiquent par des interfaces typées documentées et reçoivent leurs dépendances par injection, ce qui permet de les tester isolément. Aucun module n'accède directement au stockage d'un autre.

**Le noyau et l'amorçage.** Ils gèrent le démarrage ordonné : chargement de la configuration, ouverture du coffre, reprise de la file, puis lancement des canaux et du planificateur. Ils gèrent aussi le Wake Lock, le battement de cœur vers le relais, ainsi que la récupération en cas d'erreur non gérée : journalisation, puis redémarrage contrôlé du module concerné ou rechargement de la page en dernier recours, avec une protection contre les boucles de rechargement. Un numéro de version est affiché, et la page détecte une nouvelle version déployée pour se recharger d'elle-même à un moment calme.

**Les canaux.** Il y a un adaptateur par messagerie. Seul Telegram est à implémenter maintenant, en long polling avec `getUpdates` et un `offset` persistant. Un adaptateur convertit chaque message entrant vers un format interne commun : expéditeur, texte, pièces jointes typées (image, audio, document), identifiant de message, et réponse à un message précédent. Il convertit aussi les réponses internes vers la messagerie, en découpant les messages trop longs, en envoyant les fichiers et en affichant l'indicateur « en train d'écrire ». Seul l'identifiant du propriétaire est autorisé. Tout autre expéditeur est ignoré et journalisé. Le jeton Telegram reste sur l'iPad, chiffré dans le coffre, car l'iPad doit interroger Telegram directement. Le format interne doit permettre d'ajouter plus tard un autre canal, comme WhatsApp ou une interface web, sans modifier aucun autre module.

**L'orchestrateur.** Toutes les demandes passent par une file d'attente persistante dans IndexedDB : messages du propriétaire, tâches planifiées et commandes. Elles sont traitées avec une priorité (le propriétaire avant les tâches de fond), une concurrence maîtrisée et une idempotence fondée sur l'identifiant d'origine, afin qu'un rechargement ne traite jamais deux fois le même message. Les échecs transitoires sont relancés avec un délai croissant. Un élément qui échoue définitivement est marqué comme tel, et le propriétaire est prévenu. L'orchestrateur décide du traitement : une commande directe est exécutée sans IA, tandis qu'une demande en langage naturel passe par l'agent.

**Le routeur IA.** C'est l'équivalent de Free Claude Code, sans la partie qui imite l'API d'Anthropic, devenue inutile. Chaque fournisseur est un adaptateur qui implémente une même interface, construite sur le format de chat compatible OpenAI. La plupart des fournisseurs le parlent nativement ; sinon, l'adaptateur traduit les requêtes. Chaque fournisseur est décrit dans un fichier de configuration (`config/providers.json` ou équivalent typé). Cette fiche indique ses modèles, les capacités de chacun (texte, vision, audio, appel d'outils, longueur de contexte), la qualité estimée, les quotas (requêtes par minute et par jour, jetons) et les priorités.

Pour chaque demande, le routeur détermine les capacités nécessaires : images à analyser, audio à transcrire, outils à utiliser. Il choisit ensuite le meilleur modèle disponible qui les possède, en tenant compte des quotas restants, mesurés localement et lus dans les en-têtes de limite renvoyés par les fournisseurs. En cas d'erreur 429, 5xx, de délai dépassé ou de réponse invalide, il bascule sur le candidat suivant, et un disjoncteur met le fournisseur fautif en pause pendant un moment. Il corrige les appels d'outils mal formés, ce qui est fréquent avec les modèles gratuits : JSON tronqué, arguments en texte au lieu de JSON ou appels écrits dans le contenu. Il nettoie aussi les balises de raisonnement que certains modèles laissent dans leurs réponses. Il expose des statistiques par fournisseur : appels, échecs, quotas restants et latence. Ajouter, retirer ou réordonner un fournisseur ne doit demander qu'une modification de configuration, plus un adaptateur seulement si son format est nouveau.

Les fournisseurs prévus au départ sont NVIDIA en principal, puis Groq, Cerebras, Gemini, Mistral et OpenRouter en relève. Les modèles exacts sont choisis et vérifiés par toi, puis documentés dans la configuration. Pour la vision, il faut un modèle multimodal, par exemple chez NVIDIA ou Gemini. Pour l'audio, il faut un service de transcription (par exemple Whisper chez Groq), ou un modèle qui comprend directement l'audio (par exemple Gemini). Telegram envoie les messages vocaux en OGG/Opus. Vérifie que le service choisi accepte ce format sans conversion.

**L'agent.** C'est une boucle d'appels d'outils, avec un nombre d'étapes et une durée bornés, qui utilise le routeur. Les outils sont les suivants : exécuter du Python, lancer une tâche ou un script enregistré, lire une URL, lire ou écrire dans la mémoire, et envoyer un fichier au propriétaire. Le prompt système est construit à chaque appel à partir de la date et de l'heure (Europe/Zurich), de la fiche mémoire du propriétaire, de la liste des tâches et fichiers disponibles, ainsi que des préférences de réponse. Tout contenu externe (page web, fichier reçu, sortie de script) est traité comme une donnée et jamais comme une instruction : l'agent ne doit pas pouvoir être détourné par un contenu qu'il lit. L'historique de conversation reste court. Au-delà d'une certaine longueur, il est résumé pour économiser les quotas.

**L'exécuteur Python.** Pyodide 0.29.0 tourne dans un Web Worker dédié. Chaque exécution a une limite de temps ; si elle est dépassée, le worker est arrêté puis recréé. Un script qui plante ou tourne en boucle ne bloque jamais le reste. Les paquets sont chargés à partir des imports détectés. Les fichiers du propriétaire sont montés dans le dossier courant. Tout fichier écrit dans `SORTIE` est récupéré à la fin de l'exécution et renvoyé au propriétaire. Les arguments sont fournis dans `ARGS` et dans `sys.argv`. La sortie standard et les erreurs sont capturées et tronquées proprement. Le prototype `index.html` contient une implémentation testée de ce module (worker, montage des fichiers, dossier `SORTIE`, détection des imports) que tu peux reprendre en la restructurant.

**Le planificateur.** Il gère des tâches récurrentes selon une syntaxe cron (une bibliothèque légère et figée convient), dans le fuseau Europe/Zurich, avec une gestion correcte des changements d'heure. Toutes les tâches sont persistées. Au démarrage, il détecte les exécutions manquées pendant une coupure et applique la politique propre à chaque tâche : rattraper une fois ou ignorer. Il empêche deux exécutions simultanées de la même tâche. Le résultat de chaque exécution est journalisé et peut être envoyé au propriétaire.

**Les tâches.** Une tâche est une unité déclarative stockée dans `tasks/`, à côté de son code Python. Sa fiche contient le nom, la description, le planning facultatif, les arguments, la limite de temps, ce qu'il faut envoyer au propriétaire et une étape d'interprétation par l'IA, facultative. Le principe est strict : **le calcul est toujours en Python pur, sans IA**. L'IA intervient seulement ensuite, si la tâche le demande, pour rédiger une interprétation du résultat. Si l'IA est indisponible, le résultat brut est quand même envoyé. Ajouter une tâche ne doit demander que d'ajouter des fichiers dans `tasks/`, sans modifier le cœur. Le propriétaire peut aussi envoyer un fichier `.py` par Telegram : il est alors exécutable comme tâche ponctuelle. Fournis une seule tâche d'exemple triviale, de type « bonjour », qui sert aussi de test de bout en bout.

**La mémoire.** Elle contient trois éléments. Le premier est une fiche « propriétaire » : faits durables sur la personne et préférences de ton, de longueur et de langue. Le second est une liste de faits datés. Le troisième est un résumé roulant des échanges récents importants. L'agent peut proposer d'ajouter un fait à la mémoire via un outil, mais il le fait seulement quand le propriétaire l'énonce clairement, et jamais à partir de déductions. Le propriétaire peut consulter, corriger ou effacer la mémoire par des commandes. La taille injectée dans chaque prompt est plafonnée.

**Le coffre.** Il contient les secrets présents sur l'iPad : le jeton Telegram et le secret HMAC du relais. Ils sont chiffrés en AES-GCM avec une clé WebCrypto non exportable, générée sur l'appareil et conservée dans IndexedDB. Ce choix permet de redémarrer sans saisir de mot de passe, tout en empêchant d'extraire la clé. Les secrets sont saisis une seule fois, soit dans l'interface de configuration, soit par une commande Telegram. Dans ce cas, le message qui contient le secret est supprimé automatiquement. Aucun secret ne doit apparaître dans le code, le dépôt, les journaux ou l'export de sauvegarde. Les journaux masquent tout ce qui ressemble à une clé.

**Le journal et l'état.** Le journal est circulaire et persistant, avec des niveaux de gravité. Une page d'état minimale, sombre et sans animation, limite la consommation d'énergie. Elle affiche la version, le temps de fonctionnement, l'état des canaux et du relais, les quotas par fournisseur, la file, les dernières exécutions et les erreurs récentes. Elle permet aussi de configurer le système au premier lancement : jeton, identifiant du propriétaire, URL du relais et secret. Elle contient enfin un bouton d'export et d'import de la sauvegarde. La page doit fonctionner en mode « Sur l'écran d'accueil » de Safari, avec un manifeste et une icône, et sa mise en page doit convenir à l'orientation paysage.

### 3. Les commandes

Les commandes directes passent par Telegram et n'utilisent jamais l'IA. Elles sont donc disponibles même sans relais. Au minimum, il faut : aide, état, liste et lancement des tâches, exécution de Python, gestion des fichiers, affichage et modification de la mémoire, réinitialisation de la conversation, et configuration des secrets et du modèle préféré. Tout message qui n'est pas une commande va à l'agent. Une photo est analysée par un modèle de vision. Un message vocal est transcrit puis traité comme du texte, et la transcription est rappelée brièvement dans la réponse. Un document est conservé, et sa légende éventuelle sert de question.

## Exigences transversales

**Sécurité.** Applique le principe du moindre privilège partout. Seul le propriétaire est autorisé. Le relais est fermé : liste blanche de destinations, signature et limite de débit. Le code ne contient aucun secret, et l'historique Git doit être nettoyé. Le prototype actuel contient une clé OpenRouter encodée dans `index.html`. Retire-la, purge-la de l'historique, et indique dans `docs/DECISIONS.md` que le propriétaire doit la révoquer et en générer une nouvelle. Protège l'agent contre l'injection de prompt. Valide toutes les entrées : tailles de fichiers, types et longueur des messages.

**Robustesse.** Le système ne doit jamais perdre une demande à cause d'un rechargement. Toute dépendance externe peut tomber sans entraîner le reste : Telegram, le relais ou un fournisseur. Les délais d'attente sont explicites sur chaque appel réseau, et les nouvelles tentatives suivent un délai croissant avec une part aléatoire. Aucune promesse ne doit rester sans gestion d'erreur.

**Maintenabilité.** Le TypeScript est strict, sans `any` implicite. Les modules sont courts et ont une seule responsabilité. La configuration est séparée du code. Les commentaires expliquent le pourquoi, pas le quoi. Le `README.md` explique l'architecture avec un schéma, le premier déploiement, l'ajout d'un fournisseur, d'une tâche ou d'un canal, ainsi que le dépannage.

**Tests.** Les tests unitaires (Vitest) couvrent chaque module, avec des faux pour fetch, IndexedDB et le temps. Ils doivent couvrir en priorité le routeur (sélection, bascule, quotas, disjoncteur, réparation des appels d'outils), l'orchestrateur (persistance, idempotence, reprise), le planificateur (rattrapage, changement d'heure), le coffre et l'authentification du relais. Ajoute un test de bout en bout avec Playwright sur WebKit, le moteur de Safari, avec Telegram et le relais simulés : un message arrive, l'agent exécute du Python et une réponse contenant un fichier repart. Ce type de test a déjà fonctionné avec le prototype. La CI exécute tout.

**Économie d'énergie.** La page n'a ni animation ni rendu inutile. Les minuteries sont regroupées, et rien n'interroge le réseau plus souvent que nécessaire : un seul long polling Telegram de 25 à 50 secondes, un battement de cœur toutes les 5 minutes et le planificateur à la minute. Pendant l'inactivité, l'écran est sombre et presque statique.

## Hors périmètre

Ne développe pas maintenant les éléments suivants : tâches métier (analyse crypto, scraping de sites particuliers), canal WhatsApp, modèles exécutés localement sur l'iPad, réponses vocales du bot et interface de chat sur la page. L'architecture doit cependant permettre d'ajouter chacun d'eux sans refonte.

## Phases et critères d'acceptation

**Phase 1 — Fondations.** Mets en place l'outillage : Vite, TypeScript, Vitest, ESLint, la CI GitHub Actions et le déploiement Pages conditionné aux tests. Ajoute la structure des modules, la configuration, le journal, le coffre, ainsi que le noyau avec le Wake Lock et une reprise propre après rechargement. Retire la clé du prototype de l'historique. Acceptation : la page déployée démarre seule, conserve sa configuration chiffrée après un rechargement, et la CI bloque un commit qui casse un test.

**Phase 2 — Relais.** Développe le Worker : proxy signé avec liste blanche, secrets, limite de débit, battement de cœur et alerte Telegram. Ajoute ses tests et le guide de déploiement. Acceptation : un appel non signé est refusé, un appel signé atteint NVIDIA, et une coupure simulée de l'iPad déclenche une alerte.

**Phase 3 — Canal et orchestrateur.** Développe l'adaptateur Telegram, le format interne commun, la file persistante et les commandes directes sans IA. Acceptation : les commandes répondent, un rechargement pendant un traitement ne perd ni ne duplique aucun message, et un expéditeur inconnu est ignoré.

**Phase 4 — Python et tâches.** Développe l'exécuteur Python, les fichiers entrants et sortants, le format des tâches, le planificateur avec rattrapage, et la tâche d'exemple. Acceptation : un fichier `.py` envoyé par Telegram s'exécute et renvoie sa sortie et ses fichiers, une boucle infinie est interrompue sans bloquer le reste, et une tâche planifiée manquée pendant une coupure est rattrapée selon sa politique.

**Phase 5 — Routeur et agent.** Développe les adaptateurs des fournisseurs, la configuration, le suivi des quotas, la bascule, le disjoncteur, la réparation des outils et la boucle de l'agent. Acceptation : une question nécessitant un calcul déclenche l'exécution de Python et donne une réponse correcte, la saturation simulée du fournisseur principal bascule de façon transparente, et les statistiques des quotas sont visibles.

**Phase 6 — Multimodal et mémoire.** Ajoute la vision, la transcription vocale, la mémoire et ses commandes, ainsi que le résumé de l'historique. Acceptation : une photo est décrite correctement, un vocal reçoit une réponse, et un fait énoncé explicitement est retenu et réutilisé dans une conversation ultérieure.

**Phase 7 — Finitions.** Finalise la page d'état, le mode écran d'accueil, l'export et l'import, la détection des nouvelles versions et la documentation complète. Teste ensuite l'endurance : 12 heures de fonctionnement simulé sans fuite de mémoire ni croissance anormale du stockage. Acceptation : le `README` suffit à un débutant pour tout redéployer de zéro.
