import discord
import requests
import json
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
from views.token_shop import TokenShopView

FLASK_BASE_URL = "https://luxbot-production-0bcb.up.railway.app" # must be set in Railway

intents = discord.Intents.default()
intents.members = True
load_dotenv()
token = os.getenv('DISCORD_TOKEN')

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
        response = requests.get(f"https://api.neatqueue.com/api/v1/playerstats/{interaction.guild_id}/{interaction.user.id}",timeout=5)
    except requests.RequestException as e:
        await interaction.followup.send(f"NeatQ request failed: {e}", ephemeral=True)
        return

    if response.status_code != 200:
        await interaction.followup.send(
            f"Failed to fetch tokens (status {response.status_code}). Try again later.",
            ephemeral=True,
        )
        return

    data=response.json()
    points = data.get('points')

    await interaction.followup.send(f"You have **{points}** tokens/points")



bot.run(token, log_handler=handler, log_level=logging.DEBUG)
