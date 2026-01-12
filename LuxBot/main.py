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


# User command to initiate checkout sequence through Stripe
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

    tournament_payload = {
        "channel_id": interaction.channel_id,
        "maximum_participants": player_count,
        "auto_create_new_tournament": False,
        "team_size": 0,
        "name": name,
        "description": desc,
        "details": desc,
        "forfeit_time_sec": 36000,
    }
    voice_payload = {
        "channel_id": interaction.channel_id,
        "toggle": False,
    }
    channels_payload = {
        "channel_id": interaction.channel_id,
        "name_format": "matchslip-$"
    }
    timer_payload = {
        "channel_id": interaction.channel_id,
        "timer": 36000
    }
    # Authenticating API Key + Declaring JSON to be sent
    headers = {
        "Authorization": os.getenv("NEATQUEUE_KEY"),
        "Content-Type": "application/json",
    }
    # send a POST req to NeatQ to process point change
    try:
        requests.post(
            "https://api.neatqueue.com/api/v2/tournament/create",
            json=tournament_payload,
            headers=headers,
            timeout=10,
        )
        requests.post(
            "https://api.neatqueue.com/api/v2/lobbychannel/timer",
            json=timer_payload,
            headers=headers,
            timeout=10,
        )
        requests.post(
            "https://api.neatqueue.com/api/v2/tempchannels/name",
            json=channels_payload,
            headers=headers,
            timeout=10,
        )
        requests.post(
            "https://api.neatqueue.com/api/v2/voicechannels/teamchannels",
            json=voice_payload,
            headers=headers,
            timeout=10,
        )
    except Exception as e:
        await interaction.followup.send(f"Command wrong or NeatQueue server error: {e}", ephemeral=True)

bot.run(token, log_handler=handler, log_level=logging.DEBUG)
