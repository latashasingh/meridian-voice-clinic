import { useCallback, useEffect, useRef, useState } from "react";
import { PipecatClient } from "@pipecat-ai/client-js";
import { SmallWebRTCTransport } from "@pipecat-ai/small-webrtc-transport";
import { playEnd, playPickup, startRing, stopRing } from "./sounds.js";

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

// One colour per speciality, used as the doctor's signage band.
const BAND = {
  Cardiology: "#b5443a",
  Dermatology: "#b9822a",
  Pediatrics: "#2f8577",
  Orthopedics: "#3a56a5",
  "General Medicine": "#6a7d35",
};

const fmtDay = (day) =>
  new Date(`${day}T00:00:00`).toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short" });

const fmtTime = (time) => {
  const [h, m] = time.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
};

const fmtClock = (s) => `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;

const groupDays = (slots) => {
  const map = new Map();
  for (const s of slots) map.set(s.date, [...(map.get(s.date) ?? []), s]);
  return [...map.entries()];
};

/* ------------------------------------------------------------------ */
/* Clinic data: polls the dashboard API and detects bookings           */
/* ------------------------------------------------------------------ */

function useClinic() {
  const [doctors, setDoctors] = useState([]);
  const [appointments, setAppointments] = useState([]);
  const [fresh, setFresh] = useState({}); // appointment id -> "booked" | "cancelled"
  const [lastEvent, setLastEvent] = useState(null);
  const [offline, setOffline] = useState(false);
  const known = useRef(null);

  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const [d, a] = await Promise.all([
          fetch("/clinic/doctors").then((r) => r.json()),
          fetch("/clinic/appointments").then((r) => r.json()),
        ]);
        if (!alive) return;
        const before = known.current;
        if (before) {
          for (const appt of a) {
            const was = before.get(appt.appointment_id);
            const kind = was === undefined && appt.status === "booked" ? "booked" : was === "booked" && appt.status === "cancelled" ? "cancelled" : null;
            if (!kind) continue;
            setFresh((f) => ({ ...f, [appt.appointment_id]: kind }));
            setLastEvent({ kind, appt, at: Date.now() });
            setTimeout(() => setFresh((f) => Object.fromEntries(Object.entries(f).filter(([k]) => Number(k) !== appt.appointment_id))), 5000);
          }
        }
        known.current = new Map(a.map((x) => [x.appointment_id, x.status]));
        setDoctors(d);
        setAppointments(a);
        setOffline(false);
      } catch {
        if (alive) setOffline(true);
      }
    };
    load();
    const timer = setInterval(load, 1500);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const reset = async () => {
    await fetch("/clinic/reset", { method: "POST" }).catch(() => {});
    known.current = new Map();
  };

  return { doctors, appointments, fresh, lastEvent, offline, reset };
}

/* ------------------------------------------------------------------ */
/* Dashboard panels                                                    */
/* ------------------------------------------------------------------ */

function Doctors({ doctors }) {
  return (
    <section className="panel" aria-labelledby="doctors-title">
      <h2 id="doctors-title">Doctors</h2>
      <ul className="doctors">
        {doctors.map((d) => {
          const days = groupDays(d.slots).slice(0, 4);
          return (
            <li key={d.id} className="doctor" style={{ "--band": BAND[d.speciality] ?? "#456" }}>
              <div className="doctor-head">
                <h3>{d.name}</h3>
                <span>{d.speciality}</span>
              </div>
              {days.length === 0 ? (
                <p className="muted">Fully booked</p>
              ) : (
                <div className="days">
                  {days.map(([day, slots]) => (
                    <div className="day" key={day}>
                      <span className="day-label">{fmtDay(day)}</span>
                      <div className="chips">
                        {slots.map((s) => (
                          <span className="chip" key={s.time}>
                            {fmtTime(s.time)}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Appointments({ appointments, fresh, onReset }) {
  return (
    <section className="panel" aria-labelledby="appts-title">
      <div className="panel-head">
        <h2 id="appts-title">Appointments</h2>
        {appointments.length > 0 && (
          <button className="text-btn" onClick={onReset}>
            Clear all
          </button>
        )}
      </div>
      {appointments.length === 0 ? (
        <p className="empty">Nothing booked yet. Start a call and book a slot.</p>
      ) : (
        <ul className="ledger">
          {appointments.map((a) => (
            <li key={a.appointment_id} className={`row ${a.status} ${fresh[a.appointment_id] ? "fresh" : ""}`}>
              <div className="when">
                <strong>{fmtTime(a.time)}</strong>
                <span>{fmtDay(a.date)}</span>
              </div>
              <div className="who">
                <strong>{a.doctor}</strong>
                <span>{a.speciality}</span>
              </div>
              <div className="phone-no">{a.phone}</div>
              <span className={`state ${a.status}`}>{a.status === "booked" ? "Booked" : "Cancelled"}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Phone: waveform                                                     */
/* ------------------------------------------------------------------ */

function Waveform({ levels }) {
  const ref = useRef(null);
  useEffect(() => {
    const cv = ref.current;
    const g = cv.getContext("2d");
    let raf;
    const draw = (t) => {
      const dpr = window.devicePixelRatio || 1;
      const w = (cv.width = cv.clientWidth * dpr);
      const h = (cv.height = cv.clientHeight * dpr);
      g.clearRect(0, 0, w, h);
      const { you, bot } = levels.current;
      const lvl = Math.min(1, Math.max(you, bot) * 2.4);
      const n = 33;
      const gap = w / n;
      const bw = gap * 0.46;
      g.fillStyle = you > bot ? "#f3f1ea" : "#f6c945";
      for (let i = 0; i < n; i++) {
        const wobble = 0.5 + 0.5 * Math.sin(i * 0.62 + t / 130);
        const edge = 1 - (Math.abs(i - (n - 1) / 2) / ((n - 1) / 2)) * 0.6;
        const bh = Math.max(h * 0.05, h * (0.06 + lvl * 0.9 * wobble * edge));
        g.beginPath();
        g.roundRect(i * gap + (gap - bw) / 2, (h - bh) / 2, bw, bh, bw / 2);
        g.fill();
      }
      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(raf);
  }, [levels]);
  return <canvas ref={ref} className="wave" aria-hidden="true" />;
}

/* ------------------------------------------------------------------ */
/* App                                                                 */
/* ------------------------------------------------------------------ */

export default function App() {
  const clinic = useClinic();

  // Call state
  const [phase, setPhase] = useState("closed"); // closed | ringing | live | ended
  const [muted, setMuted] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState("");
  const [card, setCard] = useState(null);
  const phaseRef = useRef("closed");
  const clientRef = useRef(null);
  const audioRef = useRef(null);
  const levels = useRef({ you: 0, bot: 0 });
  const scrollRef = useRef(null);

  const go = (p) => {
    phaseRef.current = p;
    setPhase(p);
  };

  // Transcript helpers
  const sealYou = () => setMessages((m) => m.map((x) => (x.role === "you" ? { ...x, final: true } : x)));
  const sealBot = () => setMessages((m) => m.map((x) => (x.role === "bot" ? { ...x, sealed: true } : x)));
  const pushYou = (text, final) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last?.role === "you" && !last.final) return [...m.slice(0, -1), { ...last, text, final: !!final }];
      return [...m, { id: crypto.randomUUID(), role: "you", text, final: !!final }];
    });
  const pushBot = (text) =>
    setMessages((m) => {
      const last = m[m.length - 1];
      if (last?.role === "bot" && !last.sealed) return [...m.slice(0, -1), { ...last, text: `${last.text} ${text}` }];
      return [...m, { id: crypto.randomUUID(), role: "bot", text, sealed: false }];
    });

  const finish = useCallback(() => {
    stopRing();
    if (phaseRef.current === "live" || phaseRef.current === "ringing") {
      playEnd();
      go("ended");
    }
  }, []);

  const startCall = async () => {
    if (phaseRef.current === "ringing" || phaseRef.current === "live") return;
    setError("");
    setMessages([]);
    setSeconds(0);
    setMuted(false);
    setCard(null);
    go("ringing");
    startRing();

    const client = new PipecatClient({
      transport: new SmallWebRTCTransport({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] }),
      enableMic: true,
      enableCam: false,
      callbacks: {
        // Play the bot's voice
        onTrackStarted: (track, participant) => {
          if (participant?.local || track.kind !== "audio" || !audioRef.current) return;
          audioRef.current.srcObject = new MediaStream([track]);
          audioRef.current.play().catch(() => {});
        },
        onUserStartedSpeaking: sealYou,
        onBotStoppedSpeaking: sealBot,
        onUserTranscript: (t) => t.text && pushYou(t.text, t.final),
        onBotTranscript: (t) => t.text && pushBot(t.text),
        onLocalAudioLevel: (l) => (levels.current.you = l),
        onRemoteAudioLevel: (l) => (levels.current.bot = l),
        onDisconnected: finish,
        onError: () => setError("Connection problem. Check that the bot is running."),
      },
    });
    clientRef.current = client;

    try {
      const minRing = new Promise((r) => setTimeout(r, 1800)); // let the ringing be heard
      await Promise.all([
        client.startBotAndConnect({
          endpoint: "/start",
          requestData: { createDailyRoom: false, enableDefaultIceServers: true, transport: "webrtc" },
        }),
        minRing,
      ]);
      stopRing();
      playPickup();
      go("live");
    } catch (e) {
      stopRing();
      setError(
        /permission|denied|NotAllowed/i.test(String(e))
          ? "Microphone is blocked. Allow it in the address bar and call again."
          : "Could not reach the bot. Is it running on port 7860?"
      );
      try {
        await client.disconnect();
      } catch {}
      go("ended");
    }
  };

  const endCall = async () => {
    try {
      await clientRef.current?.disconnect();
    } catch {}
    finish();
  };

  const toggleMute = () => {
    const next = !muted;
    clientRef.current?.enableMic(!next);
    setMuted(next);
  };

  const closePhone = () => {
    clientRef.current = null;
    levels.current = { you: 0, bot: 0 };
    go("closed");
  };

  // Call timer
  useEffect(() => {
    if (phase !== "live") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // Confirmation card inside the phone when the agent books or cancels
  useEffect(() => {
    if (!clinic.lastEvent || phaseRef.current !== "live") return;
    setCard(clinic.lastEvent);
    const t = setTimeout(() => setCard(null), 9000);
    return () => clearTimeout(t);
  }, [clinic.lastEvent]);

  // Keep the transcript scrolled to the latest line
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Hang up if the tab closes
  useEffect(() => () => clientRef.current?.disconnect?.(), []);

  const onCall = phase === "ringing" || phase === "live";

  return (
    <div className={`shell ${phase !== "closed" ? "with-phone" : ""}`}>
      <audio ref={audioRef} autoPlay />

      <header className="top">
        <div className="brand">
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
            <rect width="30" height="30" rx="9" fill="currentColor" />
            <path d="M15 8v14M8 15h14" stroke="#e4ece8" strokeWidth="3.4" strokeLinecap="round" />
          </svg>
          <div>
            <h1>Meridian Clinic</h1>
            <p>Reception desk</p>
          </div>
        </div>
        <button className="call-btn" onClick={startCall} disabled={onCall}>
          <span className={`dot ${onCall ? "on" : ""}`} />
          {onCall ? "On a call" : "Try call"}
        </button>
      </header>

      {clinic.offline && (
        <p className="notice" role="status">
          Can&apos;t reach the dashboard API. Run <code>uv run uvicorn api:app --port 8000</code> in the server folder.
        </p>
      )}

      <main className="grid">
        <Appointments appointments={clinic.appointments} fresh={clinic.fresh} onReset={clinic.reset} />
        <Doctors doctors={clinic.doctors} />
      </main>

      {phase !== "closed" && (
        <aside className={`phone ${phase}`} aria-label="Call with Asha">
          <header className="phone-head">
            <div className="avatar">
              <span>A</span>
            </div>
            <div className="caller">
              <strong>Asha</strong>
              <span>Meridian Clinic</span>
            </div>
            <div className="status" aria-live="polite">
              {phase === "ringing" ? "Calling" : phase === "live" ? fmtClock(seconds) : `Ended ${fmtClock(seconds)}`}
            </div>
          </header>

          <Waveform levels={levels} />

          <div className="transcript" ref={scrollRef}>
            {messages.length === 0 && !error && (
              <p className="hint">{phase === "ringing" ? "Connecting to the front desk…" : "Say hello to start."}</p>
            )}
            {messages.map((m) => (
              <p key={m.id} className={m.role}>
                {m.text}
              </p>
            ))}
            {error && <p className="error">{error}</p>}
          </div>

          {card && (
            <div className={`confirm ${card.kind}`} role="status">
              <strong>{card.kind === "booked" ? "Appointment booked" : "Appointment cancelled"}</strong>
              <span>{card.appt.doctor}</span>
              <span>{card.appt.when}</span>
            </div>
          )}

          <footer className="controls">
            {phase === "ended" ? (
              <>
                <button className="ctl wide" onClick={startCall}>
                  Call again
                </button>
                <button className="ctl wide ghost" onClick={closePhone}>
                  Close
                </button>
              </>
            ) : (
              <>
                <button className={`ctl ${muted ? "active" : ""}`} onClick={toggleMute} disabled={phase !== "live"} aria-pressed={muted}>
                  {muted ? "Unmute" : "Mute"}
                </button>
                <button className="ctl end" onClick={endCall}>
                  {phase === "ringing" ? "Cancel" : "End call"}
                </button>
              </>
            )}
          </footer>
        </aside>
      )}
    </div>
  );
}
