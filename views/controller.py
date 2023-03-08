"""MIT License

Copyright (c) 2023 Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import discord
import function as func

from discord.ext import commands
from . import ButtonOnCooldown
from function import (
    get_playlist,
    update_playlist,
    create_account,
    checkroles,
)
from typing import Dict

def key(interaction: discord.Interaction):
    return interaction.user
    
class Back(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="⏮️", label=player.get_msg('buttonBack'), style=style, disabled=False if self.player.queue.history() or not self.player.current else True, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            if interaction.user in self.player.previous_votes:
                return await interaction.response.send_message(self.player.get_msg("voted"), ephemeral=True)
            else:
                self.player.previous_votes.add(interaction.user)
                if len(self.player.previous_votes) >= (required := self.player.required()):
                    pass
                else:
                    return await interaction.response.send_message(self.player.get_msg("backVote").format(interaction.user, len(self.player.previous_votes), required))

        if not self.player.is_playing:
            self.player.queue.backto(1)
            await self.player.do_next()
        else:
            self.player.queue.backto(2)
            await self.player.stop()

        await interaction.response.send_message(self.player.get_msg("backed").format(interaction.user))

        if self.player.queue._repeat == 1:
            self.player.queue.set_repeat("off")
        
class Resume(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="⏸️", label=player.get_msg('buttonPause'), style=style, disabled=False if self.player.current else True, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if self.player.is_paused:
            if not await self.player.is_privileged(interaction.user):
                if interaction.user in self.player.resume_votes:
                    return await interaction.response.send_message(self.player.get_msg("voted"), ephemeral=True)
                else:
                    self.player.resume_votes.add(interaction.user)
                    if len(self.player.resume_votes) >= (required := self.player.required()):
                        pass
                    else:
                        return await interaction.response.send_message(self.player.get_msg("resumeVote").format(interaction.user, len(self.player.resume_votes), required))

            self.player.resume_votes.clear()
            self.emoji = "⏸️"
            self.label = self.player.get_msg("buttonPause")
            await self.player.set_pause(False)
        
        else:
            if not await self.player.is_privileged(interaction.user):
                if interaction.user in self.player.pause_votes:
                    return await interaction.response.send_message(self.player.get_msg("voted"), ephemeral=True)
                else:
                    self.player.pause_votes.add(interaction.user)
                    if len(self.player.pause_votes) >= (required := self.player.required()):
                        pass
                    else:
                        return await interaction.response.send_message(self.player.get_msg("pauseVote").format(interaction.user, len(self.player.pause_votes), required))

            self.player.pause_votes.clear()
            self.emoji = "▶️"
            self.label = self.player.get_msg("buttonResume")
            await self.player.set_pause(True)  
        await interaction.response.edit_message(view=self.view)

class Skip(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="⏭️", label=player.get_msg('buttonSkip'), style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not self.player.is_playing:
            return 
        if not await self.player.is_privileged(interaction.user):
            if interaction.user == self.player.current.requester:
                pass 
            elif interaction.user in self.player.skip_votes:
                return await interaction.response.send_message(self.player.get_msg("voted"), ephemeral=True)
            else:
                self.player.skip_votes.add(interaction.user)
                if len(self.player.skip_votes) >= (required := self.player.required()):
                    pass
                else:
                    return await interaction.response.send_message(self.player.get_msg("skipVote").format(interaction.user, len(self.player.skip_votes), required))

        await interaction.response.send_message(self.player.get_msg("skipped").format(interaction.user))

        if self.player.queue._repeat == 1:
            self.player.queue.set_repeat("off")
        await self.player.stop()

class Stop(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="⏹️", label=player.get_msg('buttonLeave'), style=style, row=row)
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            if interaction.user in self.player.stop_votes:
                return await interaction.response.send_message(self.player.get_msg("voted"), ephemeral=True)
            else:
                self.player.stop_votes.add(interaction.user)
                if len(self.player.stop_votes) >= (required := self.player.required(leave=True)):
                    pass
                else:
                    return await interaction.response.send_message(self.player.get_msg("leaveVote").format(interaction.user, len(self.player.stop_votes), required))
        
        await interaction.response.send_message(self.player.get_msg("left").format(interaction.user))
        await self.player.teardown()

class Add(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="❤️", style=style, disabled=False if self.player.current else True, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        track = self.player.current
        if not track:
            return await interaction.response.send_message(self.player.get_msg("noTrackPlaying"))
        if track.is_stream:
            return await interaction.response.send_message(self.player.get_msg("playlistAddError"))
        user = await get_playlist(interaction.user.id, 'playlist')
        if not user:
            return await create_account(interaction)
        rank, max_p, max_t = await checkroles(interaction.user.id)
        if len(user['200']['tracks']) >= max_t:
            return await interaction.response.send_message(self.player.get_msg("playlistlimited").format(max_t), ephemeral=True)
        addtrack = {'id': track.track_id, 
                    'info':{'identifier': track.identifier,
                            'author': track.author,
                            'length': track.length / 1000,
                            'title': track.title,
                            'uri': track.uri}}
        if addtrack in user['200']['tracks']:
            return await interaction.response.send_message(self.player.get_msg("playlistrepeated"), ephemeral=True)
        respond = await update_playlist(interaction.user.id, {'playlist.200.tracks': addtrack}, push=True)
        if respond:
            await interaction.response.send_message(self.player.get_msg("playlistAdded").format(track.title, interaction.user.mention, user['200']['name']), ephemeral=True)
        else:
            await interaction.response.send_message(self.player.get_msg("playlistAddError2"), ephemeral=True)

class Loop(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        self.loopType = {
            0: "off",
            1: "track",
            2: "queue",
        }
        super().__init__(emoji="🔁", label=player.get_msg('buttonLoop'), style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            return await interaction.response.send_message(self.player.get_msg('missingPerms_mode'), ephemeral=True)

        current_repeat = self.player.queue._repeat
        mode = self.loopType.get((current_repeat + 1)%len(self.loopType), 'off')
        self.player.queue.set_repeat(mode)
        await interaction.response.send_message(self.player.get_msg('repeat').format(mode.capitalize()))

class VolumeUp(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="🔊", label=player.get_msg('buttonVolumeUp'), style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            return interaction.response.send_message(self.player.get_msg("missingPerms_function"))

        value = value if (value := self.player.volume + 20) <= 150 else 150
        await self.player.set_volume(value)

        await interaction.response.send_message(self.player.get_msg('setVolume').format(value), ephemeral=True)

class VolumeDown(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="🔉", label=player.get_msg('buttonVolumeDown'), style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            return interaction.response.send_message(self.player.get_msg("missingPerms_function"))

        value = value if (value := self.player.volume - 20) >= 0 else 150
        await self.player.set_volume(value)

        await interaction.response.send_message(self.player.get_msg('setVolume').format(value), ephemeral=True)

class VolumeMute(discord.ui.Button):
    def __init__(self, player, style, row):
        self.player = player
        super().__init__(emoji="🔇" if player.volume else "🔈",
                         label=player.get_msg('buttonVolumeMute' if player.volume else "buttonVolumeUnmute"),
                         style=style, row=row)
    
    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            return interaction.response.send_message(self.player.get_msg("missingPerms_function"))

        if self.player.volume != 0:
            value = 0
            self.emoji = "🔈"
            self.label = self.player.get_msg("buttonVolumeUnmute")
        else:
            value = self.player.settings.get("volume", 100)
            self.emoji = "🔇"
            self.label = self.player.get_msg("buttonVolumeMute")

        await self.player.set_volume(value)

        await interaction.response.edit_message(view=self.view)

class Tracks(discord.ui.Select):
    def __init__(self, player, style, row):

        self.player = player
        
        options = []
        for index, track in enumerate(self.player.queue.tracks(), start=1):
            if index > 10:
                break
            options.append(discord.SelectOption(label=f"{index}. {track.title[:40]}", description=f"{track.author[:30]} · " + ("Live" if track.is_stream else track.formatLength), emoji=track.emoji))

        super().__init__(
            placeholder=player.get_msg("playerDropdown"),
            min_values=1, max_values=1,
            options=options,
            row=row
        )

    async def callback(self, interaction: discord.Interaction):
        if not await self.player.is_privileged(interaction.user):
            return await interaction.response.send_message(self.player.get_msg("missingPerms_function"), ephemeral=True)
        
        self.player.queue.skipto(int(self.values[0].split(". ")[0]))
        await self.player.stop()
        await interaction.response.send_message(self.player.get_msg("skipped").format(interaction.user))

btnType = {
    "back": Back,
    "resume": Resume,
    "skip": Skip,
    "stop": Stop,
    "add": Add,
    "loop": Loop,
    "volumeup": VolumeUp,
    "volumedown": VolumeDown,
    "volumemute": VolumeMute,
    "tracks": Tracks
}

btnColor = {
    "blue": discord.ButtonStyle.primary,
    "grey": discord.ButtonStyle.secondary,
    "red": discord.ButtonStyle.danger,
    "green": discord.ButtonStyle.success
}

class InteractiveController(discord.ui.View):
    def __init__(self, player):
        super().__init__(timeout=None)

        self.player = player
        for row, btnRow in enumerate(func.controller_settings):
            for btn in btnRow:
                color = ""
                if isinstance(btn, Dict):
                    color = list(btn.values())[0]
                    btn = list(btn.keys())[0]
                btnClass = btnType.get(btn.lower())
                style = btnColor.get(color.lower(), btnColor["grey"])
                if not btnClass or (self.player.queue.is_empty and btn == "tracks"):
                    continue
                self.add_item(btnClass(player, style, row))

        self.cooldown = commands.CooldownMapping.from_cooldown(2.0, 10.0, key)
            
    async def interaction_check(self, interaction):
        if not self.player.node._available:
            await interaction.response.send_message(self.player.get_msg("nodeReconnect"), ephemeral=True)
            return False

        if interaction.user.id in func.bot_access_user:
            return True
            
        if self.player.channel and interaction.user in self.player.channel.members:
            retry_after = self.cooldown.update_rate_limit(interaction)
            if retry_after:
                raise ButtonOnCooldown(retry_after)
            return True
        else:
            await interaction.response.send_message(self.player.get_msg("notInChannel").format(interaction.user.mention, self.player.channel.mention), ephemeral=True)
            return False

    async def on_error(self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item):
        if isinstance(error, ButtonOnCooldown):
            try:
                sec = int(error.retry_after)
                await interaction.response.send_message(f"You're on cooldown for {sec} second{'' if sec == 1 else 's'}!", ephemeral=True)
            except:
                return
        return