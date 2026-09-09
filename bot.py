import os
import discord
import logging
from discord import app_commands
from discord.ext import tasks, commands
from dotenv import load_dotenv
from login_system.code_auth import (
    load_auth_data,
    check_and_refresh_tokens
)

from login_system.login import login_command
from login_system.logout import logout_command

from commands.account_lvl import account_level_command
from commands.account_info import account_info_command
from commands.profile import fortnite_profile_command
from commands.locker import generate_fortnite_locker
from commands.add_friend import add_epic_friend_command 
from commands.remove_friend import execute_remove_friend_command

# from commands.stw_inventory import generate_full_stw_database
from commands.stw_profile import stw_profile_command
from commands.profile_unlock import profile_unlock
from commands.shutdown import shutdown_command
from commands.restart import restart_command



load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')

PREMIUM_ROLE_ID = 1378067779323695144
intents = discord.Intents.default()
intents.messages = True
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

auth_codes = load_auth_data()

async def check_premium_access(interaction: discord.Interaction):

  if not interaction.user or not isinstance(interaction.user, discord.Member):

    await interaction.response.send_message(
        "I couldn't verify your roles. This feature might require being in a server.",
        ephemeral=True
    )
    return False


  user_role_ids = [role.id for role in interaction.user.roles]


  if PREMIUM_ROLE_ID in user_role_ids:
    return True
  else:
    await interaction.response.send_message("This feature is for premium users only.", ephemeral=True)
    return False


@tasks.loop(minutes=5)
async def auto_refresh_tokens():

    global auth_codes 

    logging.info("Starting auto_refresh_tokens cycle.")

    await check_and_refresh_tokens(auth_codes) 
    try:
        new_auth_codes = load_auth_data() 
        
        if auth_codes != new_auth_codes: 
            logging.info("In-memory auth codes differ from file, updating in-memory copy.")
        else:
            logging.info("In-memory auth codes already consistent with file content.")

        auth_codes.clear() 
        auth_codes.update(new_auth_codes) 

    except Exception as e:
        logging.error(f"Error during post-refresh auth code reload: {e}")
        # Depending on severity, you might want to stop the task or alert here.


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user} (ID: {bot.user.id})')
    global auth_codes
    auth_codes = load_auth_data() 
    auto_refresh_tokens.start()
    try:

        await bot.tree.sync()
        print("Successfully synchronized application commands.")
    except Exception as e:
        print(f"Failed to sync application commands: {e}")
def coming_soon_embed():
    embed = discord.Embed(
        title="🚧 Coming Soon!",
        description="This feature is currently under development. Stay tuned!",
        color=discord.Color.orange()
    )
    embed.set_footer(text="Thank you for your patience!")
    return embed

#LOGIN SYSTEM
# Slash command: login
@bot.tree.command(name="login", description="Login to your Epic Games account.")
@app_commands.describe(method="Choose the login method: Auth Code or Device Auth")
@app_commands.choices(method=[
    app_commands.Choice(name="Auth Code", value="auth_code"),
    # app_commands.Choice(name="Device Auth", value="device_auth"),
])
async def login(interaction: discord.Interaction, method: app_commands.Choice[str]):
    await interaction.response.defer(ephemeral=False) 
    try: 
        await login_command(interaction, method.value) 
    except Exception as e:
        logging.exception(f"Error in /login command execution for user {interaction.user.id}.") 

        await interaction.followup.send(f"❌ An unexpected error occurred during login: {str(e)}", ephemeral=True)

# Slash command: logout
@bot.tree.command(name="logout", description="Log out of your Epic Games account.")
async def logout(interaction: discord.Interaction):
    global auth_codes
    auth_codes = load_auth_data()
    await logout_command(interaction, auth_codes)
    auth_codes = load_auth_data()  


#BR COMMANDS
# Slash command: profile
@bot.tree.command(name="profile", description="View your Epic Games profile.")
async def profile(interaction: discord.Interaction):
    global auth_codes
    auth_codes = load_auth_data() 
    await fortnite_profile_command(interaction, auth_codes)
    auth_codes = load_auth_data()  

# Slash command: accountinfo
@bot.tree.command(name="account-info", description="Show your Epic Games account info.")
async def accountinfo(interaction: discord.Interaction):
    auth_codes = load_auth_data()
    await account_info_command(interaction, auth_codes)
    
# Slash command: accountlevel
@bot.tree.command(name="account-level", description="Show your Epic Games account level.")
async def accountlevel(interaction: discord.Interaction):
    auth_codes = load_auth_data()
    await account_level_command(interaction, auth_codes)

# Slash command: addfriend
@bot.tree.command(name="add-friend", description="Send a friend request to an Epic Games user.")
@app_commands.describe(friend_username="The Epic Games username you want to send a friend request to.")
async def add_friend(interaction: discord.Interaction, friend_username: str):
    if await check_premium_access(interaction):
        global auth_codes
        auth_codes = load_auth_data()
        await interaction.response.defer(ephemeral=True)
        try:
            await add_epic_friend_command(interaction, auth_codes, friend_username)
        except Exception as e:
            await interaction.followup.send(f"❌ Friend request failed: {str(e)}", ephemeral=True)

# Slash command: removefriend
@bot.tree.command(name="remove-friend", description="Remove a friend from your Epic Games friends list.")
@app_commands.describe(friend_name="The exact Epic Games display name of the friend to remove.")
async def remove_friend(interaction: discord.Interaction, friend_name: str):
    if await check_premium_access(interaction):
        await execute_remove_friend_command(interaction, friend_name)

# Slash command: locker
@bot.tree.command(name="locker", description="Show your Fortnite locker.")
async def locker(interaction: discord.Interaction):
    if await check_premium_access(interaction):

        global auth_codes
        auth_codes = load_auth_data() 
        
        user_id = str(interaction.user.id) 
        user_auth_data = auth_codes.get(user_id) 

        if not isinstance(user_auth_data, dict):
            logging.warning(f"DEBUG (Locker Command): user_auth_data for Discord ID {user_id} is not a dictionary or is None. Type: {type(user_auth_data)}")



        if not user_auth_data or not user_auth_data.get("access_token") or not user_auth_data.get("account_id"):
            embed = discord.Embed(
                title="Authentication Required ⚠️",
                description="You need to be logged in to your Epic Games account first. Please use `/login`.",
                color=discord.Color.red()
            )

            await interaction.response.send_message(embed=embed, ephemeral=True)
            return 

        await generate_fortnite_locker(interaction, user_auth_data)
    
# Slash command: itemshop
@bot.tree.command(name="itemshop", description="Show your Fortnite item shop.")
async def itemshop(interaction: discord.Interaction):
    # await fortnite_item_shop_command(interaction)
    embed = coming_soon_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

#Slash command: ghost-equip
@bot.tree.command(name="ghost-equip", description="Equip a cosmetic item for others to see in your lobby")
@app_commands.describe(
    category="The type of cosmetic item (e.g., outfit, pickaxe, emote)",
    item_name="The name of the cosmetic item you want to equip"
)
@app_commands.choices(
    category=[
        app_commands.Choice(name="Outfit", value="outfit"),
        app_commands.Choice(name="Backbling", value="backbling"),
        app_commands.Choice(name="Pickaxe", value="pickaxe"),
        app_commands.Choice(name="Emote", value="emote")
    ]
)
async def ghostequip(interaction: discord.Interaction, category: str, item_name: str):
    # if await check_premium_access(interaction): 
        embed = coming_soon_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)
        # logging.info(f"Received /equip command from {interaction.user.name}: Category='{category}', Item='{item_name}'")
        # global auth_codes
        # auth_codes = load_auth_data()  # Reload after in case of changes
        # await equip_command(interaction, auth_codes, category, item_name)
        # auth_codes = load_auth_data()  # Reload after in case of changes


#STW COMMANDS
# Slash command: stwprofile
@bot.tree.command(name="stw-profile", description="Show your Save the World profile.")
async def stwprofile(interaction: discord.Interaction):
    auth_codes = load_auth_data()
    await stw_profile_command(interaction, auth_codes)


# Slash command: stw-inventory
@bot.tree.command(name="stw-inventory", description="View your Fortnite Save the World inventory.")
async def stw_inventory(interaction: discord.Interaction):
    # if await check_premium_access(interaction):
    #     await generate_full_stw_database(interaction)
    embed = coming_soon_embed()
    await interaction.response.send_message(embed=embed, ephemeral=True)

#BOT COMMANDS
# Slash command: shutdown
@bot.tree.command(name="shutdown", description="Shut down the bot (owner only).")
async def shutdown(interaction: discord.Interaction):
    await shutdown_command(interaction, bot)

# Slash command: restart
@bot.tree.command(name="restart", description="Restart the bot (owner only).")
async def restart(interaction: discord.Interaction):
    await restart_command(interaction, bot)


@bot.tree.command(name="profile-unlock", description="Check your Save the World profile lock status")
async def lockstatus(interaction: discord.Interaction):
    await profile_unlock(interaction)


# Run bot
if __name__ == "__main__":
    # keep_alive()
    bot.run(TOKEN)