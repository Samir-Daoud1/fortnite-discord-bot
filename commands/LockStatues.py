import requests
import asyncio
import json
import utils
import discord
import coloredlogs
from datetime import datetime, timezone
from io import BytesIO

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


# ── Shared API helpers ────────────────────────────────────────────────────────

def _query_profile_sync(access_token: str, account_id: str, profile_id: str) -> dict | None:
    """Calls QueryProfile and returns the full raw response dict, or None on failure."""
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
    """
    Reads profileLockExpiration from profileChanges[0].profile.profileLockExpiration.
    Returns a timezone-aware UTC datetime if the lock is still active, else None.
    """
    try:
        # profileLockExpiration sits directly on the profile object, NOT inside stats.attributes
        raw_ts = query_result["profileChanges"][0]["profile"].get("profileLockExpiration")

        if not raw_ts:
            return None

        lock_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        return lock_dt if lock_dt > datetime.now(timezone.utc) else None

    except (KeyError, IndexError, ValueError, TypeError) as e:
        log.warning(f"Could not parse profileLockExpiration: {e}")
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


async def _send_not_logged_in(interaction: discord.Interaction):
    embed = discord.Embed(
        title="❌ Not Logged In",
        description="You're not currently logged in. Use **/login**.",
        color=discord.Color.red()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ── Countdown embed builder ───────────────────────────────────────────────────

def _build_locked_embed(lock_dt: datetime) -> discord.Embed:
    delta = lock_dt - datetime.now(timezone.utc)
    total_seconds = max(int(delta.total_seconds()), 0)

    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    time_remaining = f"{hours:02}:{minutes:02}:{seconds:02}"

    unix_ts = int(lock_dt.timestamp())

    embed = discord.Embed(
        title="🔒 Profile Locked",
        description=(
            "Your Save the World profile is currently **write-locked** by Epic's servers.\n\n"
            # f"**Time remaining:** `{time_remaining}`\n"
            f"**Unlocks at:** <t:{unix_ts}:T> (<t:{unix_ts}:R>)"
        ),
        color=discord.Color.orange()
    )
    return embed


# ── /lockstatus command ───────────────────────────────────────────────────────

async def check_lock_status(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)

    auth = _get_auth(interaction)
    if auth is None:
        await _send_not_logged_in(interaction)
        return

    access_token, account_id = auth
    loop = asyncio.get_running_loop()

    log.info(f"Querying theater0 profile for lock check — account: {account_id}")

    query_result = await loop.run_in_executor(
        None, _query_profile_sync, access_token, account_id, "theater0"
    )

    if query_result is None:
        embed = discord.Embed(
            title="❌ Profile Query Failed",
            description="Could not retrieve your Save the World profile. Please check your authentication or try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
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
            await interaction.followup.send(embed=embed)
            return

    lock_expiration = _get_lock_expiration(query_result)

    if lock_expiration is None:
        embed = discord.Embed(
            title="✅ Profile Unlocked",
            description="Your Save the World profile is **not locked**. You're free to use profile commands.",
            color=discord.Color.green()
        )
        log.info(f"[{account_id}] Profile is not locked.")
        await interaction.followup.send(embed=embed)
        return

    # ── Profile is locked — start the live countdown ──────────────────────────
    log.info(f"[{account_id}] Profile locked until {lock_expiration.isoformat()}, starting countdown.")
    message = await interaction.followup.send(embed=_build_locked_embed(lock_expiration))

    while True:
        await asyncio.sleep(1)

        if datetime.now(timezone.utc) >= lock_expiration:
            unlocked_embed = discord.Embed(
                title="✅ Profile Unlocked",
                description=(
                    f"{interaction.user.mention} Your Save the World profile lock has **expired**. "
                    "You're free to use profile commands."
                ),
                color=discord.Color.green()
            )
            try:
                await message.edit(embed=unlocked_embed)
            except discord.HTTPException as e:
                log.warning(f"[{account_id}] Failed to edit final unlock embed: {e}")
            log.info(f"[{account_id}] Lock expired, countdown finished.")
            break

        try:
            await message.edit(embed=_build_locked_embed(lock_expiration))
        except discord.HTTPException as e:
            log.warning(f"[{account_id}] Failed to edit countdown embed (message deleted?): {e}")
            break


# ── /profiledump command ──────────────────────────────────────────────────────

async def profile_dump(interaction: discord.Interaction):
    """Queries theater0 and sends the full raw JSON as a file attachment."""
    await interaction.response.defer(thinking=True)

    auth = _get_auth(interaction)
    if auth is None:
        await _send_not_logged_in(interaction)
        return

    access_token, account_id = auth
    loop = asyncio.get_running_loop()

    log.info(f"Dumping theater0 profile for account: {account_id}")

    query_result = await loop.run_in_executor(
        None, _query_profile_sync, access_token, account_id, "theater0"
    )

    if query_result is None:
        embed = discord.Embed(
            title="❌ Profile Query Failed",
            description="Could not retrieve your Save the World profile. Please check your authentication or try again later.",
            color=discord.Color.red()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    raw_json = json.dumps(query_result, indent=2)
    file_bytes = BytesIO(raw_json.encode("utf-8"))
    file = discord.File(fp=file_bytes, filename=f"theater0_dump_{account_id}.json")

    embed = discord.Embed(
        title="📄 Profile Dump",
        description="Here is your raw `theater0` QueryProfile response.",
        color=discord.Color.blue()
    )

    await interaction.followup.send(embed=embed, file=file, ephemeral=True)
    log.info(f"[{account_id}] theater0 profile dump sent.")