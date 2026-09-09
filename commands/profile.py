import discord
import aiohttp

async def fortnite_profile_command(interaction: discord.Interaction, auth_codes):
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

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # This endpoint and parsing is for demonstration; adjust as needed for your API/data
    url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=athena&rvn=-1"

    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json={"profileId": "athena", "rvn": -1}) as response:
            if response.status != 200:
                error = await response.text()
                embed = discord.Embed(
                    title="❌ Failed to Fetch Profile",
                    description=f"Status: {response.status}\nDetails: ```{error}```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return
            data = await response.json()

    try:
        stats = data["profileChanges"][0]["profile"]["stats"]["attributes"]
        level = stats.get("level", "Unknown")
        battle_pass = stats.get("book_level", "Unknown")
        wins = stats.get("wins", "Unknown")
        matches = stats.get("matches_played", "Unknown")
    except Exception:
        embed = discord.Embed(
            title="❌ Error",
            description="Could not parse Fortnite profile data.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title=f"Fortnite Profile: {display_name}",
        color=discord.Color.blue()
    )
    embed.add_field(name="Level", value=level, inline=True)
    embed.add_field(name="Battle Pass Level", value=battle_pass, inline=True)
    embed.add_field(name="Wins", value=wins, inline=True)
    embed.add_field(name="Matches Played", value=matches, inline=True)

    await interaction.response.send_message(embed=embed, ephemeral=False)