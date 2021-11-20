import logging
from typing import Literal, Optional, Union
import copy

import re

import contextlib
from datetime import datetime as dt, timezone, timedelta
from dateutil.relativedelta import relativedelta

import discord
from redbot import VersionInfo, version_info
from redbot.core import Config, VersionInfo, checks, commands, version_info
from redbot.core.utils.chat_formatting import humanize_list, pagify
from redbot.core.utils.menus import start_adding_reactions
from redbot.core.utils.predicates import ReactionPredicate

# from .helpers import (
#     get_event_embed,
#     create_event_reactions,
#     valid_image,
#     get_mentionable_role,
#     get_role_mention
# )

import asyncio

log = logging.getLogger("red.burnacid.eventboard")

class Tournament(commands.Cog):
    """Create a category with text and voice channels for tournaments"""

    __version__ = "0.0.1"
    __author__ = "Burnacid"

    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier=144014746356671234)
        default_guild = {
            "tournaments": {},
            "autoclean": 24,
            "group": -1
        }
        default_user = {"player_class": ""}
        self.config.register_guild(**default_guild)
        self.config.register_member(**default_user)

        self.tournament_init_task = self.bot.loop.create_task(self.initialize())

    def cog_unload(self):
        self.event_init_task.cancel()
        self.event_maintenance.cancel()

    async def initialize(self) -> None:
        CHECK_DELAY = 300
        while self == self.bot.get_cog("Tournament"):
            log.debug("Running Tournament Init")
            if version_info >= VersionInfo.from_str("3.2.0"):
                await self.bot.wait_until_red_ready()
            else:
                await self.bot.wait_until_ready()
            try:
                pass
            except Exception as e:
                log.error("Error loading events", exc_info=e)

            log.debug("Ended Event Init")
            await asyncio.sleep(CHECK_DELAY)

    async def is_mod_or_admin(self, member: discord.Member) -> bool:
        guild = member.guild
        if member == guild.owner:
            return True
        if await self.bot.is_owner(member):
            return True
        if await self.bot.is_admin(member):
            return True
        if await self.bot.is_mod(member):
            return True
        return False
    
    @commands.group(name="tournament")
    @commands.guild_only()
    async def tournament(self, ctx: commands.Context):
        """Tournament allows you to create the a category with voice and text channels for max 24 hours"""
        pass

    @tournament.command(name="start")
    @commands.guild_only()
    async def tournament_start(self, ctx: commands.Context, name: str, numberofchannels: str, slots: str = 0):
        """Start a tournament"""

        await ctx.message.delete(delay=60)

        try:
            if not isinstance(int(numberofchannels), int):
                await ctx.send("Number of Channels is not a number. Please try again.",delete_after=60)
                return
        except:
            await ctx.send("Number of Channels is not a number. Please try again.",delete_after=60)
            return

        try:
            if not isinstance(int(slots), int):
                await ctx.send("Slots is not a number. Please try again.",delete_after=60)
                return
        except:
            await ctx.send("Slots is not a number. Please try again.",delete_after=60)
            return

        author = ctx.author
        guild = ctx.guild

        # Get creation time
        creation_time = ctx.message.created_at
        if creation_time.tzinfo is None:
            creation_time = creation_time.replace(tzinfo=timezone.utc).timestamp()
        else:
            creation_time = creation_time.timestamp()

        # Create Tournament Category
        category = await ctx.guild.create_category("Tournament: "+ name)
        groupid = await self.config.guild(ctx.guild).group()
        group = ctx.guild.get_role(groupid)

        if groupid == ctx.guild.default_role.id or int(groupid) == -1:
            await category.set_permissions(ctx.guild.default_role, read_messages=True, send_messages=True, connect=True, speak=True)
        else:
            await category.set_permissions(group, read_messages=True, send_messages=True, connect=True, speak=True)
            await category.set_permissions(ctx.guild.default_role, read_messages=False, connect=False)

        # Create default text en voice lobby
        channels = {}
        defaultText = await ctx.guild.create_text_channel("tournament-chat", category=category)
        channels['chat'] =  defaultText.id
        defaultVoice = await ctx.guild.create_voice_channel("Tournament Lobby", category=category)
        channels['lobby'] = defaultVoice.id

        # Create voice channels
        for x in range(int(numberofchannels)):
            if slots == 0:
                chan = await ctx.guild.create_voice_channel(f"Table #{x+1}", category=category)
            else:
                chan = await ctx.guild.create_voice_channel(f"Table #{x+1}", category=category, user_limit=int(slots))
            
            channels[x+1] = chan.id            

        new_tournament = {
            "id": category.id,
            "creator": author.id,
            "create_time": creation_time,
            "name": name.lower(),
            "slots": slots,
            "channels": channels
        }

        async with self.config.guild(guild).tournaments() as tournaments_list:
            tournaments_list[category.id] = new_tournament

        pass

    @tournament.command(name="stop")
    @commands.guild_only()
    async def tournament_stop(self, ctx: commands.Context, name: str):
        """Stop a tournament"""

        await ctx.message.delete(delay=10)

        async with self.config.guild(ctx.guild).tournaments() as tournaments_list:
            for k in list(tournaments_list):
                if tournaments_list[k]['name'] == name.lower():
                    # Delete channels
                    try:
                        for key in list(tournaments_list[k]['channels'].keys()):
                            try:
                                channel = ctx.guild.get_channel(tournaments_list[k]['channels'][key])
                                await channel.delete()
                            except:
                                pass
                    except:
                        pass
                    
                    # Force delete channels in category
                    category = ctx.guild.get_channel(tournaments_list[k]['id'])
                    try:
                        channels = category.channels
                        for ch in channels:
                            try:
                                await ch.delete()
                            except:
                                 pass
                    except:
                        pass
                    
                    try:
                        await category.delete()
                    except:
                        pass

                    # Delete from settings
                    del tournaments_list[k]

    @tournament.command(name="addchannel")
    @commands.guild_only()
    async def tournament_addchannel(self, ctx: commands.Context, count: int = 1):
        """Add voice channels"""

        await ctx.message.delete(delay=10)

        category = ctx.channel.category

        async with self.config.guild(ctx.guild).tournaments() as tournaments_list:
            if str(category.id) not in tournaments_list:
                await ctx.channel.send("This is not a tournament channel. Please use this command only in the lobby of the tournament!", delete_after=60)
                return
            
            t = tournaments_list[str(category.id)]
            numberChannels = len(t['channels']) - 2

            for x in range(int(count)):
                if t['slots'] == 0:
                    chan = await ctx.guild.create_voice_channel(f"Table #{x+1+numberChannels}", category=category)
                else:
                    chan = await ctx.guild.create_voice_channel(f"Table #{x+1+numberChannels}", category=category, user_limit=int(t['slots']))

                t['channels'][x+1+numberChannels] = chan.id

    @tournament.command(name="deletechannel")
    @commands.guild_only()
    async def tournament_deletechannel(self, ctx: commands.Context, count: int = 1):
        """Delete voice channels"""

        await ctx.message.delete(delay=10)

        category = ctx.channel.category

        async with self.config.guild(ctx.guild).tournaments() as tournaments_list:
            if str(category.id) not in tournaments_list:
                await ctx.channel.send("This is not a tournament channel. Please use this command only in the lobby of the tournament!", delete_after=60)
                return

            t = tournaments_list[str(category.id)]
            numberChannels = len(t['channels']) - 2
            if numberChannels < count:
                count = numberChannels

            channels = t['channels'].copy()

            numkeys = len(channels) - 2

            for x in range(int(count)):
                key = numkeys - x

                channel = ctx.guild.get_channel(channels[str(key)])
                
                del channels[str(key)]
                await channel.delete()
            
            t['channels'] = channels

            

    @commands.group(name="tournamentset")
    @commands.guild_only()
    async def tournament_settings(self, ctx: commands.Context) -> None:
        """Manage server specific settings for tournaments"""
        pass

    @tournament_settings.command(name="group")
    @commands.guild_only()
    async def set_group(self, ctx: commands.Context, role: discord.Role):
        """
        Assign specific group to have permissions

        `{role}` the group name or id of the group that gets default view permissions. Use @everyone to set visible to everyone
        """

        await self.config.guild(ctx.guild).group.set(role.id)
        await ctx.message.delete(delay=60)
        await ctx.channel.send(f"Tournaments are now only visible for {role.name}", delete_after=60)

    @tournament_settings.command(name="autoclean")
    @commands.guild_only()
    async def set_guild_autodelete(self, ctx: commands.Context, *, hours: int):
        """
        Set how long after creation the tournament will be deleted

        `{hours}` the number of minutes after which the eventpost is removed after the start time. Set to -1 to disable removal of the events
        """

        await self.config.guild(ctx.guild).autoclean.set(int(hours))
        await ctx.message.delete(delay=60)
        if hours < 0:
            await ctx.channel.send("Auto delete tournament is disabled", delete_after=60)
        else:
            await ctx.channel.send(f"Tournaments will now be deleted {hours} hours after they are created", delete_after=60)