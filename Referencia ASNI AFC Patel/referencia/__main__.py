import os
# Direct dot products benefit from avoiding a BLAS thread team per lag.
# Users can override this explicitly before launching the process.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")

import argparse
import sys
from .campaign import compare, run


def main():
    parser = argparse.ArgumentParser(description="Referencia independiente ASNI AFC Patel")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("run")
    p.add_argument("--rate", type=int, choices=(16000, 48000), required=True)
    p.add_argument("--cpp", help="Comparator executable path")
    p = sub.add_parser("all")
    p.add_argument("--cpp", help="Comparator executable path")
    p = sub.add_parser("compare")
    p.add_argument("--run16")
    p.add_argument("--run48")
    p = sub.add_parser("audit-session")
    p.add_argument("--session", required=True)
    args = parser.parse_args()
    try:
        if args.command == "audit-session":
            from .session_audit import audit_session
            ok, _ = audit_session(args.session)
        elif args.command == "run":
            ok, _ = run(args.rate, args.cpp)
        elif args.command == "all":
            ok16, id16 = run(16000, args.cpp)
            ok48, id48 = run(48000, args.cpp)
            ok, _ = compare({16000: id16, 48000: id48})
            ok = ok and ok16 and ok48
        else:
            if bool(args.run16) != bool(args.run48):
                parser.error("Supply both --run16 and --run48, or neither")
            ok, _ = compare({16000: args.run16, 48000: args.run48} if args.run16 else None)
        return 0 if ok else 1
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
