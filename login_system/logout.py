import discord
import requests
import logging
from utils import save_auth_codes # Assuming utils.py contains save_auth_codes

# Configure logging if not already done in your main application
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

async def logout_command(interaction: discord.Interaction, auth_codes):
    user_id = str(interaction.user.id)

    if user_id not in auth_codes:
        embed = discord.Embed(
            title="❌ Not Logged In",
            description="You're not currently logged in. Use **/login**.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    access_token = auth_codes[user_id].get("access_token")

    if access_token:
        kill_url = f"https://account-public-service-prod.ol.epicgames.com/account/api/oauth/sessions/kill/{access_token}"
        kill_headers = {
            "Authorization": f"Bearer {access_token}"
        }

        try:
            # Attempt to kill the access token on Epic Games' servers
            response = requests.delete(kill_url, headers=kill_headers)
            response.raise_for_status() # Raise an HTTPError for bad responses (4xx or 5xx)

            if response.status_code == 204: # 204 No Content is a typical success for DELETE
                logging.info(f"Successfully killed Epic Games token for user {user_id}.")
            else:
                logging.warning(f"Unexpected response status {response.status_code} when killing token for user {user_id}: {response.text}")
                # Even if the token kill fails, proceed with local logout
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to kill Epic Games token for user {user_id}: {e}")
            # Proceed with local logout even if the API call fails
    else:
        logging.warning(f"No access token found for user {user_id} during logout. Proceeding with local logout.")

    # Always proceed with local logout to remove the user's data from bot storage
    del auth_codes[user_id]
    save_auth_codes(auth_codes)

    embed = discord.Embed(
        title="✅ Logged Out",
        description="You have been successfully logged out. Your Epic Games session has also been terminated. Use **/login** to link again.",
        color=discord.Color.green()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)