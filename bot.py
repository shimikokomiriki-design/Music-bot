import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
from collections import deque
import asyncio
import shutil

TOKEN = os.getenv("DISCORD_TOKEN")

# Detect FFmpeg (Linux / Render)
FFMPEG_PATH = shutil.which("ffmpeg")
if not FFMPEG_PATH:
    raise RuntimeError("❌ FFmpeg not found! Make sure ffmpeg is installed.")

SONG_QUEUES = {}
VOLUME = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ {bot.user} is online and ready!")

async def play_next(interaction, guild_id):
    if not SONG_QUEUES[guild_id]:
        vc = interaction.guild.voice_client
        if vc:
            await vc.disconnect()
        return

    audio_url, title, webpage_url = SONG_QUEUES[guild_id].popleft()
    ffmpeg_opts = {
        "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
        "options": "-vn"
    }

    vc = interaction.guild.voice_client
    source = discord.FFmpegPCMAudio(
        audio_url,
        executable=FFMPEG_PATH,
        **ffmpeg_opts
    )

    vol = VOLUME.get(str(interaction.guild.id), 0.5)
    vc.play(
        source,
        after=lambda e: asyncio.run_coroutine_threadsafe(
            play_next(interaction, guild_id),
            bot.loop
        )
    )
    vc.source = discord.PCMVolumeTransformer(vc.source, volume=vol)

    embed = discord.Embed(
        title="🎵 Now Playing",
        description=f"[{title}]({webpage_url})",
        color=0x1DB954
    )
    await interaction.channel.send(embed=embed)

@bot.tree.command(name="play", description="Play a song or add to queue")
@app_commands.describe(query="Song name or YouTube URL")
async def play(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send("❌ You must be in a voice channel.")

    voice_channel = interaction.user.voice.channel
    vc = interaction.guild.voice_client

    if not vc:
        vc = await voice_channel.connect()
    elif vc.channel != voice_channel:
        await vc.move_to(voice_channel)

    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "default_search": "auto"
    }

    try:
        if query.startswith("http"):
            info = _extract(query, ydl_opts)
        else:
            info = await search_ytdlp_async(f"ytsearch1:{query}", ydl_opts)
            if "entries" in info:
                info = info["entries"][0]
    except Exception as e:
        return await interaction.followup.send(f"❌ YouTubeDL Error: {e}")

    if not info or "url" not in info:
        return await interaction.followup.send("❌ No results found.")

    audio_url = info["url"]
    title = info.get("title", "Unknown Title")
    webpage_url = info.get("webpage_url", query)

    guild_id = str(interaction.guild.id)
    SONG_QUEUES.setdefault(guild_id, deque()).append(
        (audio_url, title, webpage_url)
    )

    if vc.is_playing() or vc.is_paused():
        await interaction.followup.send(f"➕ Added to queue: **{title}**")
    else:
        await interaction.followup.send(f"▶️ Now playing: **{title}**")
        await play_next(interaction, guild_id)

@bot.tree.command(name="skip", description="Skip current song")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
        await interaction.response.send_message("⏭ Skipped.")
    else:
        await interaction.response.send_message("❌ Nothing to skip.")

@bot.tree.command(name="stop", description="Stop playback and clear queue")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    guild_id = str(interaction.guild.id)
    SONG_QUEUES.pop(guild_id, None)

    if vc:
        if vc.is_playing() or vc.is_paused():
            vc.stop()
        await vc.disconnect()

    await interaction.response.send_message("⏹ Stopped.")

@bot.tree.command(name="volume", description="Set volume (1-200%)")
async def volume(interaction: discord.Interaction, level: int):
    if level < 1 or level > 200:
        return await interaction.response.send_message("❌ 1–200 only.")

    vol = level / 100
    VOLUME[str(interaction.guild.id)] = vol

    vc = interaction.guild.voice_client
    if vc and vc.source:
        vc.source.volume = vol

    await interaction.response.send_message(f"🔊 Volume set to {level}%")

@bot.tree.command(name="ping", description="Show bot latency")
async def ping(interaction: discord.Interaction):
    latency = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 {latency}ms")

bot.run(TOKEN)

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
