import os
import logging
import random
import requests
import json
import time
import string
import base64
from dotenv import load_dotenv
from discord.ext import tasks # Import tasks for the loop decorator

# Load environment variables
load_dotenv()

# Logging configuration
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Constants from your script
EPIC_API_URL = "https://api.epicgames.com"
OAUTH_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/oauth/token"
USER_INFO_BASE_URL = "https://account-public-service-prod.ol.epicgames.com/account/api/public/account"
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URL = os.getenv("REDIRECT_URL")
DATA_DIR = "data"
AUTH_CODES_FILE = os.path.join(DATA_DIR, "auth_codes.json")
TESTING_MODE = False

# Exceptions from your script
class EpicAPIError(Exception): pass
class TokenRequestError(EpicAPIError): pass
class AuthStorageError(EpicAPIError): pass
class UserInfoError(EpicAPIError): pass
class RefreshTokenError(EpicAPIError): pass

# Utility functions
def validate_env_vars():
    if not all([CLIENT_ID, CLIENT_SECRET, REDIRECT_URL]):
        raise EnvironmentError("Missing one or more required environment variables: CLIENT_ID, CLIENT_SECRET, REDIRECT_URL")

def generate_mock_token(prefix):
    return f"{prefix}_{''.join(random.choices(string.ascii_letters + string.digits, k=12))}"

def retry_request(method, url, headers=None, data=None, json=None, retries=3, backoff=1):
    for attempt in range(1, retries + 1):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                data=data,
                json=json
            )
            if 200 <= response.status_code < 300:
                return response
            else:
                # Log full response text for debugging
                logging.warning(f"Request failed (Attempt {attempt}/{retries}): {response.status_code} - {response.text}")
        except requests.exceptions.RequestException as e:
            logging.warning(f"Request exception (Attempt {attempt}/{retries}): {e}")
        
        if attempt < retries:
            time.sleep(backoff * attempt)
    raise EpicAPIError(f"Failed after {retries} attempts to {url}")

def get_basic_auth_header():
    basic = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded = base64.b64encode(basic.encode()).decode()
    return {
        "Authorization": f"Basic {encoded}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

def get_display_name(access_token, account_id):
    try:
        if TESTING_MODE:
            return f"MockDisplay_{random.randint(1000,9999)}"

        headers = {"Authorization": f"bearer {access_token}"}
        url = f"{USER_INFO_BASE_URL}?accountId={account_id}"
        response = retry_request("GET", url, headers=headers)
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            account_info = data[0]
            return account_info.get("displayName", "Unknown")
        else:
            logging.warning(f"Unexpected or empty account info response: {data}")
            return "Unknown"

    except Exception as e:
        logging.error(f"get_display_name() failed: {e}")
        raise UserInfoError(str(e))

def get_access_token(auth_code_data):
    """
    Exchange authorization code for access and refresh tokens.
    """
    validate_env_vars()
    try:
        if isinstance(auth_code_data, dict) and 'auth_code' in auth_code_data:
            auth_code = auth_code_data['auth_code']
        elif isinstance(auth_code_data, str):
            auth_code = auth_code_data
        else:
            raise ValueError("Invalid structure for auth_code")

        if TESTING_MODE:
            return {
                "access_token": generate_mock_token("mock_access"),
                "refresh_token": generate_mock_token("mock_refresh"),
                "expires_in": 300,
                "token_type": "bearer",
                "account_id": "mock_account_id",
                "display_name": f"MockUser_{random.randint(1000, 9999)}"
            }

        # Step 1: Get tokens from Epic OAuth
        headers = get_basic_auth_header()
        data = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URL
        }

        response = retry_request("POST", OAUTH_URL, headers=headers, data=data)
        tokens = response.json()

        if not all(k in tokens for k in ("access_token", "account_id")):
            raise TokenRequestError(f"Missing token fields in response: {tokens}")

        access_token = tokens["access_token"]
        account_id = tokens["account_id"]

        tokens["display_name"] = get_display_name(access_token, account_id)

        return tokens

    except Exception as e:
        logging.error(f"get_access_token() failed: {e}")
        raise TokenRequestError(str(e))

def save_tokens_and_auth_code(user_id: str, auth_code: str):
    try:
        tokens = get_access_token(auth_code)
        os.makedirs(DATA_DIR, exist_ok=True)

        auth_data = {}
        if os.path.exists(AUTH_CODES_FILE):
            try:
                with open(AUTH_CODES_FILE, "r") as f:
                    auth_data = json.load(f)
            except json.JSONDecodeError:
                logging.warning(f"Auth data file '{AUTH_CODES_FILE}' is corrupted. Starting with empty data.")
                auth_data = {}

        auth_data[user_id] = {
            "auth_code": auth_code, # Keep auth_code for initial setup, but not for refresh logic
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_in": tokens.get("expires_in"),
            "issued_at": time.time(),
            "display_name": tokens.get("display_name", "Unknown"),
            "account_id": tokens.get("account_id")
        }

        with open(AUTH_CODES_FILE, "w") as f:
            json.dump(auth_data, f, indent=4)

        logging.info(f"Auth data for user {user_id} saved.")
    except Exception as e:
        logging.error(f"save_tokens_and_auth_code() failed: {e}")
        raise AuthStorageError(f"Could not store auth data for {user_id}. Details: {e}")

def load_auth_data():
    try:
        if os.path.exists(AUTH_CODES_FILE):
            with open(AUTH_CODES_FILE, "r") as f:
                return json.load(f)
        else:
            logging.warning("No stored auth data found.")
            return {}
    except json.JSONDecodeError as e:
        logging.error(f"Failed to load auth data due to JSON decoding error: {e}")
        return {}
    except Exception as e:
        logging.error(f"Failed to load auth data: {e}")
        raise AuthStorageError("Failed to load authentication data.")


auth_codes = {} 


# --- Token Management Functions ---

@tasks.loop(minutes=5)
async def auto_refresh_tokens():

    global auth_codes # Declare global to modify the `auth_codes` dictionary

    logging.info("Starting auto_refresh_tokens cycle.")
    
    try:

        await check_and_refresh_tokens(auth_codes) 
        

        updated_auth_codes_from_file = load_auth_data() 
        
        # Compare and update the global in-memory dictionary
        if updated_auth_codes_from_file != auth_codes:
            auth_codes.clear() # Clear existing content
            auth_codes.update(updated_auth_codes_from_file) # Update with fresh data from file
            logging.info("Auth codes reloaded from file to sync in-memory state after refresh cycle.")
        else:
            logging.info("In-memory auth codes already consistent with file content. No explicit reload needed.")

    except Exception as e:
        logging.error(f"Error in auto_refresh_tokens background task: {e}")
        # Consider stopping the loop or adding more specific error handling/alerts here.


async def refresh_access_token(refresh_token: str):
    """
    Refreshes access token using the refresh token.
    """
    validate_env_vars()
    try:
        if TESTING_MODE:
            return {
                "access_token": generate_mock_token("refreshed_access"),
                "refresh_token": generate_mock_token("refreshed_refresh"),
                "expires_in": 300,
                "account_id": "mock_account_id",
                "display_name": f"RefreshedUser_{random.randint(1000,9999)}"
            }

        headers = get_basic_auth_header()
        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token
        }

        # This `retry_request` is synchronous and uses `requests`. 
        # For a truly non-blocking async solution, this should use `aiohttp`.
        response = retry_request("POST", OAUTH_URL, headers=headers, data=data) 
        tokens = response.json()

        if not all(k in tokens for k in ("access_token", "account_id")):
            raise RefreshTokenError(f"Missing token fields in refresh response: {tokens}")

        # This `get_display_name` is synchronous. 
        # For a truly non-blocking async solution, this should use `aiohttp`.
        tokens["display_name"] = get_display_name(tokens["access_token"], tokens["account_id"]) 
        
        # --- Crucial Debugging Step: Log the received tokens ---
        logging.info(f"API Response for refresh_access_token: "
                     f"Access Token: {tokens['access_token'][:10]}... (truncated) " # Log first 10 chars
                     f"Refresh Token: {tokens.get('refresh_token', 'N/A')[:10]}... (truncated) "
                     f"Expires In: {tokens.get('expires_in')}s")
        # --- End Debugging Step ---

        return tokens

    except Exception as e:
        logging.error(f"refresh_access_token() failed: {e}")
        raise RefreshTokenError(str(e))


async def check_and_refresh_tokens(auth_codes_data: dict):
    """
    Checks all user tokens for expiration and refreshes them if needed.
    Modifies the provided auth_codes_data dictionary in place and saves changes.
    """
    REFRESH_THRESHOLD = 500 
    current_time = int(time.time())
    
    # Create a list of user_ids to iterate over, as the dictionary might be modified (e.g., deletions)
    users_to_check = list(auth_codes_data.keys()) 
    
    changed_any_token = False

    for user_id in users_to_check:
        data = auth_codes_data.get(user_id) 
        if not data: # User might have been removed in a previous iteration or elsewhere
            continue

        issued_at = data.get("issued_at", 0)
        expires_in = data.get("expires_in", 28800) 
        
        if "refresh_token" not in data or not data["refresh_token"]:
            logging.warning(f"No refresh token found for user {user_id}. Cannot refresh. Removing associated data.")
            del auth_codes_data[user_id] # Remove data for users without a refresh token
            changed_any_token = True
            continue 

        time_left = (issued_at + expires_in) - current_time

        logging.debug(
            f"[{user_id}] Current time: {current_time}, "
            f"Issued at: {issued_at}, "
            f"Expires in: {expires_in}, "
            f"Time left: {time_left}s."
        )
        
        if time_left <= REFRESH_THRESHOLD:
            logging.info(f"Token for user {user_id} expiring in {time_left}s. Attempting refresh...")
            try:
                # Await the async refresh_access_token function
                tokens = await refresh_access_token(data["refresh_token"]) 
                
                # Compare current access_token with the newly refreshed one
                # This helps us identify if Epic Games actually issued a *new* token
                old_access_token_short = data.get("access_token", "N/A")[:10]
                new_access_token_short = tokens["access_token"][:10]

                if old_access_token_short == new_access_token_short and data.get("expires_in") == tokens.get("expires_in"):
                    logging.warning(f"Refreshed token for user {user_id} is identical to the old one (or very similar at start): Old: {old_access_token_short}, New: {new_access_token_short}. This might indicate the token was not truly expired by Epic.")
                else:
                    logging.info(f"Token for user {user_id} changed. Old: {old_access_token_short}..., New: {new_access_token_short}...")

                # Update the original auth_codes_data dictionary directly
                auth_codes_data[user_id].update({
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens.get("refresh_token", data["refresh_token"]), # Preserve if new one isn't given
                    "expires_in": int(tokens.get("expires_in", expires_in)),
                    "issued_at": int(time.time()), # IMPORTANT: Update issued_at to current time
                    "display_name": tokens.get("display_name", data.get("display_name", "Unknown")),
                    "account_id": tokens.get("account_id", data.get("account_id"))
                })
                changed_any_token = True
                logging.info(f"Successfully updated in-memory data for user {user_id} ({auth_codes_data[user_id].get('display_name', 'Unknown')}).")

            except RefreshTokenError as e: # Catch specific refresh token errors (e.g., invalid, expired)
                logging.error(f"Failed to refresh token for user {user_id}: {e}. Removing user data.")
                del auth_codes_data[user_id] # Remove user data if refresh fails critically
                changed_any_token = True
            except Exception as e: # Catch any other unexpected errors during refresh
                logging.error(f"An unexpected error occurred during token refresh for user {user_id}: {e}")

    if changed_any_token: # Only save if something actually changed in the data
        try:
            # Use your existing utility function to save the entire dictionary
            with open(AUTH_CODES_FILE, "w") as f:
                json.dump(auth_codes_data, f, indent=4)
            logging.info("Saved updated auth codes to file after refresh cycle.")
        except Exception as e:
            logging.error(f"Failed to save refreshed tokens to file: {e}")
            raise AuthStorageError("Could not save refreshed tokens after refresh cycle.")
    else:
        logging.info("No tokens needed refreshing or no changes detected in this cycle.")

    return auth_codes_data # Return the (potentially modified) dictionary

