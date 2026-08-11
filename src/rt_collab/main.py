"""Process entrypoint: `uv run rt-collab` / `python -m rt_collab.main`."""

from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run("rt_collab.app:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
