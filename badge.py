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

class Badge:
    saving_attributes: tuple[str, ...] = ('id', 'name', 'prefix', 'on_grant', 'image_url')
    def __init__(self, cog: 'Badges', id: Optional[str], name: str, prefix: str, on_grant: str, image_url: Optional[str]) -> None:
        self.cog = cog
        self.id = id or os.urandom(16).hex()
        self.name = name
        self.prefix = prefix
        self.on_grant = on_grant
        self.image_url = image_url

    def on_grant_message(self, user: User) -> str:
        message = self.on_grant
        for before, after in [
            ('{user_mention}', user.mention),
            ('{name}', self.name),
            ('{prefix}', self.prefix),
            ('{user_badge_count}', sum(self.cog.data(id=user.id).values())),
            ('{full_name}', self),
        ]:
            message = message.replace(str(before), str(after))
        return message

    def save(self) -> None:
        assert self.cog.find(name=self.name) is None, 'Badge with this name already exists'
        self.cog.bot.badge_db['badges'].append(
            {attr: getattr(self, attr) for attr in self.saving_attributes}
        )
        self.cog.bot.save_badge_db()

    def __str__(self) -> str:
        if self.prefix:
            return f'{self.prefix} {self.name}'
        return self.name


class CreationModal(discord.ui.Modal):
    def __init__(self, cog: 'Badges', user: User, image_url: Optional[str]) -> None:
        super().__init__(timeout=300.0, title='Create Badge')
        self.cog = cog
        self.user = user
        self.image_url = image_url

        self.name = discord.ui.TextInput(
            label='Badge Name',
            placeholder='Ex. Contest Winner / Most Valuable Player',
        )
        self.prefix = discord.ui.TextInput(
            label='Badge Prefix',
            placeholder='Ex. 💖 / [mod] / ⭐ / 💎',
            required=False,
        )
        self.on_grant = discord.ui.TextInput(
            label='On Grant',
            default=(
                'Hey, {user_mention}! You have obtained the **{name}** badge!\n'
                'You now have {user_badge_count} badges in total.\n\n'
                'I hope you enjoy your **{full_name}** badge!'
            ),
            style=discord.TextStyle.long,
        )
        for text_input in [self.name, self.prefix, self.on_grant]:
            self.add_item(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        name, prefix, on_grant = self.name.value, self.prefix.value, self.on_grant.value
        if self.cog.find(name=name):
            await interaction.response.send_message(
                embed=self.cog.bot.embed('A badge with that name already exists.'),
                ephemeral=True,
            )
            return
        badge = Badge(cog=self.cog, id=None, name=name, prefix=prefix, on_grant=on_grant, image_url=self.image_url)
        badge.save()
        await interaction.response.send_message(
            embed=self.cog.bot.embed(
                title='Badge Created',
                description=f'Badge `{badge}` has been created.',
            ),
        )


class Badges(commands.GroupCog, name='badge'):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name='create', description='Create a badge')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def create(self, interaction: discord.Interaction, image: Optional[discord.Attachment] = None) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        image_url = image.url if image is not None else None
        await interaction.response.send_modal(CreationModal(cog=self, user=interaction.user, image_url=image_url))

    @app_commands.command(name='delete', description='Delete a badge')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def delete(self, interaction: discord.Interaction, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        badge = await self.find_with_send(interaction=interaction, name=name)
        if badge is None:
            return
        for i, data in enumerate(self.bot.badge_db['badges']):
            if data['id'] == badge.id:
                self.bot.badge_db['badges'].pop(i)
                break
        for id, data in list(self.bot.badge_db['users'].items()):
            data.pop(badge.id, None)
            self.set_data(id=int(id), data=data, save=False)
        self.bot.save_badge_db()
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Badge Deleted',
                description=f'Badge `{badge}` has been deleted.',
            ),
        )

    @app_commands.command(name='grant', description='Grant a badge to a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='badge')
    async def grant(self, interaction: discord.Interaction, user: User, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        badge = await self.find_with_send(interaction=interaction, name=name)
        if badge is None:
            return
        data = self.data(id=user.id)
        data[badge.id] = data.get(badge.id, 0) + 1
        self.set_data(id=user.id, data=data)
        await interaction.response.send_message(
            user.mention,
            embed=self.bot.embed(
                title='Badge Granted',
                description=badge.on_grant_message(user=user),
            ),
        )

    @app_commands.command(name='role_grant', description='Grant a badge to all users with a specific role')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='badge')
    async def role_grant(self, interaction: discord.Interaction, role: discord.Role, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        badge = await self.find_with_send(interaction=interaction, name=name)
        if badge is None:
            return
        for user in role.members:
            data = self.data(id=user.id)
            data[badge.id] = data.get(badge.id, 0) + 1
            self.set_data(id=user.id, data=data, save=False)
        self.bot.save_badge_db()
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Badge Granted',
                description=f'Badge `{badge}` has been granted to all users with the role `{role}`.',
            ),
        )

    @app_commands.command(name='revoke', description='Revoke a badge from a user')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    @app_commands.rename(name='badge')
    async def revoke(self, interaction: discord.Interaction, user: User, name: str) -> None:
        if not await self.bot.is_admin(interaction=interaction): return
        badge = await self.find_with_send(interaction=interaction, name=name)
        if badge is None:
            return
        data = self.data(id=user.id)
        if badge.id not in data:
            await interaction.response.send_message(
                embed=self.bot.embed('That user does not have that badge.'),
                ephemeral=True,
            )
            return
        data[badge.id]  = max(0, data[badge.id] - 1)
        if data[badge.id] == 0:
            del data[badge.id]
        self.set_data(id=user.id, data=data)
        await interaction.response.send_message(
            embed=self.bot.embed(
                title='Badge Revoked',
                description=f'Successfully revoked the `{badge}` from {user.mention}.'
            ),
        )

    @app_commands.command(name='view', description='View a certain badge')
    async def view(self, interaction: discord.Interaction, name: str) -> None:
        badge = await self.find_with_send(interaction=interaction, name=name)
        if badge is None:
            return
        embed = self.bot.embed(
            title=f'Badge Information: **{badge}**',
            description=(
                f'Name: `{badge.name}`\n'
                f'ID: `{badge.id}`'
            ),
        )
        if badge.image_url is not None:
            embed.set_image(url=badge.image_url)
        await interaction.response.send_message(embed=embed)

    def find(self, name: Optional[str] = None, id: Optional[str] = None) -> Optional[Badge]:
        if name is None and id is None:
            raise ValueError('Either name or id must be provided.')
        key, value = ('name', name.lower()) if name is not None else ('id', id)
        for b in self.bot.badge_db['badges']:
            item = b[key]
            if key == 'name':
                item = item.lower()
            if item == value:
                return Badge(cog=self, **b)
        return None

    async def find_with_send(self, interaction: discord.Interaction, name: str) -> Optional[Badge]:
        badge = self.find(name=name)
        if badge is None:
            await interaction.response.send_message(
                embed=self.bot.embed('No badge with that name exists.'),
                ephemeral=True,
            )
        return badge

    def data(self, id: int) -> dict[str, int]:
        return self.bot.badge_db['users'].get(str(id), {})

    def set_data(self, id: int, data: dict[str, int], save: bool = True) -> None:
        if data:
            self.bot.badge_db['users'][str(id)] = data
        else:
            self.bot.badge_db['users'].pop(str(id), None)
        if save:
            self.bot.save_badge_db()

    @delete.autocomplete('name')
    @grant.autocomplete('name')
    @revoke.autocomplete('name')
    @view.autocomplete('name')
    async def badge_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        try:
            found: list[app_commands.Choice[str]] = [
                app_commands.Choice(name=b['name'], value=b['name'])
                for b in self.bot.badge_db['badges']
                if current in b['name'].lower()
            ]
            if not found:
                raise IndexError
        except IndexError:
            return [app_commands.Choice(name='No badges found', value='')]
        return found


async def setup(bot: Bot) -> None:
    cog = Badges(bot)
    bot.badge_cog = cog
    await bot.add_cog(cog)

# author: j_sse#1732 https://github.com/69Jesse