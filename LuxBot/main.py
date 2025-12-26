import discord
import requests
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os

FLASK_BASE_URL = "http://127.0.0.1:5001"
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

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if "shit" in message.content.lower():
        await message.delete()
        await message.channel.send(f"{message.author.mention} - dont use that word!")

    await bot.process_commands(message)

@bot.command()
async def buytoken(ctx):
    await ctx.message.delete()

    msg = await ctx.message.channel.send(f"{ctx.message.author.mention} check your DMs!")
    await msg.delete(delay=5)

    try:
        response = requests.post(
            f"{FLASK_BASE_URL}/create-checkout",
            json={"discord_id": ctx.message.author.id},
            timeout=10
        )
    except requests.RequestException:
        await ctx.author.send("Payment Service Unavailable")
        return
    if response.status_code != 200:
        await ctx.author.send("Failed to generate payment link")
        return

    data = response.json()
    payment_url = data.get('payment_url')

    if not payment_url:
        await ctx.author.send("Payment Link Missing")
        return

    await ctx.author.send(
        f"**Complete your payment here:** \n{payment_url}"
    )


bot.run(token, log_handler=handler, log_level=logging.DEBUG)
