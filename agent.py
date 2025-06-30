from __future__ import annotations

import asyncio
import logging
from dotenv import load_dotenv
import json
import os
from typing import Any

from livekit import rtc, api
from livekit.agents import (
    AgentSession,
    Agent,
    JobContext,
    function_tool,
    RunContext,
    get_job_context,
    cli,
    WorkerOptions,
    RoomInputOptions,
)
from livekit.plugins import (
    deepgram,
    openai,
)


# load environment variables, this is optional, only used for local development
load_dotenv(dotenv_path=".env.local")
logger = logging.getLogger("outbound-caller")
logger.setLevel(logging.INFO)

outbound_trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")


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
        # Once the call is finished, we have the full transcript.
        # We can now use the LLM to classify it.
        logger.info(f"Full transcript: {self.full_transcript}")

        # Create a new AgentSession just for this classification task
        session = AgentSession(llm=openai.LLM(model="gpt-4o"))
        session.start()
        try:
            # Add the full transcript to the chat history
            session.chat_history.add_user_message(self.full_transcript)

            # Generate the classification
            classification_stream = await session.generate_reply(stream=False)
            classification = classification_stream.text

            logger.info(f"Voicemail classified as: {classification}")

            # Here you could add logic to save the transcript and classification
            # to a database, send a notification, etc.

        finally:
            session.stop()


async def entrypoint(ctx: JobContext):
    logger.info(f"connecting to room {ctx.room.name}")
    await ctx.connect()

    dial_info = json.loads(ctx.job.metadata)
    participant_identity = phone_number = dial_info["phone_number"]

    agent = OutboundCaller()

    stt = deepgram.STT(interim_results=False, endpointing=300)
    stt_stream = stt.stream(room=ctx.room)

    # Start dialing the user
    try:
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
        logger.info(f"participant joined: {participant.identity}")

        # Listen for transcription and participant disconnection
        transcript_task = asyncio.create_task(_accumulate_transcript(stt_stream, agent))
        disconnection_task = asyncio.create_task(ctx.wait_for_participant_disconnection(participant))

        # Wait for either the participant to disconnect or the SIP call to fail
        await asyncio.wait([disconnection_task, sip_participant_task], return_when=asyncio.FIRST_COMPLETED)

        # If the participant disconnected, the call was successful in some way
        if disconnection_task.done():
            logger.info("Participant disconnected, processing transcript.")
            # Allow some time for the final transcript to be processed
            await asyncio.sleep(2)
            transcript_task.cancel() # Stop accumulating transcript
            await agent._process_transcript(ctx)
        else:
            logger.error("SIP call failed or was not answered.")
            transcript_task.cancel()

    except api.TwirpError as e:
        logger.error(
            f"error creating SIP participant: {e.message}, "
            f"SIP status: {e.metadata.get('sip_status_code')} "
            f"{e.metadata.get('sip_status')}"
        )
    finally:
        logger.info("Shutting down.")
        ctx.shutdown()

async def _accumulate_transcript(stt_stream, agent):
    async for event in stt_stream:
        if event.type == deepgram.STTEventType.TRANSCRIPT:
            alternatives = event.transcript.alternatives
            if alternatives and alternatives[0].transcript:
                agent.full_transcript += alternatives[0].transcript + " "



if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            agent_name="outbound-caller",
        )
    )
