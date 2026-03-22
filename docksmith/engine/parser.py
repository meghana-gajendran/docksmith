# docksmith/engine/parser.py
import json
import sys
from dataclasses import dataclass
from typing import List

VALID_OPS = {"FROM", "COPY", "RUN", "WORKDIR", "ENV", "CMD"}


@dataclass
class Instruction:
    lineno: int
    op:     str
    args:   str


def parse(docksmithfile_path: str) -> List[Instruction]:
    """
    Parse a Docksmithfile and return a list of Instructions.
    Exits with a clear error on any problem.
    """
    instructions = []

    with open(docksmithfile_path, "r") as f:
        lines = f.readlines()

    for lineno, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#"):
            continue

        # Split into opcode and arguments
        parts = line.split(None, 1)   # split on first whitespace only
        op    = parts[0].upper()
        args  = parts[1].strip() if len(parts) > 1 else ""

        # Unknown instruction → immediate failure
        if op not in VALID_OPS:
            print(f"Error on line {lineno}: unknown instruction '{op}'", file=sys.stderr)
            sys.exit(1)

        # First real instruction must be FROM
        if not instructions and op != "FROM":
            print(f"Error on line {lineno}: Docksmithfile must begin with FROM", file=sys.stderr)
            sys.exit(1)

        # CMD must be a valid JSON array
        if op == "CMD":
            try:
                parsed = json.loads(args)
                if not isinstance(parsed, list):
                    raise ValueError("not a list")
            except (json.JSONDecodeError, ValueError):
                print(
                    f"Error on line {lineno}: CMD requires a JSON array, got: {args}",
                    file=sys.stderr,
                )
                sys.exit(1)

        instructions.append(Instruction(lineno=lineno, op=op, args=args))

    # Must have at least a FROM
    if not instructions:
        print("Error: Docksmithfile is empty", file=sys.stderr)
        sys.exit(1)

    return instructions
