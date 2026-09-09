import discord
import aiohttp

async def fortnite_item_shop_command(interaction: discord.Interaction, auth_codes=None):
    # No auth needed for item shop, but you can keep auth_codes param for consistency

    url = "https://fortnite-public-service-prod11.ol.epicgames.com/fortnite/api/storefront/v2/catalog"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                error = await response.text()
                embed = discord.Embed(
                    title="❌ Failed to Fetch Item Shop",
                    description=f"Status: {response.status}\nDetails: ```{error}```",
                    color=discord.Color.red()
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            data = await response.json()

    # Extract daily featured items from the catalog
    try:
        daily_entries = data["storefront"]["catalogEntries"]
        daily_items = [entry for entry in daily_entries if entry["offerId"].startswith("daily")]
    except Exception:
        embed = discord.Embed(
            title="❌ Error",
            description="Could not parse Item Shop data.",
            color=discord.Color.red()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    if not daily_items:
        embed = discord.Embed(
            title="❌ No Items Found",
            description="Item Shop appears empty or data is unavailable.",
            color=discord.Color.orange()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    embed = discord.Embed(
        title="🛒 Fortnite Item Shop - Daily Featured Items",
        color=discord.Color.gold()
    )

    # Limit number of items shown (Discord embed limits, or you can paginate)
    max_items_to_show = 10
    for i, item in enumerate(daily_items[:max_items_to_show], start=1):
        offer_id = item["offerId"]
        try:
            # Item name and price
            item_name = item["devName"]
            price = item["prices"][0]["finalPrice"]
            currency = item["prices"][0]["currencyType"]

            # Try to get image URL
            images = item.get("displayAssets", [])
            image_url = images[0]["url"] if images else None

            description = f"**Price:** {price} {currency}"

            embed.add_field(name=f"{i}. {item_name}", value=description, inline=False)

            if image_url:
                embed.set_thumbnail(url=image_url)

        except Exception:
            continue

    await interaction.response.send_message(embed=embed, ephemeral=False)
