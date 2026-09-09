import os
import sys
import json
import zlib
import base64
import aiohttp
import asyncio
import platform
import coloredlogs
import discord


__version__ = "2.3"

coloredlogs.logging.basicConfig(level=coloredlogs.logging.ERROR)
log = coloredlogs.logging.getLogger(__name__)
coloredlogs.install(fmt="[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S", logger=log, level=coloredlogs.logging.ERROR)


class AuthError(Exception):
    pass

class EpicAccount:

    def __init__(self, data: dict = {}) -> None:
        self.raw = data
        self.access_token = data.get("access_token", "")
        self.display_name = data.get("displayName", "")
        self.account_id = data.get("account_id", "")
    
    async def get_profile(self, profile: str):
        async with aiohttp.ClientSession() as session:
            headers = {
                "Authorization": f"bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            url = ("https://fngw-mcp-gc-livefn.ol.epicgames.com"
                   f"/fortnite/api/game/v2/profile/{self.account_id}/client/QueryProfile?profileId={profile}&rvn=-1")
            
            async with session.request(
                method="POST",
                url=url,
                headers=headers,
                data=json.dumps({})
            ) as request:
                if request.status == 200:
                    return await request.json()
                elif request.status == 401:
                    data = await request.json()
                    error_message = (f"Authentication required or token expired: {data.get('errorCode', 'N/A')}")
                    log.error(error_message)
                    raise AuthError(error_message)
                else:
                    data = await request.json()
                    error_message = (f"Failed to get profile '{profile}'. Status: {request.status}, "
                                     f"Error Code: {data.get('numericErrorCode', 'N/A')}, "
                                     f"Message: {data.get('errorCode', 'N/A')}")
                    log.error(error_message)
                    raise Exception(error_message)


class Generator:
    def __init__(self, auth_data: dict) -> None:
        if not isinstance(auth_data, dict) or not auth_data.get("access_token") or not auth_data.get("account_id"):
            raise AuthError("Invalid or incomplete authentication data provided to Locker Generator. Please ensure you are logged in.")

        self.http: aiohttp.ClientSession = None
        self.auth_data = auth_data
        self.user_agent = f"LockerGenerator/v{__version__} {platform.system()}/{platform.version()}"
        
    async def start(self, interaction: discord.Interaction) -> str:
        self.http = aiohttp.ClientSession(headers={"User-Agent": self.user_agent})
        account: EpicAccount = None

        try:
            user_access_token = self.auth_data["access_token"]
            user_account_id = self.auth_data["account_id"]
            user_display_name = self.auth_data.get("display_name", "Unknown Player")

            account = EpicAccount({
                "access_token": user_access_token,
                "account_id": user_account_id,
                "displayName": user_display_name
            })
            
            validation_embed = discord.Embed(
                title="Validation In Progress",
                description="Validating your Epic Games authentication...",
                color=discord.Color.blue()
            )
            await interaction.edit_original_response(content="", embed=validation_embed)
            
            await account.get_profile(profile="common_core")
            log.info(f"Successfully authenticated as: {user_display_name} ({user_account_id}).")
            
            authenticated_embed = discord.Embed(
                title="Authentication Successful",
                description=f"Authenticated as **{user_display_name}**. Processing your locker items...",
                color=discord.Color.blue()
            )
            await interaction.edit_original_response(content="", embed=authenticated_embed)

            athena_profile_data = await account.get_profile(profile="athena")
            account_items = athena_profile_data["profileChanges"][0]["profile"]["items"]
            athena_creation_date = athena_profile_data["profileChanges"][0]["profile"]["created"]

            common_core_profile_data = await account.get_profile(profile="common_core")
            banner_items = common_core_profile_data["profileChanges"][0]["profile"]["items"]

            banners = []
            for item_id in banner_items:
                if "HomebaseBannerIcon" in banner_items[item_id]["templateId"]:
                    banners.append(banner_items[item_id]["templateId"].split(":")[1])

            all_items = list(map(lambda item_key: account_items[item_key]["templateId"].split(":")[1], account_items))
            all_items.extend(banners)
            
            locker_items_for_fngg = []
            fngg_items_map = await self._get_fngg_items()
            fngg_item_ids_lowercase = {key.lower(): key for key in fngg_items_map.keys()}

            for item_name in all_items:
                if item_name.lower() in fngg_item_ids_lowercase:
                    original_id = fngg_item_ids_lowercase[item_name.lower()]
                    locker_items_for_fngg.append(original_id)
                else:
                    log.warning(f"Item '{item_name}' not found in Fortnite.gg items map. Skipping.")
            
            cosmetics_api_response = await self._get_cosmetics_api()
            cosmetics_with_built_in_emotes = {}
            if cosmetics_api_response["status"] == 200:
                for cosmetic in cosmetics_api_response["data"]:
                    if "builtInEmoteIds" in cosmetic:
                        cosmetics_with_built_in_emotes[cosmetic["id"]] = cosmetic["builtInEmoteIds"]

            for cosmetic_id in locker_items_for_fngg:
                if cosmetic_id in cosmetics_with_built_in_emotes:
                    locker_items_for_fngg.extend(cosmetics_with_built_in_emotes[cosmetic_id])

            fngg_bundles_map = await self._get_fngg_bundles()
            owned_bundles = []
            for bundle_name, bundle_info in fngg_bundles_map.items():
                if all(item_in_bundle in locker_items_for_fngg for item_in_bundle in bundle_info["items"]):
                    owned_bundles.append(bundle_name)
            
            locker_items_for_fngg.extend(owned_bundles)

            valid_ints = []
            for item_id in locker_items_for_fngg:
                if item_id in fngg_items_map:
                    valid_ints.append(int(fngg_items_map[item_id]))
                else:
                    log.warning(f"Item '{item_id}' not found in Fortnite.gg items map. Skipping.")

            valid_ints.sort()

            diff = [str(valid_ints[0])] if valid_ints else []
            for i in range(1, len(valid_ints)):
                diff.append(str(valid_ints[i] - valid_ints[i-1]))
            
            compressor = zlib.compressobj(
                level=-1,
                method=zlib.DEFLATED,
                wbits=-9,
                memLevel=zlib.DEF_MEM_LEVEL,
                strategy=zlib.Z_DEFAULT_STRATEGY
            )
            data_to_compress = f"{athena_creation_date},{','.join(diff)}".encode('utf-8')
            compressed_data = compressor.compress(data_to_compress)
            compressed_data += compressor.flush()

            encoded_data = base64.urlsafe_b64encode(compressed_data).decode('utf-8').rstrip("=")
            
            url = f"https://fortnite.gg/my-locker?items={encoded_data}"
            
            log.info("Locker link generated successfully.")
            return url

        except AuthError as e:
            raise e
        except aiohttp.ClientError as e:
            log.error(f"Network error during locker generation: {e}")
            raise Exception(f"A network error occurred: {e}")
        except json.JSONDecodeError as e:
            log.error(f"Error decoding JSON response: {e}")
            raise Exception(f"Failed to process API response: {e}")
        except Exception as e:
            log.error(f"An unexpected error occurred during locker generation: {e}")
            raise Exception(f"An unexpected error occurred: {e}")
        finally:
            if self.http:
                await self.http.close()

    async def _get_fngg_items(self) -> dict:
        async with self.http.request(
            method="GET",
            url="https://fortnite.gg/api/items.json",
        ) as request:
            request.raise_for_status()
            return await request.json()
    
    async def _get_fngg_bundles(self) -> dict:
        async with self.http.request(
            method="GET",
            url="https://fortnite.gg/api/bundles.json",
        ) as request:
            request.raise_for_status()
            return await request.json()
    
    async def _get_cosmetics_api(self) -> dict:
        async with self.http.request(
            method="GET",
            url="https://fortnite-api.com/v2/cosmetics/br",
        ) as request:
            request.raise_for_status()
            return await request.json()
    

async def generate_fortnite_locker(interaction: discord.Interaction, auth_data: dict) -> None:

    await interaction.response.defer(ephemeral=False)

    try:
        generator = Generator(auth_data=auth_data)
        locker_url = await generator.start(interaction)
        
        embed = discord.Embed(
            title="Fortnite Locker Generated!",
            description=f"Here is your Fortnite.gg [locker link](<{locker_url}>)",
            color=discord.Color.green()
        )
        embed.set_footer(text="Click the link to view your locker!")
        await interaction.edit_original_response(content="", embed=embed)

    except AuthError as e:
        log.error(f"Authentication error in generate_fortnite_locker: {e}")
        error_embed = discord.Embed(
            title="Authentication Required ❌",
            description=f"Your Epic Games authentication is missing or invalid: {e}\n"
                        "Please ensure you are logged in using `/login`.",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(content="", embed=error_embed)
    except Exception as e:
        log.error(f"An unexpected error occurred during locker generation: {e}")
        error_embed = discord.Embed(
            title="Locker Generation Failed ❌",
            description=f"An unexpected error occurred: {e}\n"
                        "Please try again later. If the issue persists, contact support.",
            color=discord.Color.red()
        )
        await interaction.edit_original_response(content="", embed=error_embed)

