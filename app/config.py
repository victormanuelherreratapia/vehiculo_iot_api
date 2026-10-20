import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "vehiculo_iot")
    DB_PORT: int = int(os.getenv("DB_PORT", 3306))
    API_KEY: str = os.getenv("API_KEY", "")

settings = Config()