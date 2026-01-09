import discord
import aiohttp
import asyncio
import os

PRODUCT_LABELS = {
    "ten_tokens": "10 Tokens",
    "twenty_tokens": "20 Tokens",
    # "hundred_tokens": "100 Tokens",
}

# polling function to send receipt to user
async def poll_confirmation(
        message: discord.Message,
        flask_base_url: str,
        checkout_id: str,
        product: str,
):
    # custom key
    secret_key = os.getenv("POLL_SECRET")
    if not secret_key:
        return
    # running every 3 seconds for 5 mins
    for _ in range(100):
        await asyncio.sleep(3)

        #
        try:
            async with aiohttp.ClientSession() as session:
                # get request to flask API
                async with session.get(
                    f"{flask_base_url}/checkout-status/{checkout_id}",
                    params={"secret_key": secret_key},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    if response.status != 200:
                        continue
                    # reads response json get request
                    status = await response.json()
        except Exception:
            continue

        # Checking if response from Flask has been paid out and that the session exists
        if status.get("found") and status.get("payout") is True:
            # saves url of stripe receipt
            receipt_url = status.get("receipt_url")

            # message text for user
            receipt_msg = (f"**Payment Confirmed**\n"
                           f"**{product}** has been delivered.")
            if receipt_url:
                receipt_msg += f"\nReceipt: {receipt_url}"

            # edits message (containing checkout link) with receipt msg
            try:
                await message.edit(content=receipt_msg, view=None)
            except Exception:
                pass

            # POST request to update DB with info that receipt was sent out to eliminate spam to user
            try:
                async with aiohttp.ClientSession() as session:
                    await session.post(
                        f"{flask_base_url}/notified",
                        json={"secret_key": secret_key, "checkout_id": checkout_id},
                        timeout=aiohttp.ClientTimeout(total=8),
                    )
            except Exception:
                pass

            return

# Drop down menu for user
class TokenSelect(discord.ui.Select):
    def __init__(self, flask_base_url: str):
        self.flask_base_url = flask_base_url

        options = [
            discord.SelectOption(label="10 Tokens", value="ten_tokens", description="Buy 10 tokens"),
            discord.SelectOption(label="20 Tokens", value="twenty_tokens", description="Buy 50 tokens"),
            # discord.SelectOption(label="100 Tokens", value="hundred_tokens", description="Buy 100 tokens"),
        ]
        super().__init__(
            placeholder="Choose a token pack...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        print("callback")
        product = self.values[0]
        payload = {
            "discord_id": str(interaction.user.id),
            "product": product,  # backend maps this -> price_id
        }
        print(payload)

        # await interaction.response.defer()

        try:
            # Attempts to communicate with Flask app to generate checkout
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.flask_base_url}/create-checkout",
                    # json file containing product + discord_id
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        print(await resp.json())
                        await interaction.response.send_message(
                            "Failed to generate payment link. Try again later.",
                            ephemeral=True
                        )
                        return
                    data = await resp.json()
                    print(data)
        except Exception:
            await interaction.response.send_message(
                "Payment Service Unavailable.",
                ephemeral=True
            )
            return

        payment_url = data.get("payment_url")
        if not payment_url:
            await interaction.response.send_message("Payment Link Missing.", ephemeral=True)
            return

        checkout_id = data.get("session_id")

        label = PRODUCT_LABELS.get(product, product)

        # Clean UX: replace menu message with link and remove dropdown
        await interaction.response.edit_message(
            content=f"**{label}** checkout link:\n{payment_url}",
            view=None
        )

        # runs polling function to replace payment link with receipt on completion
        if checkout_id and interaction.message:
            asyncio.create_task(
                poll_confirmation(
                    message=interaction.message,
                    flask_base_url=self.flask_base_url,
                    checkout_id=checkout_id,
                    product=label,
                )
            )


class TokenShopView(discord.ui.View):
    def __init__(self, flask_base_url: str):
        super().__init__(timeout=60)
        self.message = None  # store message so we can edit it
        self.add_item(TokenSelect(flask_base_url=flask_base_url))

    async def on_timeout(self):
        # Disable all components
        for item in self.children:
            item.disabled = True

        # Edit the original message to show it's expired
        if self.message:
            try:
                await self.message.edit(
                    content="This menu has expired. Run `/buytoken` again.",
                    view=self
                )
            except Exception:
                pass