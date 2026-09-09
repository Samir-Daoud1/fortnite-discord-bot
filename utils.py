import os
import json
import logging
from cryptography.fernet import Fernet

DATA_DIR = "data"
AUTH_CODES_FILE = os.path.join(DATA_DIR, "auth_codes.json")
KEY_FILE = os.path.join(DATA_DIR, "secret.key")

# === Logging setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# === Encryption Key Utilities ===
def generate_key():
    key = Fernet.generate_key()
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(KEY_FILE, "wb") as key_file:
        key_file.write(key)
    return key

def load_key():
    if not os.path.exists(KEY_FILE):
        return generate_key()
    with open(KEY_FILE, "rb") as key_file:
        return key_file.read()

# === Encrypt & Decrypt Functions ===
fernet = Fernet(load_key())

def encrypt(data: str) -> str:
    return fernet.encrypt(data.encode()).decode()

def decrypt(token: str) -> str:
    return fernet.decrypt(token.encode()).decode()

# === JSON Auth Code Storage ===
def load_auth_codes() -> dict:
    """Loads and decrypts the auth_codes.json file."""
    if not os.path.exists(AUTH_CODES_FILE):
        logging.info("No auth_codes.json found. Returning empty dictionary.")
        return {}

    try:
        with open(AUTH_CODES_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load auth codes: {e}")
        return {}

def save_auth_codes(data: dict):
    """Encrypts and saves the auth codes to file."""
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(AUTH_CODES_FILE, "w") as f:
            json.dump(data, f, indent=4)
        logging.info("Auth codes saved successfully.")
    except Exception as e:
        logging.error(f"Failed to save auth codes: {e}")
        raise e
