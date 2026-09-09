import discord
import aiohttp

async def add_epic_friend_command(interaction: discord.Interaction, auth_codes, friend_username: str):
    user_id = str(interaction.user.id)

    if user_id not in auth_codes:
        embed = discord.Embed(
            title="❌ Not Logged In",
            description="You need to log in first. Use **/login**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    access_token = auth_codes[user_id]["access_token"]
    account_id = auth_codes[user_id]["account_id"]

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Step 1: Get target account ID from display name
    async with aiohttp.ClientSession() as session:
        async with session.get(f"https://account-public-service-prod.ol.epicgames.com/account/api/public/account/displayName/{friend_username}", headers=headers) as name_response:
            if name_response.status != 200:
                error = await name_response.text()
                embed = discord.Embed(
                    title="❌ User Not Found",
                    description=f"Could not find Epic Games user **{friend_username}**.\n```{error}```",
                    color=discord.Color.red()
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            name_data = await name_response.json()
            friend_account_id = name_data["id"]

    # Step 2: Send friend request
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"https://friends-public-service-prod.ol.epicgames.com/friends/api/public/friends/{account_id}/{friend_account_id}",
            headers=headers
        ) as friend_response:
            if friend_response.status == 204:
                embed = discord.Embed(
                    title="✅ Friend Request Sent",
                    description=f"A friend request was sent to **{friend_username}**.",
                    color=discord.Color.green()
                )
            elif friend_response.status == 409:
                embed = discord.Embed(
                    title="ℹ️ Already Friends or Pending",
                    description=f"You're already friends or have a pending request with **{friend_username}**.",
                    color=discord.Color.orange()
                )
            else:
                error = await friend_response.text()
                embed = discord.Embed(
                    title="❌ Failed to Send Friend Request",
                    description=f"Status: {friend_response.status}\nDetails: ```{error}```",
                    color=discord.Color.red()
                )

    await interaction.followup.send(embed=embed, ephemeral=False)
