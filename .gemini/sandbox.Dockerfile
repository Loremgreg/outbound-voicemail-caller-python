# Utiliser l'image de base fournie par Gemini CLI
FROM gemini-cli-sandbox

# Passer en utilisateur root pour installer des paquets
USER root

# Mettre à jour les paquets et installer Python, pip et venv
# C'est tout ce dont notre projet a besoin comme dépendances système.
RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && rm -rf /var/lib/apt/lists/*

# Revenir à l'utilisateur non-root par défaut pour la sécurité
USER gemini
