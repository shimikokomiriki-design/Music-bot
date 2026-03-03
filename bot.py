import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
from collections import deque
import asyncio
import shutil

TOKEN = os.getenv("DISCORD_TOKEN")

FFMPEG_PATH = shutil.which("ffmpeg")
if not FFMPEG_PATH:
    raise RuntimeError("❌ FFmpeg not found!")

SONG_QUEUES = {}
VOLUME = {}
LOOP_MODE = {}

def format_duration(seconds):
    if not seconds:
        return "Unknown"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02}:{s:02}"
    return f"{m}:{s:02}"

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} online!")

# ================== CONTROL BUTTONS ==================

class MusicControls(discord.ui.View):
    def __init__(self, interaction):
        super().__init__(timeout=None)
        self.interaction = interaction

    @discord.ui.button(label="⏸ Pause", style=discord.ButtonStyle.secondary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_playing():
            vc.pause()
            await interaction.response.send_message("⏸ Paused", ephemeral=True)

    @discord.ui.button(label="▶ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc and vc.is_paused():
            vc.resume()
            await interaction.response.send_message("▶ Resumed", ephemeral=True)

    @discord.ui.button(label="⏭ Skip", style=discord.ButtonStyle.primary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            vc.stop()
            await interaction.response.send_message("⏭ Skipped", ephemeral=True)

    @discord.ui.button(label="⏹ Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
        await interaction.response.send_message("⏹ Stopped", ephemeral=True)

# ================== PLAYER ==================

async def play_next(interaction, guild_id):
    if not SONG_QUEUES[guild_id]:
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
        return

    song = SONG_QUEUES[guild_id].popleft()
    audio_url, title, webpage_url, thumbnail, requester, duration = song

    vc = interaction.guild.voice_client

    if LOOP_MODE.get(guild_id):
        SONG_QUEUES[guild_id].appendleft(song)

    source = discord.FFmpegPCMAudio(audio_url, executable=FFMPEG_PATH)
    vc.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(interaction, guild_id), bot.loop
        )
    )

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"[{title}]({webpage_url})",
        color=0xff69b4
    )

    embed.add_field(name="⏱ Duration", value=format_duration(duration))
    embed.add_field(name="👤 Requested by", value=requester.mention)
    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    view = MusicControls(interaction)
    await interaction.channel.send(embed=embed, view=view)

# ================== PLAY COMMAND ==================

@bot.tree.command(name="play", description="Play a song")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send("❌ Join voice channel first.")

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if not vc:
        vc = await voice_channel.connect(reconnect=True)

    # 🔥 ปรับ yt-dlp ให้เสถียรกว่า
    ydl_opts = {
        "format": "bestaudio/best",
        "quiet": True,
        "noplaylist": True,
        "default_search": "ytsearch",
        "source_address": "0.0.0.0"
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # 🔥 บังคับใช้ ytsearch ลดโอกาสโดนบล็อก
            info = ydl.extract_info(f"ytsearch:{query}", download=False)

            if "entries" in info and info["entries"]:
                info = info["entries"][0]
            else:
                return await interaction.followup.send("❌ No results found.")

    except Exception as e:
        return await interaction.followup.send(f"❌ Error: {str(e)}")

    audio_url = info.get("url")
    title = info.get("title", "Unknown Title")
    webpage_url = info.get("webpage_url")
    thumbnail = info.get("thumbnail")
    duration = info.get("duration")

    guild_id = str(interaction.guild.id)
    SONG_QUEUES.setdefault(guild_id, deque()).append(
        (audio_url, title, webpage_url, thumbnail, interaction.user, duration)
    )

    embed = discord.Embed(
        title="🎶 Added to Queue",
        description=f"[{title}]({webpage_url})" if webpage_url else title,
        color=0xff69b4
    )

    embed.add_field(name="⏱ Duration", value=format_duration(duration))
    embed.add_field(name="👤 Requested by", value=interaction.user.mention)

    if thumbnail:
        embed.set_thumbnail(url=thumbnail)

    await interaction.followup.send(embed=embed)

    if not vc.is_playing():
        await play_next(interaction, guild_id)

# ================== LOOP ==================

@bot.tree.command(name="loop", description="Toggle loop mode")
async def loop(interaction: discord.Interaction):
    guild_id = str(interaction.guild.id)
    LOOP_MODE[guild_id] = not LOOP_MODE.get(guild_id, False)
    status = "ON 🔁" if LOOP_MODE[guild_id] else "OFF"
    await interaction.response.send_message(f"Loop mode: {status}")

# ================== PING ==================

@bot.tree.command(name="ping")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    embed = discord.Embed(
        title="💗 Shimaru Ping",
        description=f"Latency: **{latency}ms**",
        color=0xff69b4
    )
    await interaction.response.send_message(embed=embed)

from flask import Flask
import threading
import os

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

threading.Thread(target=run_web).start()


bot.run(TOKEN)

