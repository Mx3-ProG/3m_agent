# 3M — Assistant personnel intelligent

Assistant personnel local avec orchestrateur multi-agent exécutable : conversation, fournisseurs
LLM interchangeables, mémoire, tâches, calendrier de démonstration, outils typés, confirmations,
traces d’exécution, voix et PWA.

## État réel

- Fonctionne sans clé en mode **Démo locale** (réponse déterministe clairement annoncée).
- OpenAI, Anthropic, Ollama et ElevenLabs sont intégrés mais ne sont validés que lorsqu’ils sont
  configurés et testés avec leurs services réels.
- La reconnaissance et la lecture vocales utilisent d’abord les capacités du navigateur. Ce
  n’est pas une conversation audio duplex temps réel.
- Le provider Apple Calendar est disponible via un pont EventKit local opt-in. Le provider SQLite
  de démonstration reste actif par défaut et aucune permission Apple n’est demandée automatiquement.
- `CalendarAgent` et `TaskAgent` exécutent réellement leurs outils via un plan validé. Les écritures
  sensibles demandent une confirmation avant tout effet.
- L’accès HTTPS iPhone est documenté mais nécessite une validation sur l’appareil physique.

## Prérequis

- macOS, Linux ou un environnement Docker futur
- Python 3.12+ et `uv`
- Node.js 22+ et npm

## Installation locale

```bash
cp .env.example .env
# Remplacer les deux valeurs de jeton par la même chaîne aléatoire longue.
uv sync --dev
npm --prefix apps/web install
chmod +x scripts/dev.sh scripts/check.sh
./scripts/dev.sh
```

Ouvrir [http://localhost:3000](http://localhost:3000). L’API de santé répond sur
`http://127.0.0.1:8000/api/v1/health` et la documentation FastAPI sur
`http://127.0.0.1:8000/docs`.

Sur ce Mac, le fichier `.env` local sélectionne le modèle Ollama déjà installé
`qwen2.5-coder:7b`, validé de bout en bout. Le fichier `.env.example` reste volontairement en
mode démo afin qu’une nouvelle installation démarre sans supposer la présence d’un modèle.

## Configurer un vrai LLM

Les clés restent uniquement dans `.env`, jamais dans `apps/web` :

```dotenv
OPENAI_API_KEY=...
# ou ANTHROPIC_API_KEY=...
```

Sélectionner ensuite le fournisseur dans l’interface et saisir un nom de modèle compatible.
Pour Ollama, démarrer le service et télécharger explicitement le modèle souhaité, puis sélectionner
`ollama`. Le projet n’installe et ne télécharge aucun modèle automatiquement.

## Tests

```bash
./scripts/check.sh
```

Ce script lance Ruff, les tests backend, le contrôle TypeScript et le build de production Next.js.

Les routes privées `/api/v1/agents`, `/skills`, `/tools` et `/executions` exposent l’état réel de
l’orchestrateur. Les agents peuvent être activés ou désactivés depuis le dashboard ou par API.
La conversation utilise `/api/v1/conversations/chat/stream` pour transmettre les états réels de
planification, d’appel d’agent, d’exécution d’outil et de réponse.

## Activer Apple Calendar sur macOS

Construire le pont local :

```bash
./scripts/build-apple-calendar-bridge.sh
```

Vérifier son statut sans demander de permission :

```bash
native/apple-calendar-bridge/.build/apple-calendar-bridge status
```

La commande suivante affiche la demande d’autorisation macOS et doit être lancée volontairement :

```bash
native/apple-calendar-bridge/.build/apple-calendar-bridge request-access
```

Après autorisation, configurer puis redémarrer 3M :

```dotenv
THREEM_CALENDAR_PROVIDER=apple
THREEM_APPLE_CALENDAR_BRIDGE_PATH=native/apple-calendar-bridge/.build/apple-calendar-bridge
# Facultatif : identifiant EventKit d’un calendrier précis.
THREEM_APPLE_CALENDAR_IDENTIFIER=
```

`GET /api/v1/calendar/provider/status` permet de vérifier le provider actif. Les créations,
modifications et suppressions continuent d’exiger une confirmation conversationnelle.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Accès iPhone sécurisé](docs/IPHONE.md)
