import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import os
from flask import Flask
from threading import Thread
import asyncio
import sys

# 🌐 Flask 앱으로 Render 24/7 대응
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ 봇이 실행 중입니다."

def run_web():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

Thread(target=run_web).start()

# ⏱️ 1시간마다 자동 재시작
async def auto_restart(interval_sec=3600):
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(interval_sec)
        print(f"[🔁 자동 재시작] {interval_sec}초 경과. 봇 재시작 시도.")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"[❌ 재시작 실패] {e}")
            sys.exit()

# 봇 클래스
class CustomBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(auto_restart(3600))  # 1시간마다 재시작

intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = CustomBot(command_prefix="!", intents=intents, help_command=None)
now_playing = {}

# 봇 준비 이벤트
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.listening, name="/검색")
    await bot.change_presence(activity=activity)
    print(f"{bot.user} 준비 완료.")
    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)}개의 슬래시 명령어 동기화됨.")
    except Exception as e:
        print(f"[슬래시 명령어 동기화 실패]: {e}")

# 🔊 노래 재생 함수
async def play_song(interaction: discord.Interaction, url: str):
    try:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("먼저 음성 채널에 접속해 주세요!", ephemeral=True)
            return

        voice_client = interaction.guild.voice_client
        channel = interaction.user.voice.channel

        if not voice_client:
            voice_client = await channel.connect()
        elif voice_client.channel != channel:
            await voice_client.move_to(channel)

        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'nocheckcertificate': True,
            'default_search': 'auto',
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
        }

        ffmpeg_opts = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': '-vn',
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_url = info['url']
            title = info.get('title', '알 수 없는 제목')

        ffmpeg_path = "/nix/store/3zc5jbvqzrn8zmva4fx5p0nh4yy03wk4-ffmpeg-6.1.1-bin/bin/ffmpeg"

        source = discord.FFmpegOpusAudio(audio_url, executable=ffmpeg_path, **ffmpeg_opts)

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(source)
        now_playing[interaction.guild.id] = title
        await interaction.followup.send(f"🎶 **{title}** 재생 중!")

    except Exception as e:
        print(f"[재생 오류]: {type(e).__name__} - {e}")
        await interaction.followup.send(f"❌ 오류 발생:\n```{type(e).__name__}: {e}```", ephemeral=True)

# 🔍 검색 명령어
@bot.tree.command(name="검색", description="노래를 검색해 재생합니다.")
@app_commands.describe(query="검색할 노래 제목")
async def search(interaction: discord.Interaction, query: str):
    await interaction.response.defer(ephemeral=True, thinking=True)

    try:
        ydl_opts = {
            'quiet': True,
            'format': 'bestaudio/best',
            'default_search': 'ytsearch5',
            'nocheckcertificate': True,
            'skip_download': True,
            'no_warnings': True,
            'http_headers': {'User-Agent': 'Mozilla/5.0'},
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(query, download=False)
            videos = info.get('entries', [])
            videos = [v for v in videos if not v.get('is_unavailable') and 'webpage_url' in v]

            if not videos:
                await interaction.followup.send("❌ 재생 가능한 영상이 없습니다.", ephemeral=True)
                return

        class SongSelect(discord.ui.Select):
            def __init__(self, videos):
                options = [
                    discord.SelectOption(
                        label=f"{i+1}. {video.get('title')[:95]}",
                        value=video['webpage_url'],
                        description=f"{video.get('duration_string', '길이 정보 없음')}"
                    )
                    for i, video in enumerate(videos[:5])
                ]
                super().__init__(placeholder="노래를 선택하세요!", options=options)

            async def callback(self, interaction2: discord.Interaction):
                await interaction2.response.defer()
                await play_song(interaction2, self.values[0])

        view = discord.ui.View(timeout=60)
        view.add_item(SongSelect(videos))

        embed = discord.Embed(title=f"🔍 '{query}' 검색 결과", color=0x1DB954)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except Exception as e:
        print(f"[검색 오류]: {type(e).__name__} - {e}")
        await interaction.followup.send(f"오류 발생:\n```{type(e).__name__}: {e}```", ephemeral=True)

# ⏹️ 정지 명령어
@bot.tree.command(name="정지", description="노래 정지 및 퇴장")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        if voice_client.is_playing():
            voice_client.stop()
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ 정지하고 퇴장했어요.")
    else:
        await interaction.response.send_message("❌ 음성 채널에 있지 않습니다.", ephemeral=True)

# ⏭️ 스킵 명령어
@bot.tree.command(name="스킵", description="현재 노래를 건너뜁니다.")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ 다음 곡으로 넘어갑니다.")
    else:
        await interaction.response.send_message("❌ 현재 재생 중인 노래가 없습니다.", ephemeral=True)

# 👤 음성 채널에서 혼자 남으면 자동 퇴장
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    if voice_client and voice_client.channel and len(voice_client.channel.members) == 1:
        await voice_client.disconnect()

# ▶️ 실행
def run_bot():
    token = os.getenv("TOKEN")
    if not token:
        print("❌ TOKEN 환경변수가 설정되지 않았습니다.")
        return
    bot.run(token)

if __name__ == "__main__":
    Thread(target=run_web).start()
    run_bot()
