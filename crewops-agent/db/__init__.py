import os
from sqlalchemy import create_engine, text

# Load database URL from environment (as defined in .env)
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL env var not set")

engine = create_engine(DATABASE_URL, future=True)

def get_connection():
    return engine.connect()
