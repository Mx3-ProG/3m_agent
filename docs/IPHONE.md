# Accès iPhone sécurisé

La capture microphone Safari exige un contexte sécurisé. Une URL `http://192.168.x.x:3000` ne
constitue pas une configuration vocale fiable.

## Option recommandée pour la prochaine validation

1. Installer Tailscale sur le Mac et l’iPhone, puis connecter les deux au même tailnet.
2. Démarrer 3M en écoutant sur l’interface Tailscale uniquement.
3. Utiliser `tailscale serve` pour publier localement la PWA en HTTPS avec un certificat reconnu.
4. Ouvrir l’URL HTTPS Tailscale dans Safari, autoriser le microphone, puis choisir
   « Sur l’écran d’accueil ».
5. Tester la saisie, l’historique, la permission microphone, la reprise après verrouillage et
   la reconnexion Wi-Fi/cellulaire.

Cette procédure n’a pas encore été validée sur l’iPhone physique. N’exposez pas le port FastAPI
directement ; l’iPhone doit accéder uniquement à Next.js, qui conserve le jeton backend côté
serveur.

## Alternative LAN

Un certificat local reconnu par l’iPhone peut être créé avec `mkcert`, puis son autorité racine
installée et approuvée sur l’appareil. `mkcert` n’est pas installé par défaut dans ce projet et
son installation ou la modification du trousseau nécessite une validation explicite.

