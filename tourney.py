from __future__ import annotations
import discord
from discord.ext import commands
from discord import app_commands
from main import Bot

from typing import (
    Optional,
    Any,
    Generator,
)
from typing_extensions import Self

import json
import os
import random
import math
from enum import Enum


with open('config.json', encoding='utf8') as file: config = json.load(file)	
DISPUTE_CHANNEL_NAME = 'disputes'


class Mode(Enum):
    SINGLE_ELIMINATION = 1
    ALL_VS_ALL = 2

    def __str__(self) -> str:
        return self.name.replace('_', ' ').title()


class Match:
    def __init__(self, teamindices: Optional[list[int]] = None, winner: Optional[int] = None) -> None:
        self.teamindices: list[int] = teamindices or []
        self.winner: Optional[int] = winner

    @property
    def versus(self) -> str:
        if self.winner is not None and self.winner < 0: return ' '
        return ' vs '.join(f'`{n}`' for n in self.teamindices + ['?']*(2-len(self.teamindices))) + f' **{self.winner} WON**'*(self.winner is not None)

    def __str__(self) -> str:
        return f'Match({self.teamindices} -> {self.winner})'

    def __repr__(self) -> str:
        return str(self)


Team = list[int]
Round = list[Match]


class Tournament:
    def __init__(self, **kwargs) -> None:
        self.saved_attributes: list[str] = [
            'name', 'id', 'guild_id', 'max_players',
            'team_size', 'prize', 'info',
            'teams', 'rounds', 'score',
            'published', 'opened_checkin', 'checked_in',
            'started', 'message_id', 'channel_id',
            'mode', 'admin_submit',
        ]
        for key, value in kwargs.items():
            setattr(self, key, value)
        assert all(hasattr(self, attr) for attr in self.saved_attributes)
        self.name: str
        self.id: str
        self.guild_id: int
        self.max_players: int
        self.team_size: int
        self.prize: str
        self.info: str
        self.teams: Optional[list[Team]]
        self.rounds: Optional[list[Round]] = [[Match(**m) if not isinstance(m, Match) else m for m in r] for r in self.rounds] if self.rounds is not None else None
        self.score: Optional[dict[str, int]]
        self.published: bool
        self.opened_checkin: bool
        self.checked_in: list[int]
        self.started: bool
        self.message_id: Optional[int]
        self.channel_id: Optional[int]
        self.bot: Bot
        self.finished: bool = False
        self.mode: int = int(self.mode)
        self.admin_submit: bool

    @classmethod
    def new(cls, name: str, guild_id: int, bot: Bot) -> Self:
        return cls(
            name=name,
            guild_id=guild_id,
            id=os.urandom(16).hex(),
            **config.get('default_settings'),
            teams=None,
            rounds=None,
            score=None,
            published=False,
            opened_checkin=False,
            checked_in=[],
            started=False,
            message_id=None,
            channel_id=None,
            mode=1,
            admin_submit=True,
            bot=bot,
        )

    @classmethod
    def from_json(cls, data: dict[str, Any], bot: Bot) -> Self:
        return cls(bot=bot, **data)

    @classmethod
    def from_id(cls, id: str, guild_id: int, bot: Bot) -> Self:
        if str(guild_id) not in bot.tourney_db:
            raise ValueError(f'No tournaments in this guild found.')
        data = bot.tourney_db.get(str(guild_id), {})
        if id in data:
            return cls.from_json(data.get(id, {}), bot=bot)
        raise ValueError(f'No tournament with id {id} found')

    @classmethod
    def from_name(cls, name: str, guild_id: int, bot: Bot) -> Self:
        if str(guild_id) not in bot.tourney_db:
            raise ValueError(f'No tournaments in this guild found.')
        for data in bot.tourney_db.get(str(guild_id), {}).values():
            if data.get('name') == name:
                return cls.from_json(data, bot=bot)
        raise ValueError(f'No tournament with name {name} found in this guild.')

    @classmethod
    def from_any(cls, value: str, guild_id: int, bot: Bot) -> Self:
        try:
            return cls.from_id(id=value, guild_id=guild_id, bot=bot)
        except ValueError:
            try:
                return cls.from_name(name=value, guild_id=guild_id, bot=bot)
            except ValueError:
                raise ValueError(f'No tournament with name or id **{value}** found in this guild.')

    def json(self) -> dict[str, Any]:
        return json.loads(json.dumps(self, default=lambda cls: vars(cls) if not hasattr(cls, 'saved_attributes') else {attr: getattr(cls, attr) for attr in cls.saved_attributes}))

    def __str__(self) -> str:
        return (
            f'**ID:** {self.id}\n'
            f'**Name:** {self.name}\n'
            f'**Max Players:** {self.max_players}\n'
            f'**Team Size:** {self.team_size}\n'
            f'**Prize:** {self.prize}\n'
            f'**Info:** {self.info}'
        )

    @property
    def total_players(self) -> int:
        assert self.teams is not None
        return sum(sum(p is not None for p in team) for team in self.teams)

    def teams_fields(self) -> Generator[dict[str, str], None, None]:
        assert self.teams is not None
        mention = lambda m: m.mention if m is not None else 'NOT FOUND'
        teams_str: list[str] = [
            '\n'.join(
                (
                    '`' + (f'{i:02}.' if j == 0 else f'   ') + '` ' +
                    (mention(self.bot.get_user(member_id)) + ' **CHECKED IN!**' * (member_id in self.checked_in)
                    if member_id is not None else '')
                ) for j, member_id in enumerate(team)
            ) for i, team in enumerate(self.teams, start=1)
        ]
        per_field: int = max(
            1, 8 // self.team_size
        )
        for i in range(0, len(teams_str), per_field):
            yield {
                'name': '**Teams**' if i == 0 else '** **',
                'value': '\n'.join(teams_str[i:i+per_field]) + '\n**' + ' '*50 + '**',
            }

    def rounds_fields(self) -> Generator[dict[str, str], None, None]:
        assert self.rounds is not None
        for i, r in enumerate(self.rounds, start=1):
            yield {
                'name': f'**Round {i}**',
                'value': '\n'.join(
                    m.versus for m in r
                ),
            }

    def score_fields(self) -> Generator[dict[str, str], None, None]:
        assert self.score is not None
        assert self.teams is not None
        playing = [i for i, team in enumerate(self.teams, start=1) if team[0] is not None]
        for team, score in self.score.items():
            if int(team) in playing:
                yield {
                    'name': f'**Score Team {team}**',
                    'value': f'`{score} point{"s"*(score != 1)}`',
                }

    @property
    def embed(self) -> discord.Embed:
        assert self.published
        if not self.started:
            embed = self.bot.embed(
                title=f'**{self.name}**',
                description=(
                    f'**Prize:** {self.prize}\n\n'
                    f'{self.info}\n\n'
                    f'**Players:** {self.total_players}/{self.max_players} ({self.team_size}v{self.team_size}) ' + str(Mode(self.mode))
                ))
            for field in self.teams_fields():
                embed.add_field(**field, inline=True)
        else:
            embed = self.bot.embed(
                title=f'**{self.name}**',
                description=(
                    f'**Prize:** {self.prize}\n\n'
                    f'{self.info}\n\n'
                    f'**Players:** {self.total_players}/{self.max_players} ({self.team_size}v{self.team_size}) ' + str(Mode(self.mode))
                ))
            for field in self.teams_fields():
                embed.add_field(**field, inline=True)
            if self.mode == 1:
                for field in self.rounds_fields():
                    embed.add_field(**field, inline=False)
            elif self.mode == 2:
                for field in self.score_fields():
                    embed.add_field(**field, inline=False)
        return embed

    @property
    def view(self) -> Optional[discord.ui.View]:
        assert self.published
        if self.finished:
            return None
        elif not self.started:
            return JoinableView(tournament=self, bot=self.bot)
        else:
            return StartedView(tournament=self, bot=self.bot)

    @property
    def channel(self) -> discord.TextChannel:
        assert self.channel_id is not None
        if not hasattr(self, '_channel'):
            self._channel = self.bot.get_channel(self.channel_id)
        assert isinstance(self._channel, discord.TextChannel)
        return self._channel

    @property
    def message(self) -> discord.PartialMessage:
        assert self.message_id is not None
        if not hasattr(self, '_message'):
            self._message = self.channel.get_partial_message(self.message_id)
        assert isinstance(self._message, discord.PartialMessage)
        return self._message

    def on_publish(self) -> None:
        assert not self.published
        self.published = True
        self.teams = [[None for _ in range(self.team_size)] for _ in range(self.max_players // self.team_size)]
        self.max_players = len(self.teams) * self.team_size

    def playing_teams(self) -> list[Team]:
        assert self.teams is not None
        return [team for team in self.teams if any(p for p in team)]

    def index(self, team: Team, plus1: bool = False) -> int:
        assert self.teams is not None
        return self.teams.index(team) + plus1

    def next_power2(self, n: int) -> int:
        return 2 ** (n - 1).bit_length()

    def set_starting_rounds(self) -> None:
        teams = self.playing_teams()
        assert len(teams) >= 2
        self.rounds = [[Match() for _ in range(self.next_power2(math.ceil(len(teams) / 2)))]]
        playing = random.sample(teams, k=len(teams))
        try:
            for i in sorted(range(len(self.rounds[0])), key=lambda i: i%2 == 0, reverse=True):
                match = self.rounds[0][i]
                for _ in range(2): match.teamindices.append(self.index(playing.pop(), plus1=True))
        except IndexError:
            self.rounds.append([Match() for _ in range(self.next_power2(len(self.rounds[-1]) // 2))])
            for i, match in enumerate(self.rounds[0]):
                if len(match.teamindices) == 1:
                    m = self.rounds[1][i // 2]
                    m.teamindices.append(match.teamindices[0])
                    match.winner = -1
        try:
            for i in range(0, len(self.rounds[0]), 2):
                m1 = self.rounds[0][i]
                m2 = self.rounds[0][i+1]
                if len(m1.teamindices) == 2 and len(m2.teamindices) == 0:
                    m1.winner, m2.winner = -1, -1
                    self.rounds[1][i // 2].teamindices.extend(m1.teamindices)
        except IndexError:
            pass

    def update_rounds(self) -> None:
        assert self.started
        if self.rounds is None: return self.set_starting_rounds()
        for i, matches in enumerate(self.rounds):
            for j, match in enumerate(matches):
                if match.winner is not None and match.winner > 0:
                    if i == len(self.rounds)-1:
                        if len(self.rounds[-1]) == 1:
                            self.finished = True
                            return
                        self.rounds.append([Match() for _ in range(self.next_power2(len(self.rounds[-1]) // 2))])
                    new_match = self.rounds[i + 1][j // 2]
                    if match.winner not in new_match.teamindices:
                        new_match.teamindices.append(match.winner)

    def on_start(self) -> None:
        print(self.mode)
        assert self.published and not self.started and self.teams is not None
        self.started = True
        if self.mode == 1:
            self.update_rounds()
        elif self.mode == 2:
            self.score = {str(i): 0 for i in range(1, len(self.teams) + 1)}
            self.rounds = [[]]

    def next_available_team(self, start: int = 0) -> Team:
        assert self.teams is not None
        for i in list(range(start, len(self.teams))) + list(range(0, start)):
            team = self.teams[i]
            if sum(p is None for p in team) > 0:
                return team
        raise ValueError('This tournament is full.')

    def find(self, user_id: int) -> tuple[int, int]:
        assert self.teams is not None
        for team_index, team in enumerate(self.teams):
            for member_index, member_id in enumerate(team):
                if member_id == user_id:
                    return team_index, member_index
        raise ValueError(f'You are not in this tournament.')

    async def update(self, interaction: Optional[discord.Interaction] = None, send: bool = True) -> None:
        self.bot.tourney_db[str(self.guild_id)][self.id] = self.json()
        self.bot.save_tourney_db()
        if send:
            func = interaction.response.edit_message if interaction is not None else self.message.edit
            await func(embed=self.embed, view=self.view)

    async def join(self, interaction: Optional[discord.Interaction], user_id: Optional[int] = None, start: int = 0) -> None:
        user_id = user_id or interaction.user.id  # type: ignore
        assert not self.started
        try: self.find(user_id)
        except ValueError: pass
        else: raise ValueError('You are already in this tournament.')
        team = self.next_available_team(start=start)
        team[team.index(None)] = user_id
        return await self.update(interaction)

    async def leave(self, interaction: Optional[discord.Interaction], user_id: Optional[int] = None) -> None:
        user_id = user_id or interaction.user.id  # type: ignore
        assert not self.started
        assert self.teams is not None
        team_index, member_index = self.find(user_id)
        self.teams[team_index][member_index] = None
        return await self.update(interaction)

    async def swap(self, interaction: discord.Interaction) -> None:
        assert not self.started
        assert self.teams is not None
        team_index, member_index = self.find(interaction.user.id)
        self.teams[team_index][member_index] = None
        return await self.join(interaction, start=team_index+1)

    async def checkin(self, interaction: discord.Interaction) -> None:
        assert self.teams is not None
        team_index, member_index = self.find(interaction.user.id)
        if interaction.user.id in self.checked_in:
            self.checked_in.remove(interaction.user.id)
        else:
            self.checked_in.append(interaction.user.id)
        return await self.update(interaction)

    def round_indices(self, player_id: int) -> tuple[int, int]:
        assert self.started
        assert self.teams is not None
        assert self.rounds is not None
        team_index, _ = self.find(player_id)
        for i in range(len(self.rounds)-1, -1, -1):
            for j, match in enumerate(self.rounds[i]):
                if team_index+1 in match.teamindices:
                    return i, j
        raise ValueError('You are not in this tournament.')

    async def submit(self, interaction: discord.Interaction) -> None:
        assert self.started
        assert self.teams is not None
        assert self.rounds is not None
        team_index, _ = self.find(interaction.user.id)
        if self.mode == 1:
            round_index, match_index = self.round_indices(interaction.user.id)
            match = self.rounds[round_index][match_index]
            if len(match.teamindices) < 2: raise ValueError('You do not have an opponent yet.')
            elif match.winner is not None: raise ValueError('You are out of this tournament.')
            view = SubmitViewSingle(tournament=self, bot=self.bot, team_number=team_index+1, round_index=round_index, match_index=match_index)
            await interaction.response.send_message(embed=self.bot.embed('Did your team **WIN** or **LOSE** this round?'), view=view, ephemeral=True)
        elif self.mode == 2:
            view = SubmitViewAll(tournament=self, bot=self.bot, team_number=team_index+1)
            await interaction.response.send_message(embed=self.bot.embed('Who did you play against?'), view=view, ephemeral=True)


class JoinableView(discord.ui.View):
    def __init__(self, tournament: Tournament, bot: Bot) -> None:
        super().__init__(timeout=0.0)
        self.tournament = tournament
        self.bot = bot

        styles: dict[str, discord.ButtonStyle] = {
            'join': discord.ButtonStyle.green,
            'leave': discord.ButtonStyle.red,
            'swap': discord.ButtonStyle.blurple,
            'checkin': discord.ButtonStyle.green,
        }
        labels: tuple[str, ...] = ('join', 'leave', 'swap_teams')
        if self.tournament.opened_checkin:
            labels += ('checkin',)
        for label in labels:
            self.add_item(discord.ui.Button(
                label=label.replace('_', ' ').title(),
                custom_id=self.tournament.id + ':' + label.split('_')[0],
                style=styles.get(label.split('_')[0], discord.ButtonStyle.gray),
                row=0,
            ))


class StartedView(discord.ui.View):
    def __init__(self, tournament: Tournament, bot: Bot) -> None:
        super().__init__(timeout=0.0)
        self.tournament = tournament
        self.bot = bot

        styles: dict[str, discord.ButtonStyle] = {
            'submit': discord.ButtonStyle.blurple,
        }
        labels: tuple[str, ...] = ('submit',) if not self.tournament.admin_submit else ()
        for label in labels:
            self.add_item(discord.ui.Button(
                label=label.replace('_', ' ').title(),
                custom_id=self.tournament.id + ':' + label.split('_')[0],
                style=styles.get(label.split('_')[0], discord.ButtonStyle.gray),
                row=0,
            ))


class SubmitViewSingle(discord.ui.View):
    def __init__(self, tournament: Tournament, bot: Bot, team_number: int, round_index: int, match_index: int) -> None:
        super().__init__(timeout=120.0)
        self.tournament = tournament
        self.bot = bot
        self.team_number = team_number
        self.round_index = round_index
        self.match_index = match_index

        self.won = discord.ui.Button(
            label='I Won',
            custom_id='handled_won',
            style=discord.ButtonStyle.green,
            row=0,
        )
        self.lost = discord.ui.Button(
            label='I Lost',
            custom_id='handled_lost',
            style=discord.ButtonStyle.red,
            row=0,
        )
        for button in (self.won, self.lost):
            button.callback = self.callback
            self.add_item(button)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert interaction.data is not None
        assert self.tournament.rounds is not None
        button = getattr(self, interaction.data.get('custom_id', '').split('_')[-1])
        if button is self.lost:
            match = self.tournament.rounds[self.round_index][self.match_index]
            match.winner = next(n for n in match.teamindices if n != self.team_number)
            self.tournament.update_rounds()
            await self.tournament.update()
        await interaction.response.edit_message(embed=self.bot.embed('Result successfully submitted!'), view=None)


class SubmitViewAll(discord.ui.View):
    def __init__(self, tournament: Tournament, bot: Bot, team_number: int, against_number: Optional[int] = None) -> None:
        super().__init__(timeout=120.0)
        self.tournament = tournament
        self.bot = bot
        self.team_number = team_number
        self.against_number = against_number

        if self.against_number is not None:
            self.won = discord.ui.Button(
                label='I Won',
                custom_id='handled_won',
                style=discord.ButtonStyle.green,
                row=0,
            )
            self.lost = discord.ui.Button(
                label='I Lost',
                custom_id='handled_lost',
                style=discord.ButtonStyle.red,
                row=0,
            )
            for button in (self.won, self.lost):
                button.callback = self.callback
                self.add_item(button)

        else:
            assert self.tournament.rounds is not None
            assert self.tournament.teams is not None
            played_against: list[int] = [
                next(n for n in match.teamindices if n != self.team_number) for match in self.tournament.rounds[0] if self.team_number in match.teamindices
            ]
            playing = self.tournament.playing_teams()
            options = [
                discord.SelectOption(label=str(n), value=str(n)) for n in range(1, self.tournament.max_players+1) if n != self.team_number and n not in played_against and self.tournament.teams[n-1] in playing
            ]
            self.team = discord.ui.Select(
                custom_id='handled_team',
                placeholder='Select a team to play against' if options else 'No other teams available',
                options=options if options else [discord.SelectOption(label='No other teams available', value='0')],
                row=0,
                disabled=False if options else True,
            )
            self.team.callback = self.callback
            self.add_item(self.team)

    async def callback(self, interaction: discord.Interaction) -> None:
        assert interaction.data is not None
        if self.against_number is None:
            view = SubmitViewAll(tournament=self.tournament, bot=self.bot, team_number=self.team_number, against_number=int(interaction.data.get('values', [])[0]))
            return await interaction.response.edit_message(embed=self.bot.embed('Did your team **WIN** or **LOSE** this round?'), view=view)
        assert self.tournament.rounds is not None
        button = getattr(self, interaction.data.get('custom_id', '').split('_')[-1])
        if button is self.lost:
            match = Match(teamindices=[self.team_number, self.against_number], winner=self.against_number)
            self.tournament.rounds[0].append(match)
            assert self.tournament.score is not None
            self.tournament.score[str(self.against_number)] += 1
            await self.tournament.update()
        await interaction.response.edit_message(embed=self.bot.embed('Result successfully submitted!'), view=None)


class ConfigModal(discord.ui.Modal, title='Tournament Config'):
    def __init__(self, tournament: Tournament, bot: Bot) -> None:
        super().__init__(timeout=300.0)
        self.tournament = tournament
        self.bot = bot

        for attr in ('name', 'max_players', 'team_size', 'prize', 'info'):
            self.add_item(discord.ui.TextInput(label=attr.replace('_', ' ').title(), custom_id=attr, default=getattr(self.tournament, attr), required=False))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for item in self.children:
            assert isinstance(item, discord.ui.TextInput)
            if item.value:
                value = item.value if not isinstance(getattr(self.tournament, item.custom_id), int) else int(item.value) if item.value.isdigit() else getattr(self.tournament, item.custom_id)
                setattr(self.tournament, item.custom_id, value)

        await self.tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Tournament Updated**',
            description=str(self.tournament),
        ), ephemeral=True)


class SubmitResultsSingleView(discord.ui.View):
    def __init__(self, tournament: Tournament, bot: Bot) -> None:
        super().__init__(timeout=300.0)
        self.tournament = tournament
        self.bot = bot

        assert self.tournament.rounds is not None
        matches: list[Match] = [match for round in self.tournament.rounds for match in round if match.winner is None and len(match.teamindices) == 2]
        self.match = discord.ui.Select(
            custom_id='match',
            placeholder='Select a match to submit results for',
            options=[discord.SelectOption(label=match.versus.replace('`', ''), value=f'{match.teamindices[0]}-{match.teamindices[1]}') for match in matches],
            row=0,
        )
        self.match.callback = self.callback
        self.add_item(self.match)
        self.teamindices: Optional[list[int]] = None

    async def callback(self, interaction: discord.Interaction) -> None:
        if self.teamindices is None:
            assert interaction.data is not None
            self.teamindices = list(map(int, self.match.values[0].split('-')))
            self.remove_item(self.match)
            self.winner = discord.ui.Select(
                custom_id='winner',
                placeholder='Select a winner',
                options=[discord.SelectOption(label=f'Team {n}', value=str(n)) for n in self.teamindices],
                row=0,
            )
            self.winner.callback = self.callback
            self.add_item(self.winner)
            return await interaction.response.edit_message(embed=self.bot.embed('Select a winner'), view=self)
        else:
            winner = int(self.winner.values[0])
            assert self.tournament.rounds is not None
            match = [match for round in self.tournament.rounds for match in round if match.teamindices == self.teamindices][0]
            match.winner = winner
            self.tournament.update_rounds()
            await self.tournament.update()
            return await interaction.response.edit_message(embed=self.bot.embed('Result successfully submitted!'), view=None)


class SubmitResultsAllModal(discord.ui.Modal, title='Submit Results'):
    def __init__(self, tournament: Tournament, bot: Bot) -> None:
        super().__init__(timeout=300.0)
        self.tournament = tournament
        self.bot = bot

        self.team1 = discord.ui.TextInput(label='Team 1', custom_id='team1', placeholder='Who played as the first team? (number)', required=True)
        self.team2 = discord.ui.TextInput(label='Team 2', custom_id='team2', placeholder='Who played as the second team? (number)', required=True)
        self.winner = discord.ui.TextInput(label='Winner', custom_id='winner', placeholder='Who won? (number)', required=True)
        for item in (self.team1, self.team2, self.winner):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            team1 = int(self.team1.value)
            team2 = int(self.team2.value)
            winner = int(self.winner.value)
            if winner not in (team1, team2):
                print('aaa')
                raise ValueError
            assert self.tournament.teams is not None
            assert self.tournament.score is not None
            if not all(str(t) in self.tournament.score for t in (team1, team2)):
                raise ValueError
        except ValueError:
            return await interaction.response.send_message(embed=self.bot.embed('Please enter valid team numbers!'), ephemeral=True)
        match = Match(teamindices=[team1, team2], winner=winner)
        assert self.tournament.rounds is not None
        if any(sorted(m.teamindices) == sorted(match.teamindices) for m in self.tournament.rounds[0]):
            return await interaction.response.send_message(embed=self.bot.embed('This match has already been played!'), ephemeral=True)
        self.tournament.rounds[0].append(match)
        self.tournament.score[str(winner)] += 1
        await self.tournament.update()
        return await interaction.response.send_message(embed=self.bot.embed('Result successfully submitted!'), ephemeral=True)


class Command(commands.GroupCog, name='tournament', description='Manage tournaments'):
    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    @app_commands.command(name='create', description='Create a new tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def create(self, interaction: discord.Interaction, name: str) -> None:
        assert interaction.guild is not None
        tournament = Tournament.new(name=name, guild_id=interaction.guild.id, bot=self.bot)
        if str(interaction.guild.id) not in self.bot.tourney_db:
            self.bot.tourney_db[str(interaction.guild.id)] = {}
        await tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Tournament Created**',
            description=str(tournament),
        ), ephemeral=True)

    @app_commands.command(name='config', description='Configure a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def config(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if tournament.published:
                raise ValueError('Tournament is already published.')
        except ValueError as e: return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        return await interaction.response.send_modal(ConfigModal(tournament=tournament, bot=self.bot))

    @app_commands.command(name='publish', description='Publish a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def publish(self, interaction: discord.Interaction, tournament_name: str, channel: Optional[discord.TextChannel] = None) -> None:
        try:
            channel = channel or interaction.channel # type: ignore
            if channel is None:
                raise ValueError('Channel not found?')
            elif interaction.guild is not None:
                tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
                if tournament.published:
                    raise ValueError('Tournament is already published.')
            else:
                raise ValueError('Tournament must be published in a guild.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        tournament.on_publish()
        view = tournament.view
        assert view is not None
        message = await channel.send(embed=tournament.embed, view=view)
        tournament.channel_id, tournament.message_id = message.channel.id, message.id
        await tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Tournament Published**',
            description=f'**[Jump to Message]({message.jump_url})**',
        ), ephemeral=True)

    @app_commands.command(name='start', description='Start a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def start(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if not tournament.published:
                raise ValueError('Tournament is not published yet.')
            elif tournament.started:
                raise ValueError('Tournament has already started.')
        except ValueError as e: return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        tournament.on_start()
        await tournament.update()
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Tournament Started**',
            description='Woo!',
        ), ephemeral=True)

    # @app_commands.command(name='end', description='End a tournament')
    # @app_commands.default_permissions(administrator=True)
    # @commands.has_guild_permissions(administrator=True)
    # async def end(self, interaction: discord.Interaction, tournament_name: str) -> None:
    #     try:
    #         assert interaction.guild is not None
    #         tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
    #         if not tournament.published:
    #             raise ValueError('Tournament is not published yet.')
    #         elif not tournament.started:
    #             raise ValueError('Tournament has not started yet.')
    #     except ValueError as e: return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)

    @app_commands.command(name='delete', description='Delete a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def delete(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        del self.bot.tourney_db[str(tournament.guild_id)][tournament.id]
        self.bot.save_tourney_db()
        if tournament.message_id is not None:
            try:
                assert tournament.channel_id is not None
                channel = self.bot.get_channel(tournament.channel_id)
                assert isinstance(channel, discord.TextChannel)
                message = channel.get_partial_message(tournament.message_id)
                await message.delete()
            except Exception as e:
                return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        return await interaction.response.send_message(embed=self.bot.embed('Successfully deleted tournament.'), ephemeral=True)

    @app_commands.command(name='change_mode', description='Change a tournament\'s mode')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def change_mode(self, interaction: discord.Interaction, tournament_name: str, mode: Mode) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if tournament.published:
                raise ValueError('Tournament is already published.')
            if mode in (Mode.SINGLE_ELIMINATION, Mode.ALL_VS_ALL):
                tournament.mode = mode.value
            else:
                raise ValueError('Invalid mode.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        await tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed('Successfully changed tournament mode.'), ephemeral=True)

    @app_commands.command(name='reopen', description='Reopen a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def reopen(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if not tournament.started:
                raise ValueError('Tournament has not started yet.')
            elif tournament.mode != 2:
                raise ValueError('Tournament is not All vs All mode.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        tournament.rounds = [[]]
        await tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Tournament Reopened**',
            description='Woo!',
        ), ephemeral=True)

    @app_commands.command(name='open_checkin', description='Open check-in for a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def open_checkin(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if not tournament.published:
                raise ValueError('Tournament not published.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        tournament.opened_checkin = True
        await tournament.update()
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Check-in Opened**',
            description='Woo!',
        ), ephemeral=True)

    @app_commands.command(name='kick', description='Kick a player from a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def kick(self, interaction: discord.Interaction, tournament_name: str, player: discord.Member) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if tournament.started:
                raise ValueError('Tournament has already started.')
            await tournament.leave(interaction=None, user_id=player.id)
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Player Kicked**',
            description='Woo!',
        ), ephemeral=True)

    @app_commands.command(name='unkick', description='Unkick a player from a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def unkick(self, interaction: discord.Interaction, tournament_name: str, player: discord.Member) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if tournament.started:
                raise ValueError('Tournament has already started.')
            await tournament.join(interaction=None, user_id=player.id)
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Player Unkicked**',
            description='Woo!',
        ), ephemeral=True)

    @app_commands.command(name='dispute', description='Leave a dispute')
    async def dispute(self, interaction: discord.Interaction) -> None:
        assert interaction.guild is not None
        channel = next((channel for channel in interaction.guild.channels if channel.name == DISPUTE_CHANNEL_NAME), None)
        if channel is None:
            channel = await interaction.guild.create_text_channel(DISPUTE_CHANNEL_NAME)
        assert isinstance(channel, discord.TextChannel)
        modal = discord.ui.Modal(title='Dispute')
        dispute = discord.ui.TextInput(label='Dispute', placeholder='What is your dispute?')
        modal.add_item(dispute)
        async def on_submit(i: discord.Interaction) -> None:
            await channel.send(embed=self.bot.embed(title='Dispute from {0.user} ({0.user.id})'.format(i), description=dispute.value))
            await i.response.send_message(embed=self.bot.embed('Successfully submitted dispute.'), ephemeral=True)
        modal.on_submit = on_submit
        return await interaction.response.send_modal(modal)

    @app_commands.command(name='coinflip', description='Flip a coin')
    async def coinflip(self, interaction: discord.Interaction) -> None:
        return await interaction.response.send_message(embed=self.bot.embed(title=f'{interaction.user} flipped a coin.', description=f'> 🪙 {random.choice(("Heads", "Tails"))}'))

    @app_commands.command(name='submit_result', description='Submit a tournament result')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def submit_result(self, interaction: discord.Interaction, tournament_name: str) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if not tournament.started:
                raise ValueError('Tournament has not started.')
            elif not tournament.admin_submit:
                raise ValueError('Tournament does not allow admins to submit results.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        if tournament.mode == 1:
            view = SubmitResultsSingleView(tournament=tournament, bot=self.bot)
            return await interaction.response.send_message(embed=self.bot.embed('Which match is played?'), view=view)
        elif tournament.mode == 2:
            modal = SubmitResultsAllModal(tournament=tournament, bot=self.bot)
            return await interaction.response.send_modal(modal)


    @app_commands.command(name='change_submission_mode', description='Change the submission mode of a tournament')
    @app_commands.default_permissions(administrator=True)
    @commands.has_guild_permissions(administrator=True)
    async def change_submission_mode(self, interaction: discord.Interaction, tournament_name: str, admins_submit_results: bool) -> None:
        try:
            assert interaction.guild is not None
            tournament = Tournament.from_any(value=tournament_name, guild_id=interaction.guild.id, bot=self.bot)
            if tournament.published:
                raise ValueError('Tournament is published.')
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        tournament.admin_submit = admins_submit_results
        await tournament.update(send=False)
        return await interaction.response.send_message(embed=self.bot.embed(
            title='**Submission Mode Changed**',
            description='Woo!',
        ), ephemeral=True)

    @config.autocomplete('tournament_name')
    @publish.autocomplete('tournament_name')
    @start.autocomplete('tournament_name')
    # @end.autocomplete('tournament_name')
    @delete.autocomplete('tournament_name')
    @change_mode.autocomplete('tournament_name')
    @reopen.autocomplete('tournament_name')
    @open_checkin.autocomplete('tournament_name')
    @kick.autocomplete('tournament_name')
    @unkick.autocomplete('tournament_name')
    @submit_result.autocomplete('tournament_name')
    async def tournament_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice]:
        try:
            assert interaction.guild is not None
            found: list[app_commands.Choice] = []
            for data in self.bot.tourney_db.get(str(interaction.guild.id), {}).values():
                if current in data.get('name'): found.insert(0, app_commands.Choice(name=data.get('name'), value=data.get('id')))
                # if current in data.get('id'): found.append(app_commands.Choice(name=data.get('id')+' (ID)', value=data.get('id')))
            if len(found) == 0: raise ValueError

        except (ValueError, AttributeError):
            return [app_commands.Choice(name='No tournaments found..', value='-1')]
        return found[:25]

    async def on_button_click(self, interaction: discord.Interaction) -> None:
        assert interaction.data is not None
        assert interaction.guild is not None
        if interaction.data.get('custom_id', '').startswith('handled_'): return
        tournament_id = interaction.data.get('custom_id').split(':')[0] # type: ignore
        tournament = Tournament.from_id(id=tournament_id, guild_id=interaction.guild.id, bot=self.bot)
        assert tournament.published, 'Tournament is not published yet. (How did you even click this button?)'
        action = interaction.data.get('custom_id').split(':')[-1] # type: ignore
        async def defer(interaction: discord.Interaction) -> None:
            return await interaction.response.send_message(embed=self.bot.embed(f'Unknown action `{action}`.'), ephemeral=True)
        return await getattr(tournament, action, defer)(interaction=interaction)

    @commands.Cog.listener('on_interaction')
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        assert interaction.data is not None
        if interaction.type != discord.InteractionType.component or interaction.data.get('component_type') != 2: return
        """Button clicked from here on out."""
        try:
            return await self.on_button_click(interaction=interaction)
        except ValueError as e:
            return await interaction.response.send_message(embed=self.bot.embed(str(e)), ephemeral=True)
        except Exception as e:
            raise e


async def setup(bot: Bot) -> None:
    await bot.add_cog(Command(bot))
