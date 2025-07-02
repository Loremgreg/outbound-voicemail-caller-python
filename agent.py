from __future__ import annotations

import asyncio
import logging
import datetime
from dotenv import load_dotenv
import json
import os
from typing import Any

from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    cli,
    WorkerOptions,
)
from livekit.plugins import (
    deepgram,
    openai,
)

# Charger les variables d'environnement
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

# Récupérer les configurations depuis les variables d'environnement
outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
# Il est recommandé de gérer les informations sensibles comme les codes PIN via des variables d'environnement
PIN_CODE = os.getenv("VOICEMAIL_PIN", "1234")


# --- Fonctions pour la navigation DTMF ---

async def send_dtmf_sequence(room: rtc.Room, sequence: str):
    """
    Envoie une séquence de tonalités DTMF.
    """
    for char in sequence:
        # Les chiffres 0-9 ont leur propre valeur, '*' est 10, '#' est 11.
        code = int(char) if char.isdigit() else (10 if char == '*' else (11 if char == '#' else None))
        if code is not None:
            logger.info(f"Envoi DTMF: {char}")
            await room.local_participant.publish_dtmf(code, char)
            # Une pause est essentielle pour que le système distant traite chaque tonalité
            await asyncio.sleep(0.5)
        else:
            logger.warning(f"Caractère DTMF non reconnu: {char}")


class OutboundCaller(Agent):
    def __init__(self):
        super().__init__(
            instructions="""
            You are an AI assistant for a physiotherapy practice.
            You will receive a transcription of a voicemail message from a patient.
            Your only task is to analyze the text and classify it into one of the following categories:
            - PRISE_RDV
            - MODIFICATION_RDV
            - ANNULATION_RDV
            - DEMANDE_INFORMATION
            - AUTRE

            You must respond with only one of these category names and nothing else.
            """
        )
        self.full_transcript = ""

    async def _process_transcript(self, ctx: JobContext):
        # Une fois l'appel terminé, nous classifions la transcription complète.
        if not self.full_transcript.strip():
            logger.warning("La transcription est vide, aucune classification ne sera effectuée.")
            return

        logger.info(f"Transcription complète: {self.full_transcript}")
        session = AgentSession(llm=openai.LLM(model="gpt-4o"))
        session.start()
        try:
            session.chat_history.add_user_message(self.full_transcript)
            classification_stream = await session.generate_reply(stream=False)
            classification = classification_stream.text
            logger.info(f"Messagerie vocale classifiée comme: {classification}")

            if classification:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_entry = (
                    f"--- Voicemail Received: {timestamp} ---\n"
                    f"Classification: {classification}\n"
                    f"Transcript: {self.full_transcript.strip()}\n"
                    f"------------------------------------------\n\n"
                )
                with open("voicemail_log.txt", "a", encoding="utf-8") as f:
                    f.write(log_entry)
                logger.info("La messagerie et la classification ont été sauvegardées dans voicemail_log.txt")
        finally:
            session.stop()


async def entrypoint(ctx: JobContext):
    logger.info(f"Connexion à la room {ctx.room.name}")
    await ctx.connect()

    dial_info = json.loads(ctx.job.metadata)
    participant_identity = phone_number = dial_info["phone_number"]
    agent = OutboundCaller()

    # Activer les résultats intermédiaires pour une navigation de menu réactive
    stt = deepgram.STT(interim_results=True, endpointing=300)
    stt_stream = stt.stream(room=ctx.room)

    try:
        # Lancer l'appel SIP
        sip_participant_task = asyncio.create_task(
            ctx.api.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=ctx.room.name,
                    sip_trunk_id=outbound_trunk_id,
                    sip_call_to=phone_number,
                    participant_identity=participant_identity,
                    wait_until_answered=True,
                )
            )
        )

        participant = await ctx.wait_for_participant(identity=participant_identity)
        logger.info(f"Le participant a rejoint: {participant.identity}")

        # Écouter la transcription, naviguer dans le menu et attendre la déconnexion
        stt_task = asyncio.create_task(_process_stt_and_navigate_menu(ctx, stt_stream, agent))
        disconnection_task = asyncio.create_task(ctx.wait_for_participant_disconnection(participant))

        await asyncio.wait([disconnection_task, sip_participant_task], return_when=asyncio.FIRST_COMPLETED)

        if disconnection_task.done():
            logger.info("Le participant s'est déconnecté, traitement de la transcription.")
            await asyncio.sleep(2)  # Laisser le temps pour la transcription finale
            stt_task.cancel()
            await agent._process_transcript(ctx)
        else:
            logger.error("L'appel SIP a échoué ou n'a pas reçu de réponse.")
            stt_task.cancel()

    except api.TwirpError as e:
        logger.error(
            f"Erreur lors de la création du participant SIP: {e.message}, "
            f"statut SIP: {e.metadata.get('sip_status_code')} "
            f"{e.metadata.get('sip_status')}"
        )
    finally:
        logger.info("Arrêt.")
        ctx.shutdown()


async def _process_stt_and_navigate_menu(ctx: JobContext, stt_stream: deepgram.STTStream, agent: OutboundCaller):
    """
    Traite le flux STT pour naviguer dans le menu et accumuler la transcription.
    """
    pin_sent = False
    listen_command_sent = False
    menu_navigation_finished = False

    async for event in stt_stream:
        if event.type == deepgram.STTEventType.TRANSCRIPT:
            transcript = event.transcript.alternatives[0].transcript.lower()

            # 1. Logique de navigation dans le menu (utilise les transcriptions intermédiaires)
            if not menu_navigation_finished:
                logger.info(f"Menu-Transcript: {transcript}")

                # Étape 1: Détecter la demande de PIN
                if not pin_sent and any(keyword in transcript for keyword in ["code", "pin", "password", "mot de passe"]):
                    logger.info("Demande de code PIN détectée. Envoi du code.")
                    await send_dtmf_sequence(ctx.room, PIN_CODE + "#")
                    pin_sent = True
                    await asyncio.sleep(1)

                # Étape 2: Détecter la commande d'écoute
                if pin_sent and not listen_command_sent and "pour écouter" in transcript:
                    logger.info("Commande d'écoute détectée. Envoi de la touche '1'.")
                    await send_dtmf_sequence(ctx.room, "1")
                    listen_command_sent = True

                if pin_sent and listen_command_sent:
                    logger.info("Navigation du menu terminée. Prêt à écouter le message.")
                    menu_navigation_finished = True

            # 2. Accumuler la transcription finale du message
            if event.transcript.is_final and event.transcript.alternatives[0].transcript:
                agent.full_transcript += event.transcript.alternatives[0].transcript + " "


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller",
        )
    )