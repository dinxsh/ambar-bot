import discord
from discord.ext import commands
from discord import app_commands
from main import Bot

from enum import Enum

from badge import Badge
from trophy import Trophy
from item import Item

from typing import (
    TypeAlias,
    Optional,
    Any,
)


User: TypeAlias = discord.User | discord.Member


class Category(Enum):
    Badges = 0
    Trophies = 1
    Ambar = 2


class Ambar(commands.GroupCog, name='ambar'):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    def badges(self, id: int) -> list[Badge]:
        return [
            self.bot.badge_cog.find(id=id)  # type: ignore
            for id, amount in self.bot.badge_cog.data(id=id).items() for _ in range(amount)
        ]

    def trophies(self, id: int) -> list[Trophy]:
        return [
            self.bot.trophy_cog.find(id=id)  # type: ignore
            for id, amount in self.bot.trophy_cog.data(id=id).items() for _ in range(amount)
        ]

    def items(self, id: int) -> list[Item]:
        return [
            self.bot.item_cog.find(id=id)  # type: ignore
            for id, amount in self.bot.item_cog.data(id=id).items() for _ in range(amount)
        ]

    def data(self, id: int) -> tuple[list[Badge], list[Trophy], list[Item]]:
        return (
            self.badges(id=id),
            self.trophies(id=id),
            self.items(id=id),
        )

    @app_commands.command(name='profile', description='View your profile')
    async def profile(self, interaction: discord.Interaction, user: Optional[User] = None) -> None:
        user = user or interaction.user
        badges, trophies, items = self.data(id=user.id)
        wallet = self.wallet(id=user.id)
        embed = self.bot.embed(
            title=f'{user}\'s Profile',
            description=f'Ambar Balance: **{wallet}**\n\u200B',
        )
        fields: list[dict[str, Any]] = []
        if badges:
            fields.append(dict(
                name='**🔰 Badges**',
                value='\n'.join(f'> {badge}' for badge in badges),
                inline=False,
            ))
        if trophies:
            fields.append(dict(
                name='**🏆 Trophies**',
                value='\n'.join(f'> {trophy} `({trophy.weight})`' for trophy in trophies),
                inline=False,
            ))
        if items:
            fields.append(dict(
                name='**🛠️ Items**',
                value='\n'.join(f'> {item}' for item in items),
                inline=False,
            ))
        for field in fields[:-1]:
            field['value'] += '\n\u200B'
        for field in fields:
            embed.add_field(**field)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name='give', description='Give someone some ambar')
    async def give(self, interaction: discord.Interaction, user: User, amount: int) -> None:
        if amount <= 0:
            return await interaction.response.send_message(embed=self.bot.embed('You can\'t give negative or zero amount of ambar'), ephemeral=True)
        if self.wallet(id=interaction.user.id) < amount:
            return await interaction.response.send_message(embed=self.bot.embed('You don\'t have enough ambar'), ephemeral=True)
        self.set_wallet(id=interaction.user.id, amount=self.wallet(id=interaction.user.id) - amount)
        self.set_wallet(id=user.id, amount=self.wallet(id=user.id) + amount)
        await interaction.response.send_message(f'You gave **{amount}** ambar to {user.mention}.')

    @app_commands.command(name='add', description='Add ambar to someone\'s wallet')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def add(self, interaction: discord.Interaction, user: User, amount: int) -> None:
        if amount <= 0:
            return await interaction.response.send_message(embed=self.bot.embed('You can\'t add negative or zero amount of ambar'), ephemeral=True)
        self.set_wallet(id=user.id, amount=self.wallet(id=user.id) + amount)
        await interaction.response.send_message(embed=self.bot.embed(f'You added **{amount}** ambar to {user.mention}\'s wallet.'))

    @app_commands.command(name='remove', description='Remove ambar from someone\'s wallet')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def remove(self, interaction: discord.Interaction, user: User, amount: int) -> None:
        if amount <= 0:
            return await interaction.response.send_message(embed=self.bot.embed('You can\'t remove negative or zero amount of ambar'), ephemeral=True)
        self.set_wallet(id=user.id, amount=max(0, self.wallet(id=user.id) - amount))
        await interaction.response.send_message(embed=self.bot.embed(f'You removed **{amount}** ambar from {user.mention}\'s wallet.'))

    @app_commands.command(name='leaderboard', description='View the leaderboard')
    async def leaderboard(self, interaction: discord.Interaction, category: Category, page: int = 1) -> None:
        mention = lambda id: f'<@{id}>'
        data: list[tuple[str, tuple[int, ...]]] = []
        info: str
        if category == Category.Badges:
            data = sorted((
                (
                    mention(id),
                    (len(self.badges(id=int(id))),),
                )
                for id in self.bot.badge_db['users']
            ), key=lambda x: x[1], reverse=True)
            info = '**{0}** badges'
        elif category == Category.Trophies:
            def amount_and_weight(id: int) -> tuple[int, int]:
                trophies = self.trophies(id=id)
                return (len(trophies), sum(trophy.weight for trophy in trophies))
            data = sorted((
                (
                    mention(id),
                    amount_and_weight(id=int(id)),
                )
                for id in self.bot.trophy_db['users']
            ), key=lambda x: x[1][1], reverse=True)
            info = '**{1}** weight (**{0}** total trophies)'
        elif category == Category.Ambar:
            data = sorted((
                (
                    mention(id),
                    (self.wallet(id=int(id)),),
                )
                for id in self.bot.ambar_db
            ), key=lambda x: x[1], reverse=True)
            info = '**{0}** ambar'

        embed = self.bot.embed(
            title=f'{category.name} Leaderboard (Page {page})',
            description='\n'.join(
                f'{i}. {mention} - {info.format(*fmt)}'
                for i, (mention, fmt) in enumerate(data[10 * (page - 1):10 * page], start=10 * (page - 1) + 1)
            ),
        )
        await interaction.response.send_message(embed=embed)

    def wallet(self, id: int) -> int:
        return self.bot.ambar_db.get(str(id), 0)

    def set_wallet(self, id: int, amount: int) -> None:
        assert amount >= 0
        if amount == 0:
            self.bot.ambar_db.pop(str(id), None)
        else:
            self.bot.ambar_db[str(id)] = amount
        self.bot.save_ambar_db()

async def setup(bot: Bot) -> None:
    cog = Ambar(bot)
    bot.ambar_cog = cog
    await bot.add_cog(cog)
