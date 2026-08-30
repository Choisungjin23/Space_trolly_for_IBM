"""Backend startup configuration.

The local ``backend/.env`` file is optional.  Values already supplied by the
operating system win over values in that file so deployment configuration
continues to work as before.
"""

from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BACKEND_DIR / ".env"


def load_backend_env() -> bool:
    """Load backend/.env without overriding real OS environment variables."""
    return load_dotenv(dotenv_path=ENV_FILE, override=False)
