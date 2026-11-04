"""Test your Meta API key by itself, before running the full app.
Run:  python check_key.py
It makes two small calls and tells you in plain words what worked.
"""
import json
import os

import agent   # loads your .env file


def main():
    key = os.getenv("MODEL_API_KEY")
    if not key:
        print("X No key found. Make a file named .env next to this one with the line:")
        print("    MODEL_API_KEY=your-key-here")
        return
    print(f"Key found (starts with {key[:4]}..., {len(key)} characters).")
    try:
        client = agent.get_client()
    except Exception as e:
        print("X Could not set up the client:", e)
        return

    print("\nTest 1: say hello to Muse...")
    try:
        r = client.chat.completions.create(model=agent.MODEL, max_completion_tokens=2000, reasoning_effort="low",
                                           messages=[{"role": "user", "content": "Say hello in five words."}])
        said = (r.choices[0].message.content or "").strip()
        print("  OK. Muse says:", said or "(empty reply. The key works, but I want to see why:)")
        if not said:
            print("  finish_reason:", r.choices[0].finish_reason)
            print("  usage:", r.usage)
            try:
                print("  raw message:", str(r.choices[0].message.model_dump())[:600])
            except Exception:
                print("  raw message:", str(r.choices[0].message)[:600])
    except Exception as e:
        print("  X Failed:", e)
        print("  Check: key copied fully? credits claimed? Send me this error (not your key).")
        return

    print("\nTest 2: can Muse call one of our tools?")
    try:
        r = client.chat.completions.create(
            model=agent.MODEL, tools=agent.TOOL_DEFS, max_completion_tokens=300,
            messages=[{"role": "user", "content": "Find a pediatrician near Issaquah. Use a tool."}])
        calls = r.choices[0].message.tool_calls or []
        if calls:
            print("  OK. Muse chose the tool:", calls[0].function.name)
            print("  with:", json.dumps(json.loads(calls[0].function.arguments)))
        else:
            print("  Muse answered in text instead of calling a tool (not an error). It said:")
            print("  ", (r.choices[0].message.content or "")[:200])
    except Exception as e:
        print("  X Failed:", e)
        print("  Send me this error text (not your key) and I will fix the code.")
        return
    print("\nAll good. Now run:  python app.py")


if __name__ == "__main__":
    main()
