import discord
import requests
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

bot = commands.Bot(command_prefix='/', intents=intents)

@bot.event
async def on_ready():
    print('Logged in as')
    print(bot.user.name)
    print(bot.user.id)
    print('------')

# Test for language filtering
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if "shit" in message.content.lower():
        await message.delete()
        await message.channel.send(f"{message.author.mention} - dont use that word!")

    await bot.process_commands(message)

# User command to initiate checkout sequence through Stripe
@bot.command()
async def buytoken(ctx):
    await ctx.message.delete()
    print("Buy Token")
    # Inform User through channel where command was placed to check PMs
    msg = await ctx.message.channel.send(f"{ctx.message.author.mention} check your DMs!")
    await msg.delete(delay=5)

    try:
        await ctx.author.send(
            "Pick a token pack to purchase:",
            view=TokenShopView(flask_base_url=FLASK_BASE_URL)
        )
    except discord.Forbidden:
        await ctx.send(f"{ctx.author.mention} I can’t DM you—please enable DMs from this server.")

# Command to check current token count: WIP waiting on NeatQ API clarification
@bot.command()
async def tokencheck(ctx):
    await ctx.message.delete()
    bot_payload = {
        "channel_id": ctx.message.channel.id,
        "hidden": False,
        "user_id": int(ctx.message.author.id),
        "all_time": False
    }
    headers = {
        "Authorization": os.getenv("NEATQUEUE_KEY"),
        "Content-Type": "application/json",
    }
    response = requests.get("https://api.neatqueue.com/api/v1/playerstats/{interaction.guild_id}/{player_id}",timeout=5)
    if response.status_code != 200:
        print("Failed to call NeatQ", response.status_code, response.text)

    await ctx.message.channel.send(response.text)



bot.run(token, log_handler=handler, log_level=logging.DEBUG)
