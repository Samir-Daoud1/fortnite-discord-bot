import os
import discord
import logging
from utils import load_auth_codes, save_auth_codes
from login_system.code_auth import (
    save_tokens_and_auth_code,
    load_auth_data,
)
# Import the new functions from device_auth.py
import login_system.device_auth as device_auth

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Auth Code UI Classes (Original Logic - unchanged) ---

class AuthCodeModal(discord.ui.Modal, title="Enter Epic Auth Code"):
    def __init__(self, user_id: str, channel: discord.TextChannel):
        super().__init__()
        self.user_id = user_id
        self.channel = channel

        self.auth_code = discord.ui.TextInput(
            label="Auth Code",
            placeholder="Paste your Epic Games auth code here...",
            required=True,
            max_length=32
        )
        self.add_item(self.auth_code)

    async def on_submit(self, interaction: discord.Interaction):
        code = self.auth_code.value.strip()

        if len(code) != 32 or not code.isalnum():
            await interaction.response.send_message(
                "❌ Invalid code. It must be exactly 32 alphanumeric characters.",
                ephemeral=True
            )
            return

        await interaction.response.send_message("✅ Auth code received. Logging you in...", ephemeral=True)

        try:
            save_tokens_and_auth_code(self.user_id, code) 
            
            global auth_codes
            auth_codes = load_auth_data() 

            display_name = auth_codes.get(self.user_id, {}).get("display_name", "Unknown")

            embed = discord.Embed(
                title="✅ Login Successful (Auth Code)",
                description=f"You are now logged in as **{display_name}**!",
                color=discord.Color.green()
            )
            await self.channel.send(embed=embed)

        except Exception as e:
            logging.exception("Auth code login failed.")
            embed = discord.Embed(
                title="❌ Login Failed (Auth Code)",
                description=f"An error occurred while logging in: {str(e)}",
                color=discord.Color.red()
            )
            await self.channel.send(embed=embed)

class AuthButton(discord.ui.View):
    def __init__(self, user_id: str, channel: discord.TextChannel):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.channel = channel

    @discord.ui.button(label="Enter Auth Code", style=discord.ButtonStyle.primary)
    async def auth_button_callback(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != int(self.user_id):
            await interaction.response.send_message("❌ This button isn't for you.", ephemeral=True)
            return

        modal = AuthCodeModal(self.user_id, self.channel)
        await interaction.response.send_modal(modal)



# The actual login logic as a function to be called from bot.py
async def login_command(interaction: discord.Interaction, method: str): 
    user_id = str(interaction.user.id)
    

    user_auth_data = load_auth_codes().get(user_id, {})
    

    if "auth_code" in user_auth_data and user_auth_data["auth_code"] and \
       "account_id" in user_auth_data and user_auth_data["account_id"]:  
            embed = discord.Embed(
            title="❌ You are already logged in.",
            description=f"Ues /logout to logout of your current account.",
            color=discord.Color.red()
            )
            self = interaction
            await self.followup.send(embed=embed)
    else:
        if method == "auth_code":
            embed = discord.Embed(
                title="🔐 Epic Games Login - Auth Code Method",
                description="Follow the steps below to link your Epic Games account using an authorization code.",
                color=discord.Color.blurple()
            )
            embed.add_field(
                name="Step 1",
                value="Log into Epic Games using [this link](https://www.epicgames.com) in your browser.", inline=False
            )
            embed.add_field(
                name="Step 2",
                value="Click [this link](https://www.epicgames.com/id/api/redirect?clientId=3f69e56c7649492c8cc29f1af08a8a12&responseType=code) to get your authorization code. Copy the **32-character code** that appears after `?code=` in the URL.",
                inline=False
            )
            embed.add_field(
                name="Step 3",
                value="Click the 'Enter Auth Code' button below and paste the code you copied.",
                inline=False
            )

            view = AuthButton(user_id, interaction.channel)
            await interaction.followup.send(embed=embed, view=view, ephemeral=False)

        elif method == "device_auth":
            
            embed = discord.Embed(
                title="ℹ️ Login Method Not Supported",
                description="The selected login method is not recognized. Please choose 'auth_code' or 'device_auth'.",
                color=discord.Color.yellow()
            )
            await interaction.followup.send(embed=embed, ephemeral=True)