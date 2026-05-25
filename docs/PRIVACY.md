# Privacy & data handling

How the ASL pilot handles camera access, video, and learner data. This is the
authoritative engineering record behind the in-app privacy page
(`/privacy`, UX spec §18) and the onboarding consent copy. Written for a college
ASL-1 deployment, so it is FERPA-aware: progress data is an educational record.

The one-sentence version: **camera frames never leave the device — only the
outcome of a rep (pass / fail / skip + which sign) is sent to the server.**

---

## What the camera sees and where it goes

The practice screen requests the webcam via `getUserMedia` (see
`frontend/src/hooks/useCameraPermission.ts`). The resulting `MediaStream` is:

- bound only to a local `<video>` element for the live preview, and
- (in v2) fed frame-by-frame to the in-browser CV module.

It is **never** recorded, encoded to a file, uploaded, or sent to any third
party. There is no `MediaRecorder`, no `canvas.toBlob`/`toDataURL` upload path,
and no frame `fetch`/`FormData` anywhere in the client. The stream lives only in
page memory for the duration of the session.

When the user leaves the practice screen, denies the camera, or the component
unmounts, every track is stopped (`stream.getTracks().forEach(t => t.stop())`),
which turns the camera indicator light off. Reloading or closing the tab
discards the stream entirely — nothing persists.

## Where sign recognition runs

All computer-vision inference runs **in the browser** (Req 5: browser-first
inference; Req 13: no upload). The model pipeline (hand/body keypoints →
landmark regression → sign classifier) executes locally via WebGPU or a WASM
fallback. This is a hard contract, not an aspiration — see
`docs/ml-handoff.md`: *"The hot path stays in-browser. No frames or keypoints
cross the network."* Network calls during a rep are forbidden by the integration
contract.

A consequence worth stating plainly: because recognition is local, **we cannot
see, store, or review a learner's signing.** We only ever learn whether a rep
passed.

## What actually leaves the device

The only practice-derived data sent to the server is the rep outcome, posted to
`POST /api/progress/rep` with this exact shape
(`frontend/src/lib/api.ts`, `RepInput`):

```
{ signId, drillType, outcome: 'pass'|'fail'|'skip',
  source: 'self-report'|'cv'|'dev', hintRequested? }
```

No images, no video, no keypoints, no biometric vectors, no raw confidence
traces. Just "for sign X, the learner passed/failed/skipped, judged by
self-report or CV." That outcome updates the learner's mastery state.

Account and session data (handled separately from practice): email + password
for the account, and a session cookie for auth. Standard for a logged-in app;
unrelated to the camera.

## What is stored, and for how long

| Data | Where | Retention |
|---|---|---|
| Camera frames / video | Browser memory only | Discarded immediately; never written to disk or network |
| Keypoints / CV intermediates | Browser memory only | Discarded each rep |
| Rep outcomes + mastery state | Server (Postgres) | For the life of the account |
| Account (email, password hash) | Server (Postgres) | For the life of the account |
| Local preferences / resume state | Browser `localStorage` | Until the user clears it |

The progress/mastery records are the educational record. Under FERPA framing,
the learner (and, where applicable, the institution) is the owner of that
record; it is used to drive the learner's own progress dashboard, not shared
with third parties or used for advertising.

## Learner controls

Per UX spec §18, the privacy page is the home for data export and deletion
controls and FERPA-aware copy. Status:

- **Camera consent** — explicit. Onboarding states "Your video stays on your
  device — nothing is uploaded" before requesting access, and the app degrades
  gracefully (self-report drills) if the camera is denied or unavailable.
- **Export / delete my data** — specified in §18; wire these to delete the
  account's progress + account rows. (In-app `/privacy` page is currently a
  placeholder — `frontend/src/pages/Privacy.tsx` — and should host this copy +
  controls before any non-localhost deploy.)

## Deployment note

The privacy guarantee above assumes the production hardening in `CLAUDE.md`
(prod-deploy preconditions) is applied — in particular that dev affordances
(dev-login, seeded shared-password accounts) are disabled, since those are
authentication concerns that sit alongside this data-handling story.

## Attribution

Reference demonstration clips shown in lessons are from PopSign (Georgia Tech),
CC BY 4.0. They are demonstrator videos, not learner data.
