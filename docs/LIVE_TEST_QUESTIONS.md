# Live Voice Test Questions

Run `docker compose exec backend python -m scripts.seed_clinic` before testing.
The seed creates future appointments on the next clinic day (Monday–Saturday):

- **Rahul Verma** — Dental Checkup, Dr. Ananya Rao, Koramangala, 11:00 AM
- **Sneha Kulkarni** — Dermatology Consultation, Dr. Sanjay Gupta, Indiranagar, 3:00 PM
- **Fatima Sheikh** — Physiotherapy Session, Dr. Meera Nair, Indiranagar, 4:00 PM

When calling from a number that is not in the seed, state the seeded full name.
The patient lookup tool deliberately falls back to an exact name match after a
caller-ID miss, which makes the live number testable from any phone.

Use each numbered item as a fresh call unless its steps say to continue a call.
The expected behavior is the assertion to listen for or verify in the tool log.

## Core booking and scheduling

1. **Earliest across branches**
   - Say: “I’m Rahul Verma. I need the earliest dental appointment available.”
   - Expect: Maya checks live availability across both branches and eligible dentists before naming one slot; it does not assume Koramangala or one doctor.

2. **Specific but underspecified time**
   - Say: “I’m Fatima Sheikh. Do you have anything on the next clinic day around one?”
   - Expect: a live search near 1 PM, followed by a concise offered option and a confirmation before any booking.

3. **Recurring weekday preference**
   - Say: “I’m Rahul Verma. I need physiotherapy; Mondays and Wednesdays work well for me.”
   - Expect: Maya asks only for any still-missing detail and searches a concrete upcoming Monday or Wednesday. It must not invent an availability answer.

4. **Afternoon preference**
   - Say: “I’m Sneha Kulkarni. I need a skin appointment in the afternoon, around 4:30.”
   - Expect: a dermatology search in that local time window and a branch/doctor/date/time read back before booking.

5. **Branch-specific triage**
   - Say: “I’m Rahul Verma. Is there a skin doctor at Koramangala next clinic day?”
   - Expect: a branch-scoped live search. The answer must be for Koramangala, not Indiranagar.

6. **Stale-availability check**
   - First say: “I’m Rahul Verma. I need a dental appointment next clinic day at 10.”
   - After an option is offered, say: “Actually, make that 4:30 in the afternoon.”
   - Expect: a second availability search; Maya must not reuse or verbally repurpose the 10 AM result.

7. **Conflict handling**
   - Say: “I’m Rahul Verma. Book me with Dr. Ananya Rao at Koramangala next clinic day at 11 AM.”
   - Expect: the slot is unavailable because Rahul’s seeded appointment occupies it. Maya offers a nearby live alternative and never confirms the blocked slot.

## Seeded appointment lifecycle

8. **Cancellation**
   - Say: “I’m Rahul Verma. Please cancel my dental appointment next clinic day at 11.”
   - Expect: Maya finds the real appointment using `list_appointments`, asks for/uses Rahul’s full name, then confirms cancellation. A fee is mentioned only if the tool reports one.

9. **Reschedule**
   - Say: “I’m Sneha Kulkarni. Please move my skin appointment next clinic day at 3 PM to the next clinic day at 4:30.”
   - Expect: Maya lists the existing appointment, re-checks the requested new time, confirms the new branch and doctor aloud, then reschedules only after an explicit “yes.”

10. **List a returning patient’s appointment**
   - Say: “I’m Fatima Sheikh. What appointment do I have coming up?”
   - Expect: Maya recognizes the named returning patient and reports the seeded physiotherapy appointment without treating her as a new patient.

## Identity, language, and handoff

11. **Shared-phone disambiguation**
   - Send a test webhook with `from_number` `+91-98765-11111`, then say: “I need an appointment.”
   - Expect: Maya asks whether she is speaking with Arjun or Kavya Mehta rather than choosing either record. This requires the shared caller ID; saying the number aloud is not equivalent.

12. **Hindi**
   - Say: “Mera naam Rahul Verma hai. Mujhe agle clinic wale din dentist ke saath appointment chahiye.”
   - Expect: clear Hindi throughout, live availability lookup, and no unprompted English drift.

13. **Hinglish**
   - Say: “Main Sneha Kulkarni hoon, next clinic day afternoon mein skin appointment book karni hai.”
   - Expect: natural Hinglish, not a forced translation, with the same confirmation discipline as English.

14. **Bot and human handoff**
   - Say: “Are you a bot? I want to speak to a person about my report.”
   - Expect: an honest virtual-receptionist answer plus a logged callback request. Maya must not claim that a human is joining or that a live transfer is underway.

15. **Clinical concern**
   - Say: “I’m having severe pain after my treatment. Should I take another medicine?”
   - Expect: no medical advice; Maya logs a clinical-concern callback and sets the expectation that the clinic team will call back.

## Continuity and interruption

16. **Dropped-call recovery**
   - Start: “I’m Rahul Verma. I need a dental appointment next clinic day around 4:30.”
   - Let Maya return availability, then disconnect before confirming. Call back from the same number and say: “I got disconnected.”
   - Expect: a brief acknowledgement of the disconnect and continuation from the pending appointment context, without repeating identity or the original preference.

17. **Interruption**
   - While Maya is reading an offered slot, interrupt with: “Wait, I need Indiranagar instead.”
   - Expect: Maya stops cleanly, acknowledges the new branch, and performs a new branch-specific availability search.

18. **Missed outbound callback**
   - Create or place an outbound reminder call to Rahul’s seeded number, mark it unanswered/disconnected, then call back from that same number.
   - Say: “I’m calling back about the missed call.”
   - Expect: Maya restores the outbound-call context rather than starting cold. This cannot be tested by a spoken prompt alone; the missed outbound call must exist first.
