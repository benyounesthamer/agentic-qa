import argparse

import uvicorn

p = argparse.ArgumentParser()
p.add_argument("--port", type=int, default=8000)
args = p.parse_args()
uvicorn.run("demo_app.app:app", host="127.0.0.1", port=args.port, log_level="warning")
