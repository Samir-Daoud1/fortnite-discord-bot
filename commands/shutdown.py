import os
import discord
import logging


async def shutdown_command(interaction: discord.Interaction, bot: discord.Client):
    owner_id = os.getenv("BOT_OWNER_ID")
    if str(interaction.user.id) != str(owner_id):
        embed = discord.Embed(
            title="❌ Access Denied",
            description="Only the bot owner can use this command.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title="🛑 Shutting Down",
        description="Bot is shutting down. Bye!",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

    await bot.close()
    logging.info("Bot is shutting down.")
    import sys
    sys.exit(0)