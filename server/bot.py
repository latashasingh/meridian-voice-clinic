#
# Copyright (c) 2024–2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#

"""Voice AI doctor appointment assistant.

Pipeline: caller audio -> ElevenLabs STT -> Gemini -> ElevenLabs TTS -> caller audio

The LLM can call three tools (registered through the LLM context):
- check_doctor_availability
- book_appointment
- cancel_appointment

Run the bot using::

    uv run bot.py
"""

import os
from datetime import datetime

import clinic
from dotenv import load_dotenv
from loguru import logger
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import LLMRunFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import RunnerArguments
from pipecat.runner.utils import create_transport
from pipecat.services.elevenlabs.stt import ElevenLabsRealtimeSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.transcriptions.language import Language
from pipecat.transports.base_transport import BaseTransport, TransportParams
from pipecat.transports.daily.transport import DailyParams
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

SYSTEM_PROMPT = """You are Asha, the voice receptionist at Meridian Clinic. You help callers check doctor availability, book an appointment, and cancel an appointment. Today is {today}.

How you speak
- Your words are spoken aloud. Use short, natural sentences. No lists, markdown or emojis.
- Offer at most three slots at a time. Say dates like "Monday, 30 November" and times like "10 30 in the morning".
- Be warm and brief. One question at a time.

Identifying the caller
- You only know the caller by the phone number they say out loud. There is no login.
- Before booking or cancelling, ask for their 10 digit mobile number.
- Read it back digit by digit in groups, for example "9 8 7 6, 5 4 3 2, 1 0", and ask "Is that correct?".
- Continue only after a clear yes. If they say no, ask for the number again and repeat the read-back.
- Pass the number to tools as digits only.

Booking
1. Find out which doctor or speciality they need, and the day they prefer.
2. Call check_doctor_availability and offer slots from the result only.
3. Confirm doctor, date, time and phone number in one sentence and wait for a yes.
4. Call book_appointment with phone_confirmed set to true, then confirm the result.

Cancelling
1. Ask for the phone number and read it back.
2. After a yes, call cancel_appointment with phone_confirmed set to true, then confirm the result.

Rules
- Never invent doctors, slots or appointments. Use only what the tools return.
- Convert relative dates such as "tomorrow" or "next Monday" into YYYY-MM-DD for tool arguments, using today's date.
- If a tool returns an error, explain it simply and offer the next best option.
- Do not give medical advice. For emergencies, tell the caller to contact emergency services."""


# ---------------------------------------------------------------------------
# Tools (direct functions: Pipecat builds the schema from signature + docstring)
# ---------------------------------------------------------------------------


async def check_doctor_availability(
    params: FunctionCallParams,
    doctor: str = "",
    speciality: str = "",
    date: str = "",
):
    """Look up open appointment slots. Leave an argument empty to not filter by it.

    Args:
        doctor: Doctor name or part of it, for example "Sharma".
        speciality: Speciality, for example "cardiology" or "pediatrics".
        date: A single day to search, formatted YYYY-MM-DD. Empty means the next 7 days.
    """
    logger.info(f"check_doctor_availability(doctor={doctor!r}, speciality={speciality!r}, date={date!r})")
    await params.result_callback(clinic.check_availability(doctor=doctor, speciality=speciality, day=date))


async def book_appointment(
    params: FunctionCallParams,
    doctor: str,
    date: str,
    time: str,
    phone: str,
    phone_confirmed: bool,
    patient_name: str = "",
):
    """Book one slot for the caller. Only call this after the caller confirmed their phone number.

    Args:
        doctor: Full doctor name exactly as returned by check_doctor_availability.
        date: Appointment day, formatted YYYY-MM-DD.
        time: Appointment time in 24 hour format HH:MM, for example "14:00".
        phone: The caller's 10 digit phone number, digits only.
        phone_confirmed: True only if you read the number back and the caller said yes.
        patient_name: The caller's name if they gave it, otherwise empty.
    """
    logger.info(f"book_appointment(doctor={doctor!r}, date={date!r}, time={time!r}, phone={phone!r})")
    if not phone_confirmed:
        await params.result_callback(
            {
                "success": False,
                "error": "phone_not_confirmed",
                "message": "Read the phone number back to the caller and get a clear yes first.",
            }
        )
        return
    await params.result_callback(clinic.book(doctor, date, time, phone, patient_name))


async def cancel_appointment(params: FunctionCallParams, phone: str, phone_confirmed: bool):
    """Cancel the caller's existing appointment, found by their phone number.

    Args:
        phone: The caller's 10 digit phone number, digits only.
        phone_confirmed: True only if you read the number back and the caller said yes.
    """
    logger.info(f"cancel_appointment(phone={phone!r})")
    if not phone_confirmed:
        await params.result_callback(
            {
                "success": False,
                "error": "phone_not_confirmed",
                "message": "Read the phone number back to the caller and get a clear yes first.",
            }
        )
        return
    await params.result_callback(clinic.cancel(phone))


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------


async def run_bot(transport: BaseTransport, runner_args: RunnerArguments) -> None:
    """Run the voice bot for this session."""
    logger.info("Starting bot")
    clinic.init_db()

    # Speech-to-Text: ElevenLabs realtime. Pipecat's VAD decides when a turn ends.
    stt = ElevenLabsRealtimeSTTService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsRealtimeSTTService.Settings(language=Language.EN),
    )

    # Text-to-Speech: ElevenLabs
    tts = ElevenLabsTTSService(
        api_key=os.getenv("ELEVENLABS_API_KEY"),
        settings=ElevenLabsTTSService.Settings(
            voice=os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"),
        ),
    )

    # LLM: Google Gemini
    llm = GoogleLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        settings=GoogleLLMService.Settings(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            system_instruction=SYSTEM_PROMPT.format(today=datetime.now().strftime("%A, %d %B %Y")),
        ),
    )

    # Tools are advertised through the context; Pipecat registers the functions automatically.
    context = LLMContext(tools=[check_doctor_availability, book_appointment, cancel_appointment])
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(vad_analyzer=SileroVADAnalyzer()),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            tts,
            transport.output(),
            assistant_aggregator,
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
        observers=[],
    )

    runner = WorkerRunner(handle_sigint=runner_args.handle_sigint)

    await runner.add_workers(worker)

    @worker.rtvi.event_handler("on_client_ready")
    async def on_client_ready(rtvi):
        # Kick off the conversation
        context.add_message(
            {
                "role": "developer",
                "content": "Greet the caller as Asha from Meridian Clinic in one short sentence and ask how you can help.",
            }
        )
        await worker.queue_frames([LLMRunFrame()])

    @transport.event_handler("on_client_connected")
    async def on_client_connected(transport, client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(transport, client):
        logger.info("Client disconnected")
        await runner.cancel()

    await runner.run()


async def bot(runner_args: RunnerArguments):
    """Main bot entry point."""

    transport_params = {
        "daily": lambda: DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
        "webrtc": lambda: TransportParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    }

    transport = await create_transport(runner_args, transport_params)

    await run_bot(transport, runner_args)


if __name__ == "__main__":
    from pipecat.runner.run import main

    main()
