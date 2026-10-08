# Architecture de 3M — V1

## Principes

3M est un monorepo composé d’une PWA Next.js et d’une API FastAPI. L’orchestrateur reste un
module du backend : il n’ajoute ni réseau ni processus supplémentaire. SQLite fournit une
persistance locale simple ; les modèles SQLAlchemy permettent une migration ultérieure vers
PostgreSQL sans modifier les contrats API.

```text
Safari / Chrome / PWA
        │ même origine, aucun secret fournisseur
        ▼
Next.js (UI + proxy serveur authentifié)
        │ X-3M-Token, réseau local privé
        ▼
FastAPI ─ Orchestrateur ─ Registre agents ─ Registre compétences
   │              │
SQLite       LLMProvider
              ├─ Demo (tests et démarrage sans clé)
              ├─ OpenAI Responses API
              ├─ Anthropic Messages API
              └─ Ollama local
```

## Frontières de sécurité

- Les clés LLM et ElevenLabs ne transitent jamais dans le navigateur.
- L’API privée exige `X-3M-Token`; seul `/health` est public.
- Next.js ajoute ce jeton côté serveur via son proxy `/api/backend/*`.
- La suppression d’une tâche ou d’un événement nécessite un jeton de confirmation éphémère.
- Aucun agent ne possède de commande shell ou d’accès général au système de fichiers.
- Les souvenirs explicitement marqués sensibles sont refusés.
- Une compétence est seulement découverte depuis un manifeste local. Aucun code distant n’est
  téléchargé ou exécuté.

## Voix

La V1 implémente une boucle non duplex : reconnaissance vocale du navigateur, conversation
textuelle, puis lecture via `speechSynthesis`. Le backend expose aussi un endpoint ElevenLabs
configurable, limité en caractères. La faible latence duplex et le barge-in naturel ne sont pas
revendiqués dans cette version.

## Calendrier

`CalendarAgent` utilise un calendrier SQLite de démonstration. EventKit n’est pas accessible
directement depuis un backend Python : le connecteur Apple réel devra être un agent local macOS
séparé, signé et soumis aux autorisations du système.

## Portabilité

Les paramètres viennent de l’environnement, la base est montée comme volume et chaque surface
dispose d’un Dockerfile. Le futur VPS pourra exécuter l’API et la PWA ; les capacités macOS
resteront derrière un connecteur local authentifié.

