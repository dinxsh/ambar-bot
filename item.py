import discord
from discord.ext import commands
from discord import app_commands
from main import Bot

import os

from typing import (
    TypeAlias,
    Optional,
)


User: TypeAlias = discord.User | discord.Member


class Item:
    saving_attributes: tuple[str, ...] = ('id', 'name', 'cost', 'image_url')
    def __init__(self, cog: 'Items', id: Optional[str], name: str, cost: int, image_url: Optional[str]) -> None:
        self.cog = cog
        self.id = id or os.urandom(16).hex()
        self.name = name
        self.cost = cost
        self.image_url = image_url

    def save(self) -> None:
        assert self.cog.find(name=self.name) is None, 'Item with this name already exists'
        self.cog.bot.item_db['items'].append(
            {attr: getattr(self, attr) for attr in self.saving_attributes}
        )
        self.cog.bot.save_item_db()

    def __str__(self) -> str:
        return self.name


class CreationModal(discord.ui.Modal):
    def __init__(self, cog: 'Items', user: User, image_url: Optional[str]) -> None:
        super().__init__(timeout=300.0, title='Create Item')
        self.cog = cog
        self.user = user
        self.image_url = image_url

        self.name = discord.ui.TextInput(
            label='Item Name',
            placeholder='Ex. Shoutout',
        )
        self.cost = discord.ui.TextInput(
            label='Cost',
            placeholder='Ex. 1 / 3 / 10 / 100',
        )
        for text_input in [self.name, self.cost]:
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name, cost = self.name.value, self.cost.value
        if self.cog.find(name=name):
            await interaction.response.send_message(
                embed=self.cog.bot.embed('A item with that name already exists.'),
                ephemeral=True,
            )
            return
        try:
            cost = int(cost)
        except ValueError:
            await interaction.response.send_message(
                embed=self.cog.bot.embed('Weight must be a number.'),
                ephemeral=True,
            )
            return
        item = Item(cog=self.cog, id=None, name=name, cost=cost, image_url=self.image_url)
        item.save()
        await interaction.response.send_message(
            embed=self.cog.bot.embed(
                title='Item Created',
                description=f'Item `{item}` has been created.',
            ),
        )


class Items(commands.GroupCog, name='item'):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name='create', description='Create a item')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def create(self, interaction: discord.Interaction, image: Optional[discord.Attachment] = None) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        image_url = image.url if image is not None else None
        await interaction.response.send_modal(CreationModal(cog=self, user=interaction.user, image_url=image_url))

    @app_commands.command(name='delete', description='Delete a item')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        item = await self.find_with_send(interaction=interaction, name=name)
        if item is None:
            return
        for i, data in enumerate(self.bot.item_db['items']):
            if data['id'] == item.id:
                self.bot.item_db['items'].pop(i)
                break
        for id, data in list(self.bot.item_db['users'].items()):
            data.pop(item.id, None)
            self.set_data(id=int(id), data=data, save=False)
        self.bot.save_item_db()
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Item Deleted',
                description=f'Item `{item}` has been deleted.',
            ),
        )

    @app_commands.command(name='shop', description='View the shop')
    async def shop(self, interaction: discord.Interaction) -> None:
        embed = self.bot.embed(
            title='Shop',
            description='Items can be purchased using the `item buy` command.\n\n' + '\n'.join(
                f'> {i}. **{item["name"]}** - `{item["cost"]}`'
                for i, item in enumerate(self.bot.item_db['items'], start=1)
            ),
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='buy', description='Buy an item')
    async def buy(self, interaction: discord.Interaction, name: str) -> None:
        item = await self.find_with_send(interaction=interaction, name=name)
        if item is None:
            return
        data = self.data(id=interaction.user.id)
        wallet: int = self.bot.ambar_cog.wallet(id=interaction.user.id)
        if wallet < item.cost:
            await interaction.response.send_message(
                embed=self.bot.embed(
                    f'You do not have enough funds to purchase this item. You need {item.cost - wallet} more.',
                ),
                ephemeral=True,
            )
            return
        self.bot.ambar_cog.set_wallet(id=interaction.user.id, amount=wallet - item.cost)
        data[item.id] = data.get(item.id, 0) + 1
        self.set_data(id=interaction.user.id, data=data)
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Item Purchased',
                description=f'You have purchased `{item}`.',
            ),
        )

    @app_commands.command(name='give', description='Give an item to a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, name: str, user: discord.User) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        item = await self.find_with_send(interaction=interaction, name=name)
        if item is None:
            return
        data = self.data(id=user.id)
        data[item.id] = data.get(item.id, 0) + 1
        self.set_data(id=user.id, data=data)

    @app_commands.command(name='remove', description='Remove an item from a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def remove(self, interaction: discord.Interaction, name: str, user: discord.User) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        item = await self.find_with_send(interaction=interaction, name=name)
        if item is None:
            return
        data = self.data(id=user.id)
        data[item.id] = data.get(item.id, 0) - 1
        self.set_data(id=user.id, data=data)

    @app_commands.command(name='view', description='View a certain item')
    async def view(self, interaction: discord.Interaction, name: str) -> None:
        item = await self.find_with_send(interaction=interaction, name=name)
        if item is None:
            return
        embed = self.bot.embed(
            title=f'Item Information: **{item}**',
            description=(
                f'Name: `{item.name}`\n'
                f'Cost: `{item.cost}`\n'
                f'ID: `{item.id}`'
            ),
        )
        if item.image_url is not None:
            embed.set_image(url=item.image_url)
        await interaction.response.send_message(embed=embed)

    def find(self, name: Optional[str] = None, id: Optional[str] = None) -> Optional[Item]:
        if name is None and id is None:
            raise ValueError('Either name or id must be provided.')
        key, value = ('name', name.lower()) if name is not None else ('id', id)
        for b in self.bot.item_db['items']:
            item = b[key]
            if key == 'name':
                item = item.lower()
            if item == value:
                return Item(cog=self, **b)
        return None

    async def find_with_send(self, interaction: discord.Interaction, name: str) -> Optional[Item]:
        item = self.find(name=name)
        if item is None:
            await interaction.response.send_message(
                embed=self.bot.embed('No item with that name exists.'),
                ephemeral=True,
            )
        return item

    def data(self, id: int) -> dict[str, int]:
        return self.bot.item_db['users'].get(str(id), {})

    def set_data(self, id: int, data: dict[str, int], save: bool = True) -> None:
        if data:
            self.bot.item_db['users'][str(id)] = data
        else:
            self.bot.item_db['users'].pop(str(id), None)
        if save:
            self.bot.save_item_db()

    @delete.autocomplete('name')
    @buy.autocomplete('name')
    @give.autocomplete('name')
    @remove.autocomplete('name')
    @view.autocomplete('name')
    async def item_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        try:
            found: list[app_commands.Choice[str]] = [
                app_commands.Choice(name=f"{b['name']} ({b['cost']})", value=b['name'])
                for b in self.bot.item_db['items']
                if current in b['name'].lower()
            ]
            if not found:
                raise IndexError
        except IndexError:
            return [app_commands.Choice(name='No items found', value='')]
        return found


async def setup(bot: Bot) -> None:
    cog = Items(bot)
    bot.item_cog = cog
    await bot.add_cog(cog)
