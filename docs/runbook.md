# Mona runbook (Claudiu)

On the Mona box, in a terminal, `mona` is the command `deploy/bin/mona` in the Mona folder.

## The address
Open exactly the address `mona doctor` prints on its **origin** line (`MONA_PUBLIC_ORIGIN`). Any other spelling (`127.0.0.1` for `localhost`, another port) and every save is refused with "Not allowed".

## Before the talk (T-10 min)
1. `mona doctor` -> every line GREEN. RED names what is wrong (see below). AMBER works, but note it.
2. `mona demo-reset --anchor today`, answer `y`. It ends with "done" and a green doctor.
3. Browser on Home, 1440 wide, English, light. Check the projector.
4. Warm-up: open Chat, send one question ("What is due this month?") and wait for the answer. The first answer is the slow one.
5. Phone paired for the volunteered document.

## Start and stop
- `mona stop` stops everything. `mona up` starts it again and waits until it is healthy; then `mona doctor`.
- Stuck? `mona stop`, wait 10 seconds, `mona up`. The documents and the history are kept.
- `mona demo-reset --prefiled` restores the same day with the batch already filed (fallback for beat 2).

## Rehearsal (Andrei)
`mona stage-build` rebuilds the stage from scratch. To keep a good debrief: `mona demo-reset`, drop the live batch, judge the questions; if they are good, `mona demo-snapshot --refresh-textcache --name demo`.

## If Mona is offline or slow, beat by beat
| Beat | Do |
|---|---|
| Meet Mona | Home errors: open the Activity log; the brief is computed from the database |
| The pile | Pipeline stalled: `mona demo-reset --prefiled`, show the Activity log |
| Evidence | Highlight misses: read the quotes in the side panel |
| Back to the pile | Batch unfinished: narrate the rows still moving and go on |
| Mona asks | The rehearsed debrief, from the cache. Apply fails: Rules › Disabled, enable the rule for that question, check its preview, Apply |
| Ask Mona | Model stalls: show the same answers in Archive and Activity |
| Volunteered document | Upload from the phone browser to Intake with "Visitor document" checked |
| Trust | Undo errors: show the journal entries and their before and after paths |
| Close | The deck slides |

Whole box unreachable: tell the room, present from the deck. The cloud demo mode (laptop) is Andrei's call.

## What to say about privacy
"The document and everything Mona derived from it are deleted after 24 hours." That covers the file, the extracted data, suggestions, deadlines and journal. A conversation about it stays in the chat. At the close: "Mona runs on this box; nothing leaves the building." Under the cloud demo mode, say it is the cloud demo mode and skip that line.

## Who to call
Andrei (on site): ____________ . Backup: ____________ .
