import sys
from supervisor import childutils


def main():
    while True:
        headers, payload = childutils.listener.wait(sys.stdin, sys.stdout)
        payload_headers, data = childutils.eventdata(payload + "\n")

        process_name = payload_headers.get("processname", "unknown")
        channel = payload_headers.get("channel", "unknown")

        print(f"[{process_name}:{channel}] {data.rstrip()}", file=sys.stderr, flush=True)

        childutils.listener.ok(sys.stdout)


if __name__ == "__main__":
    main()