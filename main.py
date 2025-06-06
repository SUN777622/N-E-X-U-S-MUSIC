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
            # 영상 필터링 강화
            videos = [
                v for v in videos
                if v and isinstance(v, dict)
                and v.get('webpage_url')
                and not v.get('is_unavailable')
                and v.get('duration') and v['duration'] > 0
                and not v.get('live_status') == 'is_live'
                and v.get('availability', '') != 'unavailable'
            ]

            if not videos:
                await interaction.followup.send("❌ 재생 가능한 영상이 없습니다.", ephemeral=True)
                return

        class SongSelect(discord.ui.Select):
            def __init__(self, videos):
                options = [
                    discord.SelectOption(
                        label=f"{i+1}. {video.get('title', '제목 없음')[:95]}",
                        value=video['webpage_url'],
                        description=f"{video.get('duration_string', '길이 정보 없음')}"
                    )
                    for i, video in enumerate(videos[:5])
                ]
                super().__init__(placeholder="노래를 선택하세요!", options=options)

            async def callback(self, interaction2: discord.Interaction):
                await interaction2.response.send_message("노래를 재생합니다...", ephemeral=True)
                await play_song(interaction2, self.values[0])

        view = discord.ui.View(timeout=60)
        view.add_item(SongSelect(videos))

        embed = discord.Embed(title=f"🔍 '{query}' 검색 결과", color=0x1DB954)
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)

    except Exception as e:
        print(f"[검색 오류]: {type(e).__name__} - {e}")
        await interaction.followup.send(f"오류 발생:\n```{type(e).__name__}: {e}```", ephemeral=True)
