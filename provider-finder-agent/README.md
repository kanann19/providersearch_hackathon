# CareScout: a provider-finder agent

Finding a doctor means checking five websites: who takes my insurance, who treats
what I need, who is taking new patients, when is the next opening, and what do other
patients say. CareScout does that in one conversation, by voice or text.

> **All provider data is SAMPLE data** (129 made-up providers). Nothing is real.
> CareScout only finds providers. It never diagnoses or gives medical advice.
> For emergencies, call 911. It never asks for a member ID.

## How it works

You say: *"Sinus specialist near Bellevue, Aetna PPO."*

Muse Spark (Meta Model API) runs an agent loop. It decides which tool to call, reads
the result, and decides what to do next:

| Tool | What it does |
|---|---|
| `search_providers` | Filter by specialty, focus (sinus, adenoids, PCOS...), city, distance, insurance plan, gender, kids, telehealth, language |
| `check_availability` | Next open dates |
| `get_reviews` | Patient reviews, which Muse reads and summarizes (wait time, phone access, listening) |
| `get_community_mentions` | Sample community-group posts about a provider |
| `find_alternatives` | If a provider is full, finds similar ones who are accepting |
| `compare_providers` | Muse scores the top picks side by side (short wait, easy to reach, listens well) from reviews. The tool refuses any row whose quote is not word for word in that doctor's reviews. |
| `draft_contact` | Writes a call script, text, or email. It never sends anything. |

If nothing matches, Muse widens the distance or drops a filter and says what changed.

**Safety checks (plain code, not AI):**
- Every doctor name in the final answer must have come from a tool result.
- Every "patients say" quote must appear word for word in a real review or community
  post that a tool returned (`checks.py`). If a check fails, the agent is told to rewrite
  its answer once, and a warning is shown if it still fails. This idea comes from Meta's
  workshop: the agent can't claim something unless code confirms it.
- Turn cap on the agent loop; a friendly message if the model can't be reached.
- Every run is saved to `runs/` so what the agent did can be inspected.

## Run it

1. Install Python 3.9+.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and paste your Meta Model API key (get one at dev.meta.ai).
4. `python check_key.py` to test your key on its own.
5. `python app.py`, then open http://localhost:5000
6. Voice: with a key, the mic uses **Muse Voice Transcribe** (pick a language next to "Read answers aloud").
   If that is not available it falls back to the browser's own speech (Chrome or Edge).
7. Tap the camera button to read your insurance plan from a card photo. Only the plan name is kept.

## Tests (no API key needed)

`pip install -r requirements-dev.txt` then `python -m pytest -q`

About 100 tests cover: the tools, the sample data, the quote and name checks, the agent loop when
the model misbehaves (fake quotes, made-up doctors, empty replies, errors), the web routes,
the insurance card privacy rules, the voice relay, and a real-browser click-through
(`test_browser.py` is skipped unless Playwright is installed).

## Files

- `app.py`: small web server
- `index.html`: the page (text box, mic, result cards)
- `agent.py`: the Muse agent loop, system prompt, and safety checks
- `tools.py`: the tools the agent can call
- `extras.py`: insurance card photo reader (Muse Spark vision) and the voice relay (Muse Voice Transcribe)
- `test_*.py`, `conftest.py`: the tests
- `checks.py`: plain-code checks on the answer (doctor names and quotes)
- `check_key.py`: tests your API key and tool calling before you run the app
- `providers.json` / `providers.csv`: the sample provider data
- `mock_model.py`: a fake model used only to test the loop offline. It is not used in the demo.

## Built during the hackathon (Oct 26 to Nov 4, 2026)

Everything in this repository was built during the event: the sample dataset, the tools,
the agent loop and safety checks, the web page, voice input, and the insurance card reader.

Team: Keerthi Ananthula

Built with Meta's Muse Spark through the Meta Model API. An AI coding assistant helped
with code, and the team designed the idea, tested, and made the decisions.

## Next steps

Connect the tools to a real provider directory and real booking systems, add secure
messaging.
