"""Command line: try a message locally, or run the intake server.

  concierge draft "Hi, I'm new and need a cleaning, Tue mornings work" --email jane@x.com
      (adds it to the Front Desk dashboard queue)
  concierge draft --preview "my tooth is killing me"   (print only)
  concierge serve --port 8000
"""

from __future__ import annotations

import argparse
import logging

from .config import load_config
from .models import PatientRequest
from .pipeline import build_draft, process, receive


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="concierge")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("draft", help="turn one message into a draft")
    d.add_argument("message")
    d.add_argument("--name")
    d.add_argument("--email")
    d.add_argument("--phone")
    d.add_argument("--preview", action="store_true", help="print only, don't add to the queue")
    d.add_argument("--no-llm", action="store_true", help="use keyword triage instead of Gemini")

    s = sub.add_parser("serve", help="run intake + dashboards")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO)

    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("concierge.api:app", host=args.host, port=args.port)
        return

    cfg = load_config()
    req = PatientRequest(message=args.message, name=args.name, email=args.email, phone=args.phone, source="cli")
    use_llm = False if args.no_llm else None
    if args.preview:
        draft = build_draft(req, cfg, use_llm=use_llm)
        ref = "(preview, not saved)"
    else:
        request_id = receive(req)
        draft = process(request_id, cfg, use_llm=use_llm)
        ref = f"request #{request_id} in the Front Desk queue"
    print(f"type: {draft.triage.request_type}  (triaged by {draft.triage.triaged_by})")
    print(f"to: {draft.to or '(no email given: desk fills in)'}")
    print(f"subject: {draft.subject}\n")
    print(draft.body)
    print(f"\nsaved: {ref}")


if __name__ == "__main__":
    main()
