#!/usr/bin/env python
"""Lightweight CLI for chatting with the configured Gemini model."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable

import google.generativeai as genai

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

API_KEY_ENV = "GEMINI_API_KEY"


def _configure_client(model_name: str | None) -> genai.GenerativeModel:
    api_key = os.environ.get(API_KEY_ENV)
    if not api_key:
        raise RuntimeError(
            f"Environment variable {API_KEY_ENV} must be set with your Gemini API key."
        )
    genai.configure(api_key=api_key)
    target_model = model_name or "models/gemini-2.5-flash"
    return genai.GenerativeModel(target_model)


def _print_blocks(role: str, parts: Iterable[str]) -> None:
    header = "You" if role == "user" else "Gemini"
    print(f"{header}: ")
    for part in parts:
        print(part)
    print()


def run_once(message: str, model_name: str | None) -> int:
    model = _configure_client(model_name)
    response = model.generate_content(message)
    _print_blocks("user", [message])
    _print_blocks("model", [response.text or "(no text response)"])
    return 0


def run_interactive(model_name: str | None) -> int:
    model = _configure_client(model_name)
    chat = model.start_chat(history=[])
    print("Interactive Gemini session. Type 'exit' or 'quit' to end.\n")
    while True:
        try:
            message = input("You: ")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!" )
            return 0
        if message.strip().lower() in {"exit", "quit"}:
            print("Goodbye!")
            return 0
        if not message.strip():
            continue
        reply = chat.send_message(message)
        print(f"Gemini: {reply.text or '(no text response)'}\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Send prompts to Gemini or run an interactive chat session."
    )
    parser.add_argument(
        "message",
        nargs="?",
        help="Single message to send. If omitted, interactive mode is started.",
    )
    parser.add_argument(
        "--model",
        dest="model",
        default=None,
        help="Optional override for the Gemini model name.",
    )

    args = parser.parse_args(argv)

    if args.message:
        return run_once(args.message, args.model)
    return run_interactive(args.model)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
