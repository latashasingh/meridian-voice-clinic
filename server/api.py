"""Dashboard API.

Read-only endpoints for the frontend (doctors, slots, appointments) plus a
demo reset. It reads the same SQLite file as the voice bot, so a booking made
by voice shows up here immediately.

Run with::

    uv run uvicorn api:app --port 8000 --reload
"""

import clinic
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

clinic.init_db()

app = FastAPI(title="Meridian Clinic dashboard API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

router = APIRouter(prefix="/clinic")


@router.get("/doctors")
def get_doctors():
    clinic.init_db()  # keeps the 7-day slot window fresh
    return clinic.doctors_overview()


@router.get("/appointments")
def get_appointments():
    return clinic.appointments_overview()


@router.post("/reset")
def reset():
    clinic.reset_appointments()
    return {"ok": True}


app.include_router(router)
