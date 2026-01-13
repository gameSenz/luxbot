import aiohttp
import discord
import requests
import json

from discord import app_commands
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
from supabase import create_client, Client
from supabase.client import ClientOptions
from views.token_shop import TokenShopView


intents = discord.Intents.default()
intents.members = True
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

FLASK_BASE_URL = str(os.getenv("FLASK_URL"))

PACK_TYPES = {
    "POKEMON": "Pokemon",
    "YUGIOH": "Yu-Gi-Oh",
    "RIFTBOUND": "Riftbound",
    "LORCANA": "Lorcana",
}

supabase_url: str = os.environ.get("SUPABASE_URL")
supabase_key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(
    supabase_url,
    supabase_key,
    options=ClientOptions(
        postgrest_client_timeout=10,
        storage_client_timeout=10,
        schema="public",
    )
)

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} ({bot.user.id})")

    # Sync slash commands (global)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s).")
    except Exception as e:
        print("Command sync failed:", e)


@bot.tree.command(name="award_packs", description="ADMIN: Award participation packs")
@app_commands.describe(
    user="User to award packs to",
    pack_type="Type of pack to award",
    amount="Amount of packs to award",
    notes="Tournament/Reason",
)
@app_commands.choices(pack_type=[
    app_commands.Choice(name="Pokemon", value="POKEMON"),
    app_commands.Choice(name="Yu-Gi-Oh", value="YUGIOH"),
    app_commands.Choice(name="Riftbound", value="RIFTBOUND"),
    app_commands.Choice(name="Lorcana", value="LORCANA"),
])
async def award_packs(
        interaction: discord.Interaction,
        user: discord.User,
        pack_type: app_commands.Choice[str],
        amount: int,
        notes: str, ):
    
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )

    if amount <= 0:
        return await interaction.response.send_message(
            "Amount must be greater than 0.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    try:
        # Record the award in Supabase
        # Note: Assuming 'Pack_Awards' table exists or similar to 'Order_History'
        response = supabase.table("pack_ledger").insert({
            "discord_id": int(user.id),
            "pack_type": pack_type.value,
            "change": amount,
            "notes": notes,
            "created_by": str(interaction.user.name)
        }).execute()
        ledger_id = response.data[0]["id"]

    except Exception as e:
        await interaction.followup.send(f"Failed to award packs: (DB Error)", ephemeral=True)
        return

    await interaction.followup.send(
        f"Successfully awarded **{amount}x {PACK_TYPES[pack_type.value]}** packs to **{user.display_name}**.\nNotes: {notes}",
        ephemeral=True
    )

    try:
        await user.send(f"You have been awarded **{amount}x {PACK_TYPES[pack_type.value]}** participation packs.\nNotes: {notes}\nReceipt ID: **{ledger_id}**")
    except discord.Forbidden:
        pass

@bot.tree.command(name="check_packs", description="Show your participation pack balances")
@app_commands.describe(user="Optional: view someone else's packs (admin only)")
async def check_packs(interaction: discord.Interaction, user: discord.User | None = None):
    # Default to self
    target = user or interaction.user

    # Optional permission rule: only allow viewing others if admin
    if user is not None and not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "You can only view your own packs.",
            ephemeral=True
        )

    discord_id = int(target.id)

    try:
        response = (
            supabase.table("pack_ledger")
            .select("pack_type, change")
            .eq("discord_id", discord_id)
            .execute()
        )
        rows = response.data or []
    except Exception:
        return await interaction.response.send_message(
            "Failed to fetch packs (database error).",
            ephemeral=True
        )

    balances = {i: 0 for i in PACK_TYPES}
    for row in rows:
        pack_type = str(row.get("pack_type", "")).upper()
        if pack_type in balances:
            balances[pack_type] += int(row.get("change") or 0)

    # Build display
    lines = [f"**{PACK_TYPES[pack_type]}**: `{balances[pack_type]}`" for pack_type in PACK_TYPES]

    embed = discord.Embed(
        title=f"{target.display_name}'s Packs",
        description="\n".join(lines),
        color=discord.Color.blue()
    )
    embed.set_thumbnail(url=target.display_avatar.url)

    await interaction.response.send_message(embed=embed, ephemeral=(user is None))


@bot.tree.command(name="fulfill_packs", description="ADMIN: Fulfill shipment of a user's packs")
async def fulfill_packs(interaction: discord.Interaction,
                      user: discord.User):

    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "You do not have permission to use this command.", ephemeral=True
        )

    await interaction.response.defer(ephemeral=True)

    discord_id = int(user.id)

    try:
        # Fetch current ledger to calculate balances
        response = (
            supabase.table("pack_ledger")
            .select("pack_type, change")
            .eq("discord_id", discord_id)
            .execute()
        )
        rows = response.data or []
    except Exception:
        return await interaction.followup.send(
            "Failed to fetch packs (database error).",
            ephemeral=True
        )

    balances = {i: 0 for i in PACK_TYPES}
    for row in rows:
        pack_type = str(row.get("pack_type", "")).upper()
        if pack_type in balances:
            balances[pack_type] += int(row.get("change") or 0)

    claims = []
    for pack_type, balance in balances.items():
        if balance > 0:
            try:
                supabase.table("pack_ledger").insert({
                    "discord_id": int(discord_id),
                    "pack_type": pack_type,
                    "change": -balance,
                    "notes": "Packs shipped out",
                    "created_by": str(interaction.user.id)
                }).execute()
                claims.append(f"**{balance} x {PACK_TYPES[pack_type]}**")
            except Exception as e:
                print(f"Error fulfilling {pack_type}: {e}")

    if not claims:
        return await interaction.followup.send("No packs left to fulfill", ephemeral=True)

    summary = "\n".join(claims)
    try:
        await user.send(f"You have been shipped: \n{summary}")
    except discord.Forbidden:
        pass


#User command to initiate checkout sequence through Stripe
@bot.tree.command(name="buytoken", description="Buy token packs (via DM)")
async def buytoken(interaction: discord.Interaction):

    # Inform User through channel where command was placed to check PMs
    await interaction.response.send_message("Check your DMs!", ephemeral=True)

    # Send checkout menu via DM
    try:
        view = TokenShopView(flask_base_url=FLASK_BASE_URL)
        dm_msg = await interaction.user.send("Select a token pack to purchase:", view=view)
        view.message = dm_msg

    except discord.Forbidden:
        await interaction.followup.send("I can’t DM you, please enable DMs from this server.", ephemeral=True)

# Command to check current token count: WIP waiting on NeatQ API clarification
@bot.tree.command(name="tokencheck", description="Check your current token/point balance.")
async def tokencheck(interaction: discord.Interaction):

    await interaction.response.defer(ephemeral=True)

    try:
        # On NEATQ TEST UPDATE ON LIVE
        response = requests.get(f"https://api.neatqueue.com/api/v1/playerstats/1442266660823240766/{interaction.user.id}",timeout=5)
    except requests.RequestException as e:
        await interaction.followup.send(f"NeatQ request failed: {e}", ephemeral=True)
        return

    if response.status_code != 200:
        await interaction.followup.send(
            f"If you are a **NEW** user your data will be updated on purchase\nElse, failed to fetch tokens either (status {response.status_code}). Try again later.",
            ephemeral=True,
        )
        return

    data=response.json()
    points = data.get('points')

    await interaction.followup.send(f"You have **{points}** tokens/points")


@bot.tree.command(name="create_tournament", description="ADMIN ONLY: Create a new tournament")
@app_commands.describe(
    name="Tournament Name",
    desc="Create a new tournament",
    player_count="Amt of players"
)
async def create_tournament(interaction: discord.Interaction,
                            name: str,
                            desc: str,
                            player_count: int,
                            ):
    await interaction.response.defer(ephemeral=True)

    tournament_payload = {
        "channel_id": int(interaction.channel_id),          # int
        "maximum_participants": int(player_count),           # int
        "tournament_type": "single_elimination",        # string
        "auto_start_on_fill": False,                    # boolean
        "auto_create_matches": True,                    # boolean
        "auto_create_new_tournament": int(0),                # int
        "team_size": int(1),                              # int | null
        "name": str(name),                                   # string | null
        "description": str(desc),                            # string
        "details": str(desc),                                # string | null
        "forfeit_timer_sec": int(36000),                     # int | null
        "hold_third_place_match": False,                # boolean
        "url": None,                                    # string | null
        "subdomain": None,                              # string | null
        "entry_price": None,                            # int | null
        "payout_fee": None                              # int | null
    }
    voice_payload = {
        "channel_id": interaction.channel_id,           # int
        "toggle": "Disabled".strip(),                           # string | Enabled or Disabled ???
    }
    channels_payload = {
        "channel_id": interaction.channel_id,           # int
        "name_format": "matchslip-$"                    # string
    }
    timer_payload = {
        "channel_id": interaction.channel_id,           # int
        "timer": 36000                                  # int
    }
    start_payload = {
        "channel_id": interaction.channel_id
    }
    # Authenticating API Key + Declaring JSON to be sent
    headers = {
        "Authorization": os.getenv("NEATQUEUE_KEY"),
        "Content-Type": "application/json",
    }
    async def post_json(session: aiohttp.ClientSession, url: str, payload: dict):
        async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"{url} failed ({response.status}): {text}")
            return text
    try:
        async with aiohttp.ClientSession() as session:
            r1 = await post_json(session, "https://api.neatqueue.com/api/v2/tournament/create", tournament_payload)
            r2 = await post_json(session, "https://api.neatqueue.com/api/v2/lobbychannel/timer", timer_payload)
            r3 = await post_json(session, "https://api.neatqueue.com/api/v2/tempchannels/name", channels_payload)
            r4 = await post_json(session, "https://api.neatqueue.com/api/v2/voicechannels/teamchannels", voice_payload)
            r5 = await post_json(session, "https://api.neatqueue.com/api/v2/tournament/start", start_payload)
        await interaction.followup.send(f"DEBUG r1={repr(r1)[:200]}", ephemeral=True)
        await interaction.followup.send(f"DEBUG r2={repr(r2)[:200]}", ephemeral=True)
        await interaction.followup.send(f"DEBUG r3={repr(r3)[:200]}", ephemeral=True)
        await interaction.followup.send(f"DEBUG r4={repr(r4)[:200]}", ephemeral=True)
        await interaction.followup.send(f"DEBUG r5={repr(r5)[:200]}", ephemeral=True)

        await interaction.followup.send(
            f"You have successfully created **{name}** tournament for **{player_count}** players.", ephemeral=True
        )

    except Exception as e:
        await interaction.followup.send(f"Command wrong or NeatQueue server error: {e}", ephemeral=True)

bot.run(token, log_handler=handler, log_level=logging.DEBUG)
