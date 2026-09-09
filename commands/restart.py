import os
import discord
import logging

async def restart_command(interaction: discord.Interaction, bot):
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
        title="🔄 Restarting",
        description="Bot is restarting. Please wait...",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)
    logging.info("Bot is restarting...")
    import sys
    await bot.close()   
    os.execl(sys.executable, sys.executable, *sys.argv)