# ARIA intelligence architecture

ARIA's `AriaCore.process_input` coordinates intent detection, context resolution,
emotion and personality, relationship lookup, access-controlled memory retrieval,
reasoning, local actions, response generation, and conversation updates. General
conversation uses the configured cloud model; productivity, memory, goals, and
document extraction can use local services.

## Context and memory

- `ConversationManager` keeps at most 20 recent turns per requester, expires turns
  after six hours, and retains a bounded extractive summary of removed user topics.
  Goals and topics are scoped to that same conversation owner.
- `MemoryManager` stores durable, selectively captured memories in SQLite. Exact
  duplicates reinforce the existing record and increase its occurrence count;
  ordinary chat is not automatically persisted. Each owner is limited to 500
  records. When full, ARIA asks the user to review or forget memories instead of
  silently discarding them.
- Retrieval ranks a small set using the current request, recent context, active
  goal, and a recognized person. Conflicting records are retained; the response
  planner is instructed to surface relevant conflicts and ask which is current.

Memory privacy defaults to `PERSONAL`. `PRIVATE` and `PERSONAL` records are
available only to their owner. `SHARED` records are available only to explicitly
listed requester IDs; `PUBLIC` records may be retrieved by any requester.
`PRIVATE` records are never shared. For example, an explicit request can use
`Remember privately that ...` or `Remember to share with friend: ...`. Memory
management operations are also restricted to records owned by the requester.

`RelationshipManager` stores a person's name and nickname, flexible relationship
type, preferences, shared interests, trust level, privacy boundaries, and context.
Memories can be linked to a person with `subject_person`; relationship details
are added to reasoning context only for the primary user.

## Requester identity and privacy

Callers may pass `requester_id` to `process_input` so conversation history and
memory access are scoped to the recognized speaker. The default remains
`primary_user` for existing single-user callers. A caller must supply this value
from a trusted identity or speaker-verification layer; do not accept an
unauthenticated client-supplied ID as proof of identity.

Requests to disclose private conversations receive a natural refusal before
cloud response generation. Session history is not shared between requester IDs.

## Offline behavior

When cloud generation times out or the provider cannot be reached, ARIA uses
bounded local responses, saved context, goals, and a small set of basic Python
explanations. This is not a general-purpose offline language model. Open-ended
factual generation and live web research require their configured cloud or search
provider; ARIA reports configuration and provider failures rather than claiming
those capabilities ran locally.

## Creation, research, safety, and actions

The capability router selects existing document generation, web research, and
allowlisted computer-automation workflows from the same ARIA conversation
entry point. PPTX, DOCX, PDF, XLSX, TXT, and Markdown generation runs through
the configured cloud model, validates the requested output structure, writes
to ARIA's generated-files directory, and returns the actual file path. A
presentation request is not reported as complete unless a valid presentation
file was written. Image, video, and audio generation are not implemented;
ARIA says so and can help prepare a prompt or production plan instead.

Explicit web research uses the configured search provider, passes provider
snippets as untrusted data to synthesis, and returns the source links and
publication dates supplied by that provider. Evidence coverage reports the
number of distinct source domains. Summaries are snippet-only and are not
independently cross-checked, so ARIA labels confidence as limited rather than
treating provider results as confirmed facts.

Website safety checks are local URL heuristics only. They flag visible
characteristics such as plaintext HTTP, URL shorteners, user information,
IP-literal hosts, punycode, and brand-name lookalikes. They do not visit the
website, consult a live threat-intelligence feed, or prove that a page is
malicious or safe. The result is explicitly presented as an uncertain signal.

Computer automation continues to use allowlisted targets, risk classifications,
confirmation gates, execution limits, and audit records. Actions that could
delete, send, publish, or purchase are not made available merely by selecting a
capability. Existing goal storage is integrated with conversation intent; ARIA
does not silently close applications or monitor activity to enforce a goal.

## Voice, vision, and ambient mode

The voice pipeline uses the existing ARIA request path. Microphone capture is
one utterance at a time; the browser and desktop interfaces keep continuous
listening off until the user enables it. Browser recognition sends the recorded
clip to Google's online transcription service. Local speech output uses the
installed Windows voice and can be interrupted. ARIA and JARVIS-style voice
personas change presentation and voice selection, not the underlying assistant
identity or reasoning.

Vision is off by default and starts only after an explicit camera action. The
optional local OpenCV service reports face counts only; it does not identify
people or infer emotion, and it releases the camera when stopped. Frames are
transient and are not uploaded or retained.

Ambient mode is independently opt-in and currently approves only a focused-work
timer. It does not monitor the microphone, camera, or screen. Reminders are
suppressed during active voice interactions and rate-limited; they are shown as
text rather than spoken over the user. Local voice output and face detection do
not make cloud-dependent transcription or open-ended conversation available
offline.
