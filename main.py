import discord
from discord import app_commands
from discord.ext import commands
import yt_dlp
import os
from flask import Flask
from threading import Thread
import asyncio
import sys

# ================== 24/7 Flask 서버 설정 ==================
app = Flask(__name__)

@app.route('/')
def home():
    return "24/7 uptime server is running."

def run_web():
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

# 아래 코드로 백그라운드에서 Flask 서버 실행
Thread(target=run_web).start()

# ================== 자동 재시작 함수 ==================
async def auto_restart(interval_sec=3600):
    await bot.wait_until_ready()
    while not bot.is_closed():
        await asyncio.sleep(interval_sec)
        print(f"[자동 재시작] {interval_sec}초 경과, 봇 재시작 시도...")
        try:
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            print(f"[자동 재시작 실패] {e}")
            sys.exit()

# ================== 커스텀 봇 클래스 ==================
class CustomBot(commands.Bot):
    async def setup_hook(self):
        self.loop.create_task(auto_restart(3600))  # 1시간마다 재시작

# ================== 디스코드 봇 설정 ==================
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = CustomBot(command_prefix="!", intents=intents, help_command=None)
now_playing = {}

# ================== 봇 준비 이벤트 ==================
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.listening, name="/검색")
    await bot.change_presence(activity=activity)
    print(f"{bot.user} 봇이 준비되었습니다!")

    try:
        synced = await bot.tree.sync()
        print(f"{len(synced)}개의 슬래시 커맨드가 동기화되었습니다.")
    except Exception as e:
        print(f"슬래시 커맨드 동기화 에러: {e}")

# ================== 노래 재생 함수 ==================
async def play_song(interaction: discord.Interaction, url: str):
    try:
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.followup.send("음성 채널에 먼저 들어가 주세요!", ephemeral=True)
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

        ffmpeg_executable = "/nix/store/3zc5jbvqzrn8zmva4fx5p0nh4yy03wk4-ffmpeg-6.1.1-bin/bin/ffmpeg"  # 환경에 맞게 변경

        source = discord.FFmpegOpusAudio(audio_url, executable=ffmpeg_executable, **ffmpeg_opts)

        if voice_client.is_playing():
            voice_client.stop()

        voice_client.play(source)
        now_playing[interaction.guild.id] = title
        await interaction.followup.send(f"🎶 재생 시작: **{title}**")

    except Exception as e:
        print(f"[재생 오류]: {type(e).__name__} - {e}")
        try:
            await interaction.followup.send("❌ 노래 재생 중 오류가 발생했습니다.", ephemeral=True)
        except:
            pass

# ================== /검색 커맨드 ==================
@bot.tree.command(name="검색", description="노래를 검색합니다.")
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
            if not videos:
                await interaction.followup.send("검색 결과가 없습니다.", ephemeral=True)
                return

        class SongSelect(discord.ui.Select):
            def __init__(self, videos: list):
                options = []
                for i, video in enumerate(videos[:5]):
                    title = video.get('title', '제목 없음')
                    url = video.get('webpage_url')
                    duration = video.get('duration_string', '정보 없음')
                    options.append(discord.SelectOption(
                        label=f"{i+1}. {title[:95]}",
                        value=url,
                        description=f"길이: {duration}"
                    ))
                super().__init__(placeholder="노래를 선택하세요", options=options, max_values=1)

            async def callback(self, select_interaction: discord.Interaction):
                await select_interaction.response.defer()
                await play_song(select_interaction, self.values[0])

        view = discord.ui.View(timeout=60)
        view.add_item(SongSelect(videos))

        embed = discord.Embed(
            title=f"🔍 '{query}' 검색 결과 (상위 5개)",
            color=0x1DB954
        )
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except Exception as e:
        print(f"[검색 오류]: {type(e).__name__} - {e}")
        await interaction.followup.send("검색 중 오류가 발생했습니다.", ephemeral=True)

# ================== /스킵 커맨드 ==================
@bot.tree.command(name="스킵", description="현재 재생 중인 노래를 건너뜁니다.")
async def skip(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ 노래를 건너뛰었습니다!")
    else:
        await interaction.response.send_message("❌ 현재 재생 중인 노래가 없습니다.", ephemeral=True)

# ================== /정지 커맨드 ==================
@bot.tree.command(name="정지", description="노래 재생을 멈추고 음성 채널에서 나갑니다.")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client:
        if voice_client.is_playing():
            voice_client.stop()
        await voice_client.disconnect()
        await interaction.response.send_message("⏹️ 노래 재생을 멈추고 음성 채널에서 나갔습니다.")
    else:
        await interaction.response.send_message("❌ 봇이 음성 채널에 없습니다.", ephemeral=True)

# ================== 혼자 남았을 때 퇴장 ==================
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return

    voice_client = discord.utils.get(bot.voice_clients, guild=member.guild)
    if voice_client and voice_client.channel and len(voice_client.channel.members) == 1:
        await voice_client.disconnect()

# ================== 실행 ==================
def run_bot():
    token = os.getenv("TOKEN")
    if not token:
        print("ERROR: TOKEN 환경변수가 설정되지 않았습니다.")
        return

    bot.run(token)

if __name__ == "__main__":
    Thread(target=run_web).start()
    run_bot()
