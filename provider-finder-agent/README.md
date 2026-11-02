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
| `draft_contact` | Writes a call script, text, or email. It never sends anything. |

If nothing matches, Muse widens the distance or drops a filter and says what changed.

**Safety checks (plain code, not AI):**
- Every doctor name in the final answer must have come from a tool result. If not, the
  agent is told to rewrite it, and a warning is shown if it still fails.
- Turn cap on the agent loop; a friendly message if the model can't be reached.
- Every run is saved to `runs/` so what the agent did can be inspected.

## Run it

1. Install Python 3.9+.
2. `pip install -r requirements.txt`
3. Copy `.env.example` to `.env` and paste your Meta Model API key (get one at dev.meta.ai).
4. `python app.py`, then open http://localhost:5000
5. Voice input works in Chrome and Edge.

Test the tools without any API key: `python test_tools.py`

## Files

- `app.py`: small web server
- `index.html`: the page (text box, mic, result cards)
- `agent.py`: the Muse agent loop, system prompt, and safety checks
- `tools.py`: the six tools the agent can call
- `providers.json` / `providers.csv`: the sample provider data
- `mock_model.py`: a fake model used only to test the loop offline. It is not used in the demo.

## Built during the hackathon (Oct 26 to Nov 4, 2026)

Everything in this repository was built during the event: the sample dataset, the tools,
the agent loop and safety checks, the web page, and voice input.

Team: _(add your names here)_

Built with Meta's Muse Spark through the Meta Model API. An AI coding assistant helped
with code, and the team designed the idea, tested, and made the decisions.
_(Check the Official Rules on AI assistance and edit this line if needed.)_

## Next steps

Connect the tools to a real provider directory and real booking systems, add secure
messaging, and use Muse Voice for transcription.
