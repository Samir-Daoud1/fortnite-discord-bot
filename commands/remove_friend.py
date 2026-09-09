import discord
from discord import app_commands
import aiohttp
import json
import logging
import asyncio # Import asyncio for sleep

# Import load_auth_codes from your utils.py
from utils import load_auth_codes

# Configure logging for this module
logger = logging.getLogger(__name__)

# --- Rate Limiting Configuration ---
# Delay in seconds between individual API requests to Epic Games for display name lookups.
# This is crucial for preventing rate limits when resolving a friend's name.
REQUEST_DELAY_SECONDS = 0.5 # 1000 milliseconds (1 second) delay between individual requests

# --- Internal Helper Function to fetch display names ---
async def _fetch_display_names(access_token: str, account_ids: list[str]) -> dict[str, str]:
    """
    Internal helper to fetch display names for a list of Epic Games account IDs.
    Iterates through each account ID and uses the direct /account/api/public/account endpoint,
    correctly parsing the 'id' field from the response.
    Includes a delay between requests to prevent rate limiting.
    Returns a dictionary mapping accountId to displayName.
    Handles cases where 'displayName' might be missing in the response and Epic Games 429 (Too Many Requests) errors.
    """
    if not account_ids:
        return {}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    display_names = {}
    async with aiohttp.ClientSession() as session:
        for i, account_id in enumerate(account_ids):
            url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}"
            
            # Simple retry logic for 429 errors
            retries = 3
            for attempt in range(retries):
                try:
                    async with session.get(url, headers=headers) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if isinstance(data, dict) and 'id' in data:
                                # Prefer 'displayName', fallback to 'id' if not present
                                display_name = data.get('displayName')
                                if display_name:
                                    display_names[data['id']] = display_name
                                    logger.debug(f"Successfully fetched display name for {account_id}: {display_name}.")
                                else:
                                    display_names[data['id']] = data['id'] # Fallback to ID
                                    logger.debug(f"Display name not found for {account_id}, using account ID as fallback. Raw data: {data}")
                                break # Exit retry loop on success
                            elif resp.status == 429: # Handle rate limit specifically
                                retry_after = resp.headers.get("Retry-After")
                                wait_time = int(retry_after) if retry_after else 60 # Default to 60 seconds if header missing
                                logger.warning(f"Rate limited by Epic Games for {account_id}. Retrying after {wait_time} second(s). Attempt {attempt + 1}/{retries}")
                                await asyncio.sleep(wait_time)
                            else:
                                error_data = await resp.text()
                                logger.error(f"Failed to fetch display name for {account_id}: HTTP Status {resp.status} - Response: {error_data}")
                                break # Don't retry for other non-429 errors
                except aiohttp.ClientError as e:
                    logger.error(f"Network error during display name fetch for {account_id} (Attempt {attempt + 1}/{retries}): {e}")
                    if attempt < retries - 1:
                        await asyncio.sleep(5) # Small delay before retrying network errors
                    else:
                        logger.error(f"Max retries reached for network error for {account_id}.")
                except json.JSONDecodeError:
                    error_text = await resp.text()
                    logger.error(f"Failed to parse JSON response for display name for {account_id}: Status {resp.status if 'resp' in locals() else 'N/A'} - Raw response: {error_text}")
                    break # Don't retry for JSON decode errors
                except Exception as e:
                    logger.error(f"An unexpected error occurred during display name fetch for {account_id} (Attempt {attempt + 1}/{retries}): {e}", exc_info=True)
                    break # Don't retry for unexpected exceptions

            # Introduce a delay between requests, but only if not the last item and not just retried a 429
            if i < len(account_ids) - 1:
                await asyncio.sleep(REQUEST_DELAY_SECONDS)
                logger.debug(f"Paused for {REQUEST_DELAY_SECONDS} seconds before next display name fetch.")

    logger.info(f"Finished fetching display names. Total successful: {len(display_names)}.")
    return display_names


# --- Internal Helper Function to fetch raw friend list ---
async def _fetch_epic_friends_list(access_token: str, account_id: str) -> list:
    """
    Internal helper to fetch the Epic Games friend list for a given account ID.
    Returns a list of raw friend dictionaries (with 'accountId' but no 'displayName' initially).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    base_url = "https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/"
    friends_url = f"{base_url}{account_id}"

    friends_raw_data = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(friends_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if isinstance(data, list):
                        friends_raw_data = data
                        logger.info(f"Successfully fetched {len(friends_raw_data)} raw friend entries for account {account_id}.")
                    else:
                        logger.warning(
                            f"Unexpected API response structure for friends list for account {account_id}. "
                            f"Expected a list, got: {type(data).__name__}. Raw data: {data}"
                        )
                        return []
                else:
                    error_data = await resp.text()
                    logger.error(
                        f"Failed to fetch raw friends list for account {account_id}: "
                        f"HTTP Status {resp.status} - Response: {error_data}"
                    )
                    if resp.status == 401: logger.error("Authentication failed: Access token might be expired or invalid.")
                    elif resp.status == 403: logger.error("Forbidden: Token lacks necessary permissions.")
                    elif resp.status == 404: logger.error("Not Found: User account ID might be incorrect or API endpoint changed.")
                    return []
    except aiohttp.ClientError as e:
        logger.error(f"Network error during raw friend list fetch for account {account_id}: {e}")
        return []
    except json.JSONDecodeError:
        error_text = await resp.text()
        logger.error(f"Failed to parse JSON response for raw friends list for account {account_id}: "
                     f"Status {resp.status if 'resp' in locals() else 'N/A'} - Raw response: {error_text}")
        return []
    except Exception as e:
        logger.error(f"An unexpected error occurred during raw friend list fetch for account {account_id}: {e}", exc_info=True)
        return []

    return friends_raw_data

# --- New Function: Resolve Friend Name to Account ID ---
async def _resolve_friend_name_to_id(access_token: str, user_account_id: str, target_display_name: str) -> str | None:
    """
    Resolves a friend's display name to their Epic Games account ID by iterating through the friend list
    and fetching display names one by one with delays.

    Args:
        access_token (str): The Epic Games access token.
        user_account_id (str): The Epic Games account ID of the user whose friends list is being searched.
        target_display_name (str): The display name of the friend to find.

    Returns:
        str | None: The account ID of the friend if found, otherwise None.
    """
    logger.info(f"Attempting to resolve friend name '{target_display_name}' for user {user_account_id}.")
    
    raw_friends = await _fetch_epic_friends_list(access_token, user_account_id)
    if not raw_friends:
        logger.info(f"No raw friends found for user {user_account_id} to resolve name '{target_display_name}'.")
        return None

    found_account_id = None
    for i, friend_entry in enumerate(raw_friends):
        if not isinstance(friend_entry, dict) or 'accountId' not in friend_entry:
            logger.warning(f"Skipping malformed friend entry: {friend_entry}")
            continue

        friend_id = friend_entry['accountId']
        
        # Fetch display name for this single friend ID
        display_name_map = await _fetch_display_names(access_token, [friend_id])
        
        fetched_display_name = display_name_map.get(friend_id)

        if fetched_display_name and fetched_display_name.lower() == target_display_name.lower():
            found_account_id = friend_id
            logger.info(f"Successfully resolved '{target_display_name}' to account ID: {found_account_id}.")
            break # Found the friend, stop searching

        # Introduce delay between individual display name lookups
        if i < len(raw_friends) - 1:
            await asyncio.sleep(REQUEST_DELAY_SECONDS)
            logger.debug(f"Paused for {REQUEST_DELAY_SECONDS} seconds before next friend name lookup.")

    if not found_account_id:
        logger.info(f"Friend '{target_display_name}' not found in friend list for user {user_account_id}.")
    
    return found_account_id


async def _perform_epic_friend_removal_api_call(access_token: str, user_account_id: str, friend_account_id: str) -> tuple[bool, str]:
    """
    Internal helper to make the API call to remove an Epic Games friend.
    Returns (success: bool, message: str).
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    url = f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{user_account_id}/{friend_account_id}"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status == 204:
                    logger.info(f"Successfully removed friend {friend_account_id} for user {user_account_id}.")
                    return True, "✅ Successfully removed friend."
                else:
                    error_data = {}
                    try:
                        error_data = await resp.json()
                    except json.JSONDecodeError:
                        error_text = await resp.text()
                        logger.error(f"Failed to parse JSON error from Epic Games API ({resp.status}): {error_text}")
                        return False, f"❌ Failed to remove friend: Received an unreadable error from Epic Games ({resp.status})."

                    error_code = error_data.get("errorCode", "unknown_error")
                    error_message = error_data.get("errorMessage", "No specific message provided.")
                    numeric_error_code = error_data.get("numericErrorCode", "N/A")
                    originating_service = error_data.get("originatingService", "unknown")

                    log_message = (
                        f"Epic Games API error removing friend: {resp.status} - "
                        f"Code: {error_code}, Message: '{error_message}', "
                        f"Numeric: {numeric_error_code}, Service: {originating_service}"
                    )
                    logger.error(log_message)

                    user_feedback_message = f"❌ Failed to remove friend: {error_message} (Code: {numeric_error_code})"
                    if resp.status == 404:
                        user_feedback_message = "❌ Friend not found or already removed. Please check the friend list."
                    elif resp.status == 403:
                        user_feedback_message = "❌ Permission denied. Your authentication might be expired. Please try `/login`."
                    elif resp.status == 401:
                        user_feedback_message = "❌ Your Epic Games session has expired. Please use `/login` again."

                    return False, user_feedback_message
    except aiohttp.ClientError as e:
        logger.error(f"Network error during friend removal API call: {e}")
        return False, f"❌ Network error: Could not connect to Epic Games servers."
    except Exception as e:
        logger.error(f"An unexpected error occurred during friend removal: {e}")
        return False, f"❌ An unexpected error occurred: {str(e)}"

# === Main Command Execution Function (to be called by main_bot_script.py) ===

async def execute_remove_friend_command(interaction: discord.Interaction, friend_name: str):
    """
    Executes the main logic for the /remove-friend command.
    Resolves the friend's name to an account ID before attempting removal.
    """
    await interaction.response.defer(ephemeral=True) # Defer immediately

    auth_codes = load_auth_codes()
    user_id = str(interaction.user.id)

    if user_id not in auth_codes:
        embed = discord.Embed(
            title="Authentication Required",
            description="❌ You're not logged in. Please use `/login` first.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    user_auth_data = auth_codes.get(user_id)
    if not user_auth_data:
        embed = discord.Embed(
            title="Authentication Error",
            description="❌ Your authentication data wasn't found. Please relog.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    access_token = user_auth_data.get("access_token")
    account_id = user_auth_data.get("account_id")
    if not access_token or not account_id:
        embed = discord.Embed(
            title="Authentication Incomplete",
            description="❌ Your authentication data is incomplete. Please try logging in again with `/login`.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    if not friend_name:
        embed = discord.Embed(
            title="No Friend Name Provided",
            description="❌ Please provide the Epic Games display name of the friend you want to remove.",
            color=discord.Color.orange()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # --- Resolve friend name to account ID ---
    # This part can be slow for many friends due to rate limiting.
    # We will send an initial message to the user to manage expectations.
    initial_message_embed = discord.Embed(
        title="Searching for Friend...",
        description=f"🔍 Looking for friend '{friend_name}' in your Epic Games friends list. This might take a moment if you have many friends.",
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=initial_message_embed, ephemeral=True)

    friend_account_id_to_remove = None
    try:
        friend_account_id_to_remove = await _resolve_friend_name_to_id(access_token, account_id, friend_name)
    except Exception as e:
        logger.error(f"Error during friend name resolution for '{friend_name}': {e}", exc_info=True)
        embed = discord.Embed(
            title="Friend Lookup Failed",
            description=f"❌ An unexpected error occurred while trying to find '{friend_name}'. Please try again or provide the exact Epic Account ID if you know it.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return


    if not friend_account_id_to_remove:
        embed = discord.Embed(
            title="Friend Not Found",
            description=f"❌ Could not find a friend named '**{friend_name}**' in your Epic Games friends list. Please ensure the name is spelled correctly.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    # --- Proceed with removal once ID is found ---
    success, message = await _perform_epic_friend_removal_api_call(access_token, account_id, friend_account_id_to_remove)
    
    if success:
        # Use the provided friend_name for the success message, as it's what the user typed
        embed = discord.Embed(
            title="Friend Removal Successful",
            description=f"✅ You have successfully removed **{friend_name}** from your Epic Games friends list.",
            color=discord.Color.green()
        )
    else:
        embed = discord.Embed(
            title="Friend Removal Failed",
            description=message,
            color=discord.Color.red()
        )
        if "Friend not found or already removed" in message:
            embed.color = discord.Color.orange()

    await interaction.followup.send(embed=embed, ephemeral=True)
