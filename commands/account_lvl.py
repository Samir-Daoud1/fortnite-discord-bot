import discord
import aiohttp


async def account_level_command(interaction: discord.Interaction, auth_codes: dict):
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
    display_name = auth_codes[user_id]["display_name"]

    url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=athena&rvn=-1"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json={"profileId": "athena", "rvn": -1}) as response:
            if response.status != 200:
                error = await response.text()
                embed = discord.Embed(
                    title="❌ Failed to Fetch Account Level",
                    description=f"Status: {response.status}\nDetails: ```{error}```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            data = await response.json()

    try:
        attributes = data["profileChanges"][0]["profile"]["stats"]["attributes"]
        account_level = attributes.get("accountLevel", "N/A")
        season_level = attributes.get("seasonLevel", "N/A")
        battle_pass = attributes.get("book_level", "N/A")
    except Exception:
        embed = discord.Embed(
            title="❌ Error",
            description="Could not parse BR account data.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title=f"🏆 Battle Royale Account Level - {display_name}",
        color=discord.Color.dark_purple()
    )
    embed.add_field(name="🔢 Account Level", value=str(account_level), inline=True)
    embed.add_field(name="🎮 Season Level", value=str(season_level), inline=True)
    embed.add_field(name="📘 Battle Pass Level", value=str(battle_pass), inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=False)
