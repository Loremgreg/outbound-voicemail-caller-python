# GEMINI.md - Contexte du Projet Outbound Voicemail Caller

Ce document fournit le contexte essentiel à l'agent Gemini pour comprendre et travailler sur ce projet.

## 1. Résumé du Projet

Ce projet est un agent Python utilisant le framework **LiveKit Agents**. Son objectif principal est d'appeler automatiquement une messagerie vocale, de naviguer dans son menu à l'aide de tonalités DTMF, de transcrire le message vocal laissé, de le classifier à l'aide d'un LLM (OpenAI), et de sauvegarder le résultat dans un fichier journal.

## 2. Architecture et Workflow

Le fonctionnement de l'agent se déroule comme suit :

1.  **Déclenchement (`Dispatch`)** : L'agent est démarré via une commande `lk dispatch`. Cette commande fournit le numéro de téléphone de la messagerie vocale à appeler dans les métadonnées.

2.  **Appel Sortant (SIP)** : La fonction `entrypoint` est exécutée. Elle utilise le `SIP_OUTBOUND_TRUNK_ID` configuré pour lancer un appel sortant vers le numéro de téléphone fourni.

3.  **Connexion et Transcription en Temps Réel** :
    *   L'agent attend que l'appel soit connecté (`wait_for_participant`).
    *   Il utilise **Deepgram** pour la transcription parole-texte (STT) en temps réel, avec les `interim_results` activés pour une réactivité maximale.

4.  **Navigation DTMF et Enregistrement (`_process_stt_and_navigate_menu`)** : C'est le cœur de la logique pendant l'appel.
    *   **Navigation** : L'agent écoute la transcription en direct.
        *   S'il détecte des mots-clés comme "code" ou "pin", il envoie le `PIN_CODE` via la fonction `send_dtmf_sequence`.
        *   S'il détecte ensuite une instruction comme "pour écouter", il envoie la touche "1".
    *   **Enregistrement** : Simultanément, la fonction accumule la transcription **finale** du message vocal dans la variable `agent.full_transcript`.

5.  **Fin de l'Appel** : L'agent détecte lorsque l'appelant raccroche (`wait_for_participant_disconnection`).

6.  **Analyse Post-Appel (`_process_transcript`)** :
    *   La transcription complète est envoyée au modèle `gpt-4o` d'**OpenAI**.
    *   L'IA classifie le message selon des catégories prédéfinies (`PRISE_RDV`, `ANNULATION_RDV`, etc.).
    *   La classification et la transcription sont sauvegardées dans le fichier `voicemail_log.txt`.

## 3. Fichiers Clés

*   `agent.py`: Contient toute la logique de l'agent.
*   `requirements.txt`: Liste les dépendances Python du projet.
*   `.env.local`: Fichier de configuration (non versionné) contenant les secrets.
*   `voicemail_log.txt`: Fichier de sortie où les résultats sont enregistrés.
*   `README.md`: Documentation principale pour un utilisateur humain.

## 4. Commandes d'Exécution

1.  **Installer les dépendances** : `pip install -r requirements.txt`
2.  **Lancer l'agent** : `python3 agent.py dev`
3.  **Déclencher un appel** : `lk dispatch create --new-room --agent-name outbound-caller --metadata '''{"phone_number": "+1234567890"}'''`

## 5. Documentation et Liens Utiles

*   **LiveKit Agents Framework**
    *   [Vue d'ensemble des Agents](https://docs.livekit.io/agents/overview/)
*   **LiveKit SIP (Session Initiation Protocol)**
    *   [Documentation Générale SIP](https://docs.livekit.io/sip/)
    *   [Guide de configuration d'un Trunk SIP avec Twilio](https://docs.livekit.io/sip/quickstarts/configuring-twilio-trunk/)
    *   [Documentation sur la gestion du DTMF](https://docs.livekit.io/sip/dtmf/)
    *   [API pour les appels sortants](https://docs.livekit.io/sip/api/)
*   **SDK Python**
    *   [Référence du SDK Python pour les Agents](https://docs.livekit.io/agents/python/introduction/)