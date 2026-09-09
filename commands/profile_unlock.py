import requests
import asyncio
import json
import utils
import discord
import coloredlogs
from datetime import datetime, timezone

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


coloredlogs.logging.basicConfig(level=coloredlogs.logging.ERROR)
log = coloredlogs.logging.getLogger(__name__)

coloredlogs.install(fmt="[%(asctime)s][%(levelname)s] %(message)s", datefmt="%H:%M:%S", logger=log, level=coloredlogs.logging.ERROR)


FORTNITE_GAME_API_HOST = "https://fngw-mcp-gc-livefn.ol.epicgames.com"

COMMON_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
}


# ── Epic Games API (unchanged) ────────────────────────────────────────────────

def _query_profile_sync(access_token: str, account_id: str, profile_id: str) -> dict | None:
    url = (
        f"{FORTNITE_GAME_API_HOST}/fortnite/api/game/v2/profile/{account_id}"
        f"/client/QueryProfile?profileId={profile_id}&rvn=-1"
    )
    headers = {**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"}
    try:
        log.debug(f"Calling QueryProfile for account {account_id}, profile={profile_id}")
        response = requests.post(url, headers=headers, json={})
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        log.error(f"HTTP error querying profile for account {account_id}: {e}")
        if hasattr(e.response, "text"):
            log.error(f"Response details: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        log.error(f"Network error querying profile for account {account_id}: {e}")
        return None


def _get_lock_expiration(query_result: dict) -> datetime | None:
    try:
        raw_ts = query_result["profileChanges"][0]["profile"].get("profileLockExpiration")
        if not raw_ts:
            return None
        lock_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        return lock_dt if lock_dt > datetime.now(timezone.utc) else None
    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.warning(f"Could not parse profileLockExpiration: {e}")
        return None


def _set_stw_quickbar_sync(access_token: str, account_id: str, profile_id: str) -> dict | None:
    url = f"{FORTNITE_GAME_API_HOST}/fortnite/api/game/v2/profile/{account_id}/client/ModifyQuickbar?profileId={profile_id}&rvn=-1"
    headers = {**COMMON_HEADERS, "Authorization": f"Bearer {access_token}"}
    payload = {
        "primaryQuickbarChoices": ["", "", ""],
        "secondaryQuickbarChoice": ""
    }
    response = None
    try:
        log.debug(f"Calling SetStWQuickbar for account {account_id}, profile={profile_id}")
        log.debug(f"Payload sent: {json.dumps(payload)}")
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if response is not None:
            try:
                error_data = response.json()
                if error_data.get("errorCode") == "errors.com.epicgames.fortnite.not_ready":
                    log.error(f"Save the World not ready for account {account_id}. Error: {error_data.get('errorMessage', 'N/A')}")
                    return {"error": "SAVE_THE_WORLD_NOT_READY", "details": error_data.get('errorMessage', 'N/A')}
            except json.JSONDecodeError:
                pass
        log.error(f"Error setting StW Quickbar for account {account_id}: {e}")
        if response is not None and hasattr(response, 'text'):
            log.error(f"Response details: {response.text}")
        return None
    except requests.exceptions.RequestException as e:
        log.error(f"Network or request error setting StW Quickbar for account {account_id}: {e}")
        return None


# ── Auth helper ───────────────────────────────────────────────────────────────

def _get_auth(interaction: discord.Interaction) -> tuple[str, str] | None:
    auth_data = utils.load_auth_codes()
    user_id_str = str(interaction.user.id)
    if user_id_str not in auth_data or \
       "access_token" not in auth_data[user_id_str] or \
       "account_id" not in auth_data[user_id_str]:
        return None
    return auth_data[user_id_str]["access_token"], auth_data[user_id_str]["account_id"]


# ── Embed builders ────────────────────────────────────────────────────────────

def _build_countdown_embed(lock_dt: datetime) -> discord.Embed:
    delta = lock_dt - datetime.now(timezone.utc)
    total_seconds = max(int(delta.total_seconds()), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_remaining = f"{hours:02}:{minutes:02}:{seconds:02}"
    unix_ts = int(lock_dt.timestamp())
    embed = discord.Embed(
        title="⏳ Profile Lock Timer",
        description=(
            "Your profile is currently **locked**. The timer is running.\n\n"
            f"**Time remaining:** `{time_remaining}`\n"
            f"**Unlocks at:** <t:{unix_ts}:T> (<t:{unix_ts}:R>)"
        ),
        color=discord.Color.orange()
    )
    return embed


# ── Discord UI Views ──────────────────────────────────────────────────────────

class ModifyView(discord.ui.View):
    """Shown after the timer expires — lets the user trigger ModifyQuickbar."""

    def __init__(self, access_token: str, account_id: str):
        super().__init__(timeout=300)
        self.access_token = access_token
        self.account_id = account_id

    @discord.ui.button(label="Modify", style=discord.ButtonStyle.success, emoji="🔓")
    async def modify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        loop = asyncio.get_running_loop()
        set_result = await loop.run_in_executor(
            None, _set_stw_quickbar_sync, self.access_token, self.account_id, "theater0"
        )

        if set_result and "error" in set_result and set_result["error"] == "SAVE_THE_WORLD_NOT_READY":
            embed = discord.Embed(
                title="❌ Save the World Not Ready",
                description=(
                    "It appears your Epic Games account either **does not own Save the World**, "
                    "or you **have not completed the Save the World tutorial** yet.\n\n"
                    "To use this feature, please ensure you own Save the World and have progressed past the initial tutorial."
                ),
                color=discord.Color.orange()
            )
            log.warning(f"[{self.account_id}] STW not ready during ModifyQuickbar.")
            await interaction.edit_original_response(embed=embed, view=None)

        elif set_result:
            embed = discord.Embed(
                title="✅ Profile Unlocked",
                description="Your Save the World Quickbar has been successfully cleared.\n\nYour profile is now **unlocked**.",
                color=discord.Color.green()
            )
            log.info(f"[{self.account_id}] Successfully modified quickbar, profile unlocked.")
            await interaction.edit_original_response(embed=embed, view=None)

        else:
            embed = discord.Embed(
                title="❌ Modify Failed",
                description="Failed to modify your Quickbar due to an unexpected error. Please check your authentication or try again.",
                color=discord.Color.red()
            )
            log.error(f"[{self.account_id}] ModifyQuickbar failed with unhandled error.")
            await interaction.edit_original_response(embed=embed, view=None)


class StartView(discord.ui.View):
    """Initial panel with the Start button."""

    def __init__(self, access_token: str, account_id: str):
        super().__init__(timeout=300)
        self.access_token = access_token
        self.account_id = account_id

    @discord.ui.button(label="Start", style=discord.ButtonStyle.primary, emoji="▶️")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()

        loop = asyncio.get_running_loop()
        query_result = await loop.run_in_executor(
            None, _query_profile_sync, self.access_token, self.account_id, "theater0"
        )

        if query_result is None:
            embed = discord.Embed(
                title="❌ Profile Query Failed",
                description="Could not retrieve your Save the World profile. Please check your authentication or try again later.",
                color=discord.Color.red()
            )
            await interaction.edit_original_response(embed=embed, view=None)
            return

        if "errorCode" in query_result:
            if query_result["errorCode"] == "errors.com.epicgames.fortnite.not_ready":
                embed = discord.Embed(
                    title="❌ Save the World Not Ready",
                    description=(
                        "Your Epic Games account either **does not own Save the World**, "
                        "or you **have not completed the Save the World tutorial** yet."
                    ),
                    color=discord.Color.red()
                )
                await interaction.edit_original_response(embed=embed, view=None)
                return

        lock_expiration = _get_lock_expiration(query_result)

        if lock_expiration is None:
            # No lock active — skip timer and go straight to Modify
            embed = discord.Embed(
                title="✅ Profile Not Locked",
                description="Your profile is **not currently locked**.\n\nPress **Modify** to unlock your profile.",
                color=discord.Color.green()
            )
            await interaction.edit_original_response(embed=embed, view=ModifyView(self.access_token, self.account_id))
            log.info(f"[{self.account_id}] Profile not locked, skipping timer.")
            return

        # Profile is locked — run the live countdown
        log.info(f"[{self.account_id}] Profile locked until {lock_expiration.isoformat()}, starting countdown.")
        await interaction.edit_original_response(embed=_build_countdown_embed(lock_expiration), view=None)
        message = await interaction.original_response()

        while True:
            await asyncio.sleep(1)

            if datetime.now(timezone.utc) >= lock_expiration:
                ready_embed = discord.Embed(
                    title="🔓 Lock Expired",
                    description="The lock has **expired**.\n\nPress **Modify** to unlock your profile.",
                    color=discord.Color.green()
                )
                try:
                    await message.edit(embed=ready_embed, view=ModifyView(self.access_token, self.account_id))
                except discord.HTTPException as e:
                    log.warning(f"[{self.account_id}] Failed to edit unlock embed: {e}")
                log.info(f"[{self.account_id}] Lock expired, showing Modify button.")
                break

            try:
                await message.edit(embed=_build_countdown_embed(lock_expiration))
            except discord.HTTPException as e:
                log.warning(f"[{self.account_id}] Failed to edit countdown embed: {e}")
                break


# ── /profileunlock command ────────────────────────────────────────────────────

async def profile_unlock(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    auth = _get_auth(interaction)
    if auth is None:
        embed = discord.Embed(
            title="❌ Not Logged In",
            description="You're not currently logged in. Use **/login**.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    access_token, account_id = auth

    embed = discord.Embed(
        title="🏠 Profile Unlock",
        description=(
            "Enter your homebase and press **Start** to begin the timer.\n\n"
            "The bot will wait for your profile lock to expire, "
            "then allow you to modify your profile."
        ),
        color=discord.Color.blurple()
    )

    await interaction.followup.send(embed=embed, view=StartView(access_token, account_id))
    log.info(f"[{account_id}] ProfileUnlock panel sent.")