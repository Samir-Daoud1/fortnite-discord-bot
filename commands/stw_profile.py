import discord
import aiohttp
import json

async def stw_profile_command(interaction: discord.Interaction, auth_codes: dict):
    user_id = str(interaction.user.id)

    await interaction.response.defer(ephemeral=False)

    if user_id not in auth_codes:
        embed = discord.Embed(
            title="❌ Not Logged In",
            description="You need to log in first. Use **/login**.",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(embed=embed)
        return

    access_token = auth_codes[user_id]["access_token"]
    account_id = auth_codes[user_id]["account_id"]
    display_name = auth_codes[user_id]["display_name"]

    url = f"https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/game/v2/profile/{account_id}/client/QueryProfile?profileId=campaign&rvn=-1"

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json={"profileId": "campaign", "rvn": -1}) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    stats = data.get("profileChanges", [{}])[0].get("profile", {}).get("stats", {}).get("attributes", {})
                    items = data.get("profileChanges", [{}])[0].get("profile", {}).get("items", {})

                    commander_level = stats.get("level")
                    commander_xp = stats.get("xp")
                    schematic_xp = stats.get("schematic_xp")
                    survivor_xp = stats.get("survivor_xp")
                    hero_xp = stats.get("hero_xp")
                    
                    def format_numeric_value(value):
                        if isinstance(value, (int, float)):
                            return f"{value:,}"
                        return "N/A"

                    commander_level_formatted = format_numeric_value(commander_level)
                    commander_xp_formatted = format_numeric_value(commander_xp)
                    schematic_xp_formatted = format_numeric_value(schematic_xp)
                    survivor_xp_formatted = format_numeric_value(survivor_xp)
                    hero_xp_formatted = format_numeric_value(hero_xp)

                    mission_alert_rewards_count = len(stats.get("mission_alert_redemption_record", {}).get("redemption_records", {}))

                    total_schematics = sum(1 for item_data in items.values() if item_data.get('templateId', '').startswith('Weapon:'))
                    total_heroes = sum(1 for item_data in items.values() if item_data.get('templateId', '').startswith('Hero:'))
                    total_survivors = sum(1 for item_data in items.values() if item_data.get('templateId', '').startswith('Worker:'))
                    total_defenders = sum(1 for item_data in items.values() if item_data.get('templateId', '').startswith('Defender:'))

                    if commander_level == 1 and (total_heroes <= 1 and total_schematics == 0 and total_survivors == 0 and total_defenders == 0):
                        embed = discord.Embed(
                            title="❌ Save the World Profile Not Found",
                            description=(
                                "It appears your Epic Games account either **does not own Save the World**, "
                                "or you **have not completed the Save the World tutorial** yet.\n\n"
                                "Please ensure you own Save the World and have progressed past the initial tutorial "
                                "for your profile to be accessible."
                            ),
                            color=discord.Color.orange()
                        )
                        await interaction.edit_original_response(embed=embed)
                        return


                    embed = discord.Embed(
                        title=f"🧭 STW Profile - {display_name}",
                        description=f"Detailed overview of your Save the World profile:",
                        color=discord.Color.blue()
                    )
                    embed.add_field(name="🎖️ Commander Level", value=commander_level_formatted, inline=True)
                    embed.add_field(name="⭐ Commander XP", value=commander_xp_formatted, inline=True)
                    embed.add_field(name="\u200b", value="\u200b", inline=True)
                    
                    embed.add_field(name="🛠️ Schematic XP", value=schematic_xp_formatted, inline=True)
                    embed.add_field(name="👷 Survivor XP", value=survivor_xp_formatted, inline=True)
                    embed.add_field(name="🦸 Hero XP", value=hero_xp_formatted, inline=True)

                    embed.add_field(name="📦 Mission Alert Redemptions", value=str(mission_alert_rewards_count), inline=True)
                    embed.add_field(name="Blueprint Schematics", value=str(total_schematics), inline=True)
                    embed.add_field(name="Heroes Owned", value=str(total_heroes), inline=True)
                    embed.add_field(name="Survivors Owned", value=str(total_survivors), inline=True)
                    embed.add_field(name="Defenders Owned", value=str(total_defenders), inline=True)

                    embed.set_footer(text="Data from Epic Games API | Levels may not reflect actual power level")
                    await interaction.edit_original_response(embed=embed)

                else:
                    error_data = await response.json()
                    error_code = error_data.get("errorCode")
                    error_message = error_data.get("errorMessage", "No specific error message provided.")

                    if error_code == "errors.com.epicgames.fortnite.profile_not_found" or \
                       error_code == "errors.com.epicgames.fortnite.not_ready":
                        
                        embed = discord.Embed(
                            title="❌ Save the World Not Found/Ready",
                            description=(
                                "It appears your Epic Games account either **does not own Save the World**, "
                                "or you **have not completed the Save the World tutorial** yet.\n\n"
                                "Please ensure you own Save the World and have progressed past the initial tutorial "
                                "for your profile to be accessible."
                            ),
                            color=discord.Color.orange()
                        )
                        embed.set_footer(text=f"Error Code: {error_code}")
                        await interaction.edit_original_response(embed=embed)
                    else:
                        embed = discord.Embed(
                            title="❌ Failed to Fetch STW Profile",
                            description=f"An unexpected error occurred while fetching your STW profile.\n"
                                        f"**Status Code:** `{response.status}`\n"
                                        f"**Error Code:** `{error_code}`\n"
                                        f"**Details:** `{error_message}`",
                            color=discord.Color.red()
                        )
                        await interaction.edit_original_response(embed=embed)

    except aiohttp.ClientError as e:
        embed = discord.Embed(
            title="❌ Network Error",
            description=f"Could not connect to Epic Games servers. Please try again later.\nDetails: `{e}`",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(embed=embed)
    except json.JSONDecodeError:
        embed = discord.Embed(
            title="❌ API Response Error",
            description="Received an unreadable response from the Epic Games API. The service might be temporarily unavailable.",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(embed=embed)
    except Exception as e:
        embed = discord.Embed(
            title="❌ An Unexpected Error Occurred",
            description=f"Something went wrong while processing your STW profile. Please report this to the bot developer.\nDetails: `{e}`",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(embed=embed)