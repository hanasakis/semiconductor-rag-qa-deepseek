"""Verify local Ollama has the required DeepSeek-R1 model available."""

import sys
import ollama


def main():
    base_url = "http://localhost:11434"
    required_model = "deepseek-r1:8b"

    print(f"Checking Ollama at {base_url} ...")

    try:
        client = ollama.Client(host=base_url)
        models = client.list()
    except Exception as e:
        print(f"ERROR: Cannot connect to Ollama at {base_url}")
        print(f"  {e}")
        print("  Is Ollama running? Run: ollama serve")
        return 1

    model_names = [m["name"] for m in models.get("models", [])]
    print(f"Found {len(model_names)} model(s):")
    for name in model_names:
        marker = " <-- REQUIRED" if name == required_model else ""
        print(f"  - {name}{marker}")

    if required_model not in model_names:
        print(f"\nERROR: Required model '{required_model}' not found!")
        print(f"  Pull it with: ollama pull {required_model}")
        return 1

    print(f"\nOK: '{required_model}' is available.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
