# 3M — Assistant personnel intelligent

Première version locale d’un assistant personnel unifié : conversation, fournisseurs LLM
interchangeables, mémoire, tâches, calendrier de démonstration, agents, compétences, voix et PWA.

## État réel

- Fonctionne sans clé en mode **Démo locale** (réponse déterministe clairement annoncée).
- OpenAI, Anthropic, Ollama et ElevenLabs sont intégrés mais ne sont validés que lorsqu’ils sont
  configurés et testés avec leurs services réels.
- La reconnaissance et la lecture vocales utilisent d’abord les capacités du navigateur. Ce
  n’est pas une conversation audio duplex temps réel.
- Le calendrier Apple n’est pas encore connecté ; la V1 utilise des événements SQLite de démo.
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

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Accès iPhone sécurisé](docs/IPHONE.md)
