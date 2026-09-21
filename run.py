"""Start the local-only web application."""
import argparse
import uvicorn
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run("app.server:app", host="127.0.0.1", port=args.port, access_log=False)
