from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
import pymongo

uri = "mongodb+srv://dineshtalwadker:omshanti2005@ambar.shkhbep.mongodb.net/test"
client = pymongo.MongoClient(uri)
db = client.data

import json
from typing import (
    TYPE_CHECKING,
    Awaitable,
    Optional,
    Callable,
    Any,
)

uri = "mongodb+srv://dineshtalwadker:omshanti2005@ambar.shkhbep.mongodb.net/test"
client = pymongo.MongoClient(uri)
db = client.data

if TYPE_CHECKING:
    from badge import Badges
    from trophy import Trophies
    from item import Items
    from ambar import Ambar


'''https://discord.com/api/oauth2/authorize?client_id=1058457937586176000&permissions=8&scope=bot%20applications.commands'''
with open('config.json', encoding='utf8') as file: config = json.load(file)
token = config.get('token')
owner_ids = config.get('owner_ids').copy()

class Bot(commands.Bot):
    user: discord.User
    badge_cog: 'Badges'
    trophy_cog: 'Trophies'
    item_cog: 'Items'
    ambar_cog: 'Ambar'
    def __init__(self) -> None:
        self.cog_names = ['tourney', 'badge', 'trophy', 'item', 'ambar']
        super().__init__(
            command_prefix=self.get_prefixes,
            activity=discord.Activity(type=discord.ActivityType.listening, name='you'),
            help_command=None,
            strip_after_prefix=True,
            intents=discord.Intents.all(),
            case_insensitive=True,
            owner_ids=set(owner_ids),
        )
        with open('tourney_db.json', encoding='utf8') as file:
            self.tourney_db = json.load(file)
        with open('badge_db.json', encoding='utf8') as file:
            self.badge_db = json.load(file)
        with open('trophy_db.json', encoding='utf8') as file:
            self.trophy_db = json.load(file)
        with open('item_db.json', encoding='utf8') as file:
            self.item_db = json.load(file)
        with open('ambar_db.json', encoding='utf8') as file:
            self.ambar_db = json.load(file)
        self.embed_color = 0x9845A8

    def save_tourney_db(self) -> None:
        with open('tourney_db.json', 'w', encoding='utf8') as file:
            json.dump(self.tourney_db, file, indent=4)
            col = db["tourney"]
            db.tourney.deleteMany({})

    def save_badge_db(self) -> None:
        with open('badge_db.json', 'w', encoding='utf8') as file:
            json.dump(self.badge_db, file, indent=4)
            col = db["badge"]
            db.badge.deleteMany({})

    def save_trophy_db(self) -> None:
        with open('trophy_db.json', 'w', encoding='utf8') as file:
            json.dump(self.trophy_db, file, indent=4)
            col = db["trophy"]
            db.trophy.deleteMany({})

    def save_item_db(self) -> None:
        with open('item_db.json', 'w', encoding='utf8') as file:
            json.dump(self.item_db, file, indent=4)
            col = db["item"]
            db.item.deleteMany({})

    def save_ambar_db(self) -> None:
        with open('ambar_db.json', 'w', encoding='utf8') as file:
            print(file)
            json.dump(self.ambar_db, file, indent=4)
            col = db["ambar"]
            db.ambar.deleteMany({})

    def get_prefixes(self, bot: commands.Bot, message: discord.Message) -> list[str]:
        return [
            '!',
        ]

    async def load(self, re: bool = False) -> None:
        func = self.reload_extension if re else self.load_extension
        for cog_name in self.cog_names: await func(cog_name)
        print('Cogs (re)loaded')

    async def setup_hook(self) -> None:
        await self.load()
        self.owner = self.application.owner # type: ignore
        print(f'\t\t\t\033[31m\033[1m >>> Logged in as {self.user.name}#{self.user.discriminator} <<< \033[0m')

    def embed(self, description: str, title: Optional[str] = None, color: Optional[int] = None) -> discord.Embed:
        return discord.Embed(
            title=title,
            description=description,
            color=color or self.embed_color,
        )

    async def is_admin(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id in owner_ids:
            return True
        await interaction.response.send_message(embed=self.embed('You are not an admin!'), ephemeral=True)
        return False


bot = Bot()
tree = app_commands.CommandTree(bot = Bot())

@bot.command(aliases=[])
@commands.is_owner()
async def Sync(ctx) -> None:
    await bot.tree.sync()
    await ctx.send('Successfully synced!')


@bot.command(aliases=[])
@commands.is_owner()
async def Reload(ctx) -> None:
    await bot.load(re=True)
    await ctx.send('Successfully reloaded!')


@bot.event
async def on_command_error(ctx, error) -> None:
    if isinstance(error, commands.NotOwner):
        print(f'{ctx.author} tried to run a command, but their id is not in the owners list.')
        return
    raise error


def main() -> None:
    bot.run(token)

