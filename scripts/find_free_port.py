"""Find the first free TCP port in a range (for dev startup scripts)."""
from __future__ import annotations

import argparse
import socket


def find_free_port(host: str, start: int, end: int) -> int:
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind((host, port))
            except OSError:
                continue
            return port
    raise RuntimeError(f"No free port on {host} in range {start}-{end}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Find a free local TCP port")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--start", type=int, default=8000)
    parser.add_argument("--end", type=int, default=8099)
    args = parser.parse_args()
    print(find_free_port(args.host, args.start, args.end))


if __name__ == "__main__":
    main()
