import discord
import aiohttp


async def account_info_command(interaction: discord.Interaction, auth_codes: dict):
    user_id = str(interaction.user.id)

    if user_id not in auth_codes:
        embed = discord.Embed(
            title="❌ Not Logged In",
            description="You need to log in first. Use **/login**.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    access_token = auth_codes[user_id]["access_token"]
    account_id = auth_codes[user_id]["account_id"]

    url = f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/{account_id}"

    headers = {
        "Authorization": f"Bearer {access_token}"
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as response:
            if response.status != 200:
                error = await response.text()
                embed = discord.Embed(
                    title="❌ Failed to Fetch Account Info",
                    description=f"Status: {response.status}\nDetails: ```{error}```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            data = await response.json()

    # Safely extract non-sensitive info
    display_name = data.get("displayName", "Unknown")
    id_ = data.get("id", "Unknown")
    name = data.get("name", "Unknown")
    last_display_name_change = data.get("lastDisplayNameChange", "Unknown")
    number_display_name_changes = data.get("numberOfDisplayNameChanges", "Unknown")
    country = data.get("country", "Unknown")
    preferred_language = data.get("preferredLanguage", "Unknown")
    creation_date = data.get("created", "Unknown")

    embed = discord.Embed(
        title=f"🧾 Epic Games Account Info - {display_name}",
        color=discord.Color.blue()
    )
    # embed.add_field(name="🆔 Account ID", value=id_, inline=False)
    embed.add_field(name="👤 Name (Internal)", value=name, inline=True)
    embed.add_field(name="📅 Created On", value=creation_date, inline=True)
    embed.add_field(name="🌍 Country", value=country, inline=True)
    embed.add_field(name="🗣 Preferred Language", value=preferred_language, inline=True)
    embed.add_field(name="🔁 Last Display Name Change", value=last_display_name_change, inline=False)
    embed.add_field(name="🔄 Display Name Changes Left", value=str(number_display_name_changes), inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=False)
