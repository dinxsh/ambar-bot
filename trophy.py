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


class Trophy:
    saving_attributes: tuple[str, ...] = ('id', 'name', 'prefix', 'on_grant', 'weight', 'image_url')
    def __init__(self, cog: 'Trophies', id: Optional[str], name: str, prefix: str, on_grant: str, weight: int, image_url: Optional[str]) -> None:
        self.cog = cog
        self.id = id or os.urandom(16).hex()
        self.name = name
        self.prefix = prefix
        self.on_grant = on_grant
        self.weight = weight
        self.image_url = image_url

    def on_grant_message(self, user: User) -> str:
        message = self.on_grant
        for before, after in [
            ('{user_mention}', user.mention),
            ('{name}', self.name),
            ('{prefix}', self.prefix),
            ('{user_trophy_count}', sum(self.cog.data(id=user.id).values())),
            ('{user_trophy_weight}', sum(self.cog.find(id=id).weight * count for id, count in self.cog.data(id=user.id).items())),  # type: ignore
            ('{full_name}', self),
        ]:
            message = message.replace(str(before), str(after))
        return message

    def save(self) -> None:
        assert self.cog.find(name=self.name) is None, 'Trophy with this name already exists'
        self.cog.bot.trophy_db['trophies'].append(
            {attr: getattr(self, attr) for attr in self.saving_attributes}
        )
        self.cog.bot.save_trophy_db()

    def __str__(self) -> str:
        if self.prefix:
            return f'{self.prefix} {self.name}'
        return self.name


class CreationModal(discord.ui.Modal):
    def __init__(self, cog: 'Trophies', user: User, image_url: Optional[str]) -> None:
        super().__init__(timeout=300.0, title='Create Trophy')
        self.cog = cog
        self.user = user
        self.image_url = image_url

        self.name = discord.ui.TextInput(
            label='Trophy Name',
            placeholder='Ex. Contest Winner / Most Valuable Player',
        )
        self.prefix = discord.ui.TextInput(
            label='Trophy Prefix',
            placeholder='Ex. 💖 / [mod] / ⭐ / 💎',
            required=False,
        )
        self.on_grant = discord.ui.TextInput(
            label='On Grant',
            default=(
                'Hey, {user_mention}! You have obtained the **{name}** trophy!\n'
                'You now have {user_trophy_count} trophies ({user_trophy_weight} weight) in total.\n\n'
                'I hope you enjoy your **{full_name}** trophy!'
            ),
            style=discord.TextStyle.long,
        )
        self.weight = discord.ui.TextInput(
            label='Weight',
            placeholder='Ex. 1 / 3 / 10 / 100',
        )
        for text_input in [self.name, self.prefix, self.on_grant, self.weight]:
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name, prefix, on_grant, weight = self.name.value, self.prefix.value, self.on_grant.value, self.weight.value
        if self.cog.find(name=name):
            await interaction.response.send_message(
                embed=self.cog.bot.embed('A trophy with that name already exists.'),
                ephemeral=True,
            )
            return
        try:
            weight = int(weight)
        except ValueError:
            await interaction.response.send_message(
                embed=self.cog.bot.embed('Weight must be a number.'),
                ephemeral=True,
            )
            return
        trophy = Trophy(cog=self.cog, id=None, name=name, prefix=prefix, on_grant=on_grant, weight=weight, image_url=self.image_url)
        trophy.save()
        await interaction.response.send_message(
            embed=self.cog.bot.embed(
                title='Trophy Created',
                description=f'Trophy `{trophy}` has been created.',
            ),
        )


class Trophies(commands.GroupCog, name='trophy'):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name='create', description='Create a trophy')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def create(self, interaction: discord.Interaction, image: Optional[discord.Attachment] = None) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        image_url = image.url if image is not None else None
        await interaction.response.send_modal(CreationModal(cog=self, user=interaction.user, image_url=image_url))

    @app_commands.command(name='delete', description='Delete a trophy')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        trophy = await self.find_with_send(interaction=interaction, name=name)
        if trophy is None:
            return
        for i, data in enumerate(self.bot.trophy_db['trophies']):
            if data['id'] == trophy.id:
                self.bot.trophy_db['trophies'].pop(i)
                break
        for id, data in list(self.bot.trophy_db['users'].items()):
            data.pop(trophy.id, None)
            self.set_data(id=int(id), data=data, save=False)
        self.bot.save_trophy_db()
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Trophy Deleted',
                description=f'Trophy `{trophy}` has been deleted.',
            ),
        )

    @app_commands.command(name='grant', description='Grant a trophy to a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='trophy')
    async def grant(self, interaction: discord.Interaction, user: User, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        trophy = await self.find_with_send(interaction=interaction, name=name)
        if trophy is None:
            return
        data = self.data(id=user.id)
        data[trophy.id] = data.get(trophy.id, 0) + 1
        self.set_data(id=user.id, data=data)
        await interaction.response.send_message(
            user.mention,
            embed=self.bot.embed(
                title='Trophy Granted',
                description=trophy.on_grant_message(user=user),
            ),
        )

    @app_commands.command(name='role_grant', description='Grant a trophy to all users with a specific role')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='trophy')
    async def role_grant(self, interaction: discord.Interaction, role: discord.Role, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        trophy = await self.find_with_send(interaction=interaction, name=name)
        if trophy is None:
            return
        for user in role.members:
            data = self.data(id=user.id)
            data[trophy.id] = data.get(trophy.id, 0) + 1
            self.set_data(id=user.id, data=data, save=False)
        self.bot.save_trophy_db()
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Trophy Granted',
                description=f'Trophy `{trophy}` has been granted to all users with the role `{role}`.',
            ),
        )

    @app_commands.command(name='revoke', description='Revoke a trophy from a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='trophy')
    async def revoke(self, interaction: discord.Interaction, user: User, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        trophy = await self.find_with_send(interaction=interaction, name=name)
        if trophy is None:
            return
        data = self.data(id=user.id)
        if trophy.id not in data:
            await interaction.response.send_message(
                embed=self.bot.embed('That user does not have that trophy.'),
                ephemeral=True,
            )
            return
        data[trophy.id]  = max(0, data[trophy.id] - 1)
        if data[trophy.id] == 0:
            del data[trophy.id]
        self.set_data(id=user.id, data=data)
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Trophy Revoked',
                description=f'Successfully revoked the `{trophy}` from {user.mention}.'
            ),
        )

    @app_commands.command(name='view', description='View a certain trophy')
    async def view(self, interaction: discord.Interaction, name: str) -> None:
        trophy = await self.find_with_send(interaction=interaction, name=name)
        if trophy is None:
            return
        embed = self.bot.embed(
            title=f'Trophy Information: **{trophy}**',
            description=(
                f'Name: `{trophy.name}`\n'
                f'Weight: `{trophy.weight}`\n'
                f'ID: `{trophy.id}`'
            ),
        )
        if trophy.image_url is not None:
            embed.set_image(url=trophy.image_url)
        await interaction.response.send_message(embed=embed)

    def find(self, name: Optional[str] = None, id: Optional[str] = None) -> Optional[Trophy]:
        if name is None and id is None:
            raise ValueError('Either name or id must be provided.')
        key, value = ('name', name.lower()) if name is not None else ('id', id)
        for b in self.bot.trophy_db['trophies']:
            item = b[key]
            if key == 'name':
                item = item.lower()
            if item == value:
                return Trophy(cog=self, **b)
        return None

    async def find_with_send(self, interaction: discord.Interaction, name: str) -> Optional[Trophy]:
        trophy = self.find(name=name)
        if trophy is None:
            await interaction.response.send_message(
                embed=self.bot.embed('No trophy with that name exists.'),
                ephemeral=True,
            )
        return trophy

    def data(self, id: int) -> dict[str, int]:
        return self.bot.trophy_db['users'].get(str(id), {})

    def set_data(self, id: int, data: dict[str, int], save: bool = True) -> None:
        if data:
            self.bot.trophy_db['users'][str(id)] = data
        else:
            self.bot.trophy_db['users'].pop(str(id), None)
        if save:
            self.bot.save_trophy_db()

    @delete.autocomplete('name')
    @grant.autocomplete('name')
    @revoke.autocomplete('name')
    @view.autocomplete('name')
    async def trophy_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        try:
            found: list[app_commands.Choice[str]] = [
                app_commands.Choice(name=b['name'], value=b['name'])
                for b in self.bot.trophy_db['trophies']
                if current in b['name'].lower()
            ]
            if not found:
                raise IndexError
        except IndexError:
            return [app_commands.Choice(name='No trophies found', value='')]
        return found


async def setup(bot: Bot) -> None:
    cog = Trophies(bot)
    bot.trophy_cog = cog
    await bot.add_cog(cog)
