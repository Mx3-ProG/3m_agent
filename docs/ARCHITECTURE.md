# Architecture de 3M — Conversation et Context Engine V3

## Principes

3M est un monorepo composé d’une PWA Next.js et d’une API FastAPI. L’orchestrateur reste un
module du backend : il n’ajoute ni réseau ni processus supplémentaire. SQLite fournit une
persistance locale simple ; les modèles SQLAlchemy permettent une migration ultérieure vers
PostgreSQL sans modifier les contrats API.

```text
Safari / Chrome / PWA
        │ même origine, aucun secret fournisseur
        ▼
Next.js (conversation persistante, historique, voix + proxy serveur authentifié)
        │ X-3M-Token, JSON ou flux SSE, réseau local privé
        ▼
FastAPI ─ ContextEngine ─ Orchestrateur ─ Plan validé ─ Agent ─ Outil typé
   │           │              │              │            │       │
SQLite   ContextPackage  IntentRouter   Registres agents/skills   Provider métier
   │          │
   │       LLMProvider (conversation générale seulement)
   │          ├─ Demo (tests et démarrage sans clé)
   │          ├─ OpenAI Responses API
   │          ├─ Anthropic Messages API
   │          └─ Ollama local
   │
   ├─ messages, conversations et résumés
   ├─ références structurées `context_entities`
   ├─ pending_actions
   └─ execution_traces
```

## ConversationSession et boucle d’orchestration

L’identifiant de conversation est conservé dans l’URL et envoyé à chaque message. Le backend
recharge la conversation, ses messages récents, son résumé, ses références structurées et ses
actions encore valides. Recharger le navigateur ou redémarrer l’API ne réinitialise donc pas la
session. Une nouvelle conversation possède au contraire son propre contexte isolé.

Avant toute décision, `ContextEngine` construit un `ContextPackage` borné : message courant,
résumé, derniers messages dans le budget configuré, sujet actif, créneaux/événements référencés,
actions en attente, traces récentes, capacités actives, préférences explicites non sensibles et
contexte temporel Europe/Paris. Il prépare les faits ; l’orchestrateur reste seul responsable du
plan et de l’exécution.

1. Le routeur déterministe traite les intentions sûres et courantes. Pour une formulation ambiguë,
   le LLM sélectionné peut proposer une route structurée à partir du catalogue vivant des outils ;
   il ne fournit ni commande libre ni arguments exécutables.
2. Il produit un `ExecutionPlan` borné à huit étapes, avec dépendances explicites.
3. Python reconstruit les arguments métier puis vérifie agent, compétence, outil, propriété de
   l’outil et niveau d’autorisation. Toute proposition inconnue est rejetée.
4. Chaque étape est exécutée avec validation Pydantic, délai maximal et résultat structuré.
5. Une action sensible est persistée en attente ; seul un « oui » lié à cette conversation ou
   l’endpoint de confirmation exécute exactement la charge utile enregistrée.
6. Le résultat et la trace lisible sont persistés, puis la réponse est construite depuis le résultat
   réel de l’outil. Le LLM n’est pas autorisé à inventer un succès d’outil.

Le suivi de conversation permet notamment le parcours « trouve des créneaux » → « la deuxième » →
« oui ». Une demande multi-domaine peut chaîner CalendarAgent puis TaskAgent. Le choix explicite
d’un agent est accepté seulement si celui-ci possède la capacité demandée.

## Agents et outils

| Agent | Outils possédés | Écritures avec confirmation |
| --- | --- | --- |
| CalendarAgent | `calendar.list_events`, `calendar.find_free_slots`, `calendar.create_event`, `calendar.update_event`, `calendar.delete_event` | création, modification, suppression |
| TaskAgent | `tasks.list`, `tasks.create`, `tasks.update`, `tasks.complete`, `tasks.delete` | suppression |

Les outils ont un schéma d’entrée et de sortie, un niveau `safe_read`, `write`, `sensitive` ou
`dangerous`, un état activé/désactivé et une limite de temps. Les manifestes YAML associent chaque
compétence à ses agents et outils ; ils sont validés au démarrage.

## Contrôle et observabilité

- `/api/v1/agents` : santé, activation, outils et dernière utilisation ;
- `/api/v1/skills` et `/api/v1/tools` : capacités effectivement disponibles ;
- `/api/v1/executions` : intention, raison de routage, plan, résultats, durée et erreur ;
- `/api/v1/confirmations/{id}/approve|reject` : résolution explicite d’une action en attente.
- `/api/v1/conversations/chat/stream` : flux SSE des états réels puis résultat final ;
- `/api/v1/conversations` et `/{id}/messages` : bibliothèque, reprise et ajout de messages ;
- `/api/v1/debug/conversations/{id}/context` : contexte courant, uniquement en développement ;
- `/api/v1/calendar/provider/status` : provider calendrier actif et autorisation disponible.

L’activation des agents et compétences est persistée dans SQLite et restaurée au démarrage. Les
logs `[3M]` restent lisibles localement sans exposer de secret.

## Frontières de sécurité

- Les clés LLM et ElevenLabs ne transitent jamais dans le navigateur.
- L’API privée exige `X-3M-Token`; seul `/health` est public.
- Next.js ajoute ce jeton côté serveur via son proxy `/api/backend/*`.
- Les écritures calendrier et les suppressions nécessitent une confirmation éphémère, rattachée à
  la conversation et expirant automatiquement.
- Aucun agent ne possède de commande shell ou d’accès général au système de fichiers.
- Les souvenirs explicitement marqués sensibles sont refusés.
- Une compétence est seulement découverte depuis un manifeste local. Aucun code distant n’est
  téléchargé ou exécuté.

## Voix

Deux modes sont disponibles : push-to-talk et conversation continue. Dans le second, une machine
d’état maintient l’intention d’écoute entre reconnaissance, transcription, réflexion et lecture.
La reconnaissance est suspendue pendant `speechSynthesis`, puis reprend à la fin ; couper le micro
force toujours l’état `off`. Le bouton d’interruption arrête la lecture et revient à l’écoute en
mode continu. Aucun audio brut n’est stocké.

La Web Speech API dépend du navigateur, de ses permissions et parfois de son service de
reconnaissance. Cette version n’est pas un flux audio duplex et ne revendique pas encore un
barge-in vocal fiable : l’interruption explicite par bouton est la voie supportée.

## Calendrier et point d’intégration Apple

`CalendarAgent` dépend du contrat `CalendarProvider`. `DemoCalendarProvider`, adossé à SQLite,
reste le défaut déterministe. `AppleCalendarProvider` appelle uniquement l’exécutable local fixe
`native/apple-calendar-bridge/.build/apple-calendar-bridge`, compilé depuis la source Swift du
projet. Ce pont utilise EventKit pour lister, créer, modifier et supprimer des événements.

Le statut EventKit peut être lu sans déclencher de dialogue. L’accès complet est demandé seulement
par la commande explicite `request-access`; 3M ne contourne jamais les permissions macOS. Le choix
du provider se fait avec `THREEM_CALENDAR_PROVIDER=apple`. Les plans, agents, outils, permissions et
confirmations restent identiques quel que soit le provider.

## États conversationnels progressifs

Le endpoint SSE émet `planning`, `calling_agent`, `executing_tool`, `waiting_confirmation`,
`responding` ou `error`, puis un événement `result` contenant le `ChatResponse` final. Ces états
sont produits par les points d’exécution réels de l’orchestrateur et traversent sans buffering le
proxy Next.js. L’interface n’invente aucune étape absente.

## Portabilité

Les paramètres viennent de l’environnement, la base est montée comme volume et chaque surface
dispose d’un Dockerfile. Le futur VPS pourra exécuter l’API et la PWA ; les capacités macOS
resteront derrière un connecteur local authentifié.
