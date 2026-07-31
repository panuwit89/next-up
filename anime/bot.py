import discord
from discord.ext import commands
from discord import app_commands
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import os
from dotenv import load_dotenv
import asyncio
import datetime

from anime.database import (
    subscribe, unsubscribe, get_subscriptions,
    update_last_episode, get_guild_subscriptions,
    set_offset, get_offset
)
from anime.anime_checker import search_anime, get_latest_episode, get_airing_episodes, get_seasonal_anime, get_episode_list, get_anime_by_id, get_next_airing_episode

load_dotenv()

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
scheduler = AsyncIOScheduler()
BANGKOK_TZ = datetime.timezone(datetime.timedelta(hours=7))
last_scheduler_started_at = None
last_episode_check_started_at = None
last_episode_check_finished_at = None
last_episode_check_error = None

def format_airing_time(airing_at: int, offset_minutes: int = 0) -> str:
    airing_time = datetime.datetime.fromtimestamp(
        airing_at + offset_minutes * 60,
        tz=BANGKOK_TZ
    )
    return airing_time.strftime("%d/%m %H:%M")

# ==================== COMMANDS ====================

@bot.tree.command(name="subscribe", description="ติดตามอนิเมะเพื่อรับแจ้งเตือนตอนใหม่")
@app_commands.describe(
    query="ชื่ออนิเมะที่ต้องการติดตาม",
    anime_id="ID ของอนิเมะ"
)
async def cmd_subscribe(interaction: discord.Interaction, query: str = None, anime_id: int = None):
    await interaction.response.defer()

    # ถ้ามี anime_id ให้ sub เลยโดยไม่ต้อง search
    if anime_id:
        anime = await get_anime_by_id(anime_id)
        if not anime:
            await interaction.followup.send("❌ ไม่พบอนิเมะจาก ID ที่ระบุ")
            return

        title = anime.get("title", {}).get("romaji", "Unknown")
        ep_num, ep_title = await get_airing_episodes(anime_id)

        subscribe(
            str(interaction.guild_id),
            str(interaction.channel_id),
            anime_id,
            title
        )

        if ep_num:
            update_last_episode(str(interaction.guild_id), anime_id, ep_num)

        embed = discord.Embed(
            title="✅ ติดตามสำเร็จ!",
            description=f"จะแจ้งเตือนเมื่อ **{title}** มีตอนใหม่ในช่อง <#{interaction.channel_id}>",
            color=discord.Color.green()
        )

        if anime.get("coverImage", {}).get("large"):
            embed.set_thumbnail(url=anime["coverImage"]["large"])

        await interaction.followup.send(embed=embed)
        return

    # ถ้าไม่มี anime_id ต้องมี query
    if not query:
        await interaction.followup.send("❌ กรุณาระบุชื่ออนิเมะ หรือ ID อย่างใดอย่างหนึ่ง")
        return

    results = await search_anime(query)

    if not results:
        await interaction.followup.send("❌ ไม่พบอนิเมะที่ค้นหา ลองใช้ชื่อภาษาอังกฤษดูนะครับ")
        return

    # สร้าง dropdown ให้เลือก
    options = []
    for anime in results[:5]:
        title = anime.get("title", {}).get("romaji", "Unknown")
        aid = anime.get("id")
        ep = anime.get("episodes", "?")
        status = anime.get("status", "")

        options.append(discord.SelectOption(
            label=title[:100],
            value=str(aid),
            description=f"ตอน: {ep} | {status}"[:100]
        ))

    class AnimeSelect(discord.ui.Select):
        def __init__(self):
            super().__init__(placeholder="เลือกอนิเมะ...", options=options)

        async def callback(self, select_interaction: discord.Interaction):
            selected_id = int(self.values[0])
            selected = next((a for a in results if a["id"] == selected_id), None)
            title = selected["title"]["romaji"] if selected else "Unknown"

            ep_num, ep_title = await get_airing_episodes(selected_id)

            subscribe(
                str(interaction.guild_id),
                str(interaction.channel_id),
                selected_id,
                title
            )

            if ep_num:
                update_last_episode(str(interaction.guild_id), selected_id, ep_num)

            embed = discord.Embed(
                title="✅ ติดตามสำเร็จ!",
                description=f"จะแจ้งเตือนเมื่อ **{title}** มีตอนใหม่ในช่อง <#{interaction.channel_id}>",
                color=discord.Color.green()
            )

            if selected and selected.get("coverImage", {}).get("large"):
                embed.set_thumbnail(url=selected["coverImage"]["large"])

            await select_interaction.response.edit_message(content=None, embed=embed, view=None)

    view = discord.ui.View()
    view.add_item(AnimeSelect())
    await interaction.followup.send("🔍 พบอนิเมะต่อไปนี้ เลือกที่ต้องการติดตาม:", view=view)

@bot.tree.command(name="unsubscribe", description="ยกเลิกการติดตามอนิเมะ")
@app_commands.describe(anime_id="Anime ID (จาก /list)")
async def cmd_unsubscribe(interaction: discord.Interaction, anime_id: int):
    success = unsubscribe(str(interaction.guild_id), anime_id)

    if success:
        await interaction.response.send_message(f"✅ ยกเลิกการติดตาม Anime ID `{anime_id}` แล้ว")
    else:
        await interaction.response.send_message("❌ ไม่พบอนิเมะที่ติดตามอยู่")


@bot.tree.command(name="list", description="ดูรายการอนิเมะที่ติดตามอยู่")
async def cmd_list(interaction: discord.Interaction):
    await interaction.response.defer()

    subs = get_guild_subscriptions(str(interaction.guild_id))

    if not subs:
        await interaction.followup.send("📋 ยังไม่ได้ติดตามอนิเมะเรื่องใด ใช้ `/subscribe` เพื่อเริ่มต้น")
        return

    embed = discord.Embed(
        title="📺 อนิเมะที่ติดตามอยู่",
        color=discord.Color.blue()
    )

    for sub in subs:
        ep = sub.get("last_episode", "?")
        offset = get_offset(str(interaction.guild_id), sub["anime_id"])
        latest_ep, _ = await get_airing_episodes(sub["anime_id"], offset)

        if latest_ep and (ep == "?" or ep is None or latest_ep > ep):
            update_last_episode(str(interaction.guild_id), sub["anime_id"], latest_ep)
            ep = latest_ep

        next_ep = await get_next_airing_episode(sub["anime_id"])

        if next_ep:
            day_str = format_airing_time(next_ep["airingAt"], offset)
            offset_str = f" (+{offset}น.)" if offset else ""
            next_str = f"ตอน {next_ep['episode']} — {day_str}{offset_str}"
        else:
            next_str = "ไม่ระบุ"

        embed.add_field(
            name=sub["anime_title"],
            value=(
                f"ID: `{sub['anime_id']}` | ตอนล่าสุด: {ep}\n"
                f"⏭ ตอนถัดไป: {next_str}\n"
                f"📢 Channel: <#{sub['channel_id']}>"
            ),
            inline=False
        )

    await interaction.followup.send(embed=embed)

@bot.tree.command(name="onair", description="ดูอนิเมะที่กำลังออกอากาศอยู่ตอนนี้")
@app_commands.describe(limit="จำนวนที่ต้องการแสดง (สูงสุด 25, default 10)")
async def cmd_onair(interaction: discord.Interaction, limit: int = 10):
    await interaction.response.defer()

    results = await get_seasonal_anime(min(limit, 25))

    if not results:
        await interaction.followup.send("❌ ดึงข้อมูลไม่ได้ในตอนนี้ ลองใหม่อีกครั้งนะครับ")
        return

    # เรียงตาม score
    results.sort(key=lambda x: x.get("score") or 0, reverse=True)

    embed = discord.Embed(
        title="📺 อนิเมะที่กำลัง On Air อยู่ตอนนี้",
        color=discord.Color.purple()
    )

    for anime in results[:limit]:
        title = anime.get("title", {}).get("romaji", "Unknown")
        anime_id = anime.get("id", "?")
        score = anime.get("averageScore") or "?"
        ep_count = anime.get("episodes") or "?"
        next_ep = anime.get("nextAiringEpisode")

        if next_ep:
            offset = get_offset(str(interaction.guild_id), anime_id)
            day_str = format_airing_time(next_ep["airingAt"], offset)
            offset_str = f" (+{offset}น.)" if offset else ""
            next_str = f"ตอน {next_ep['episode']} — {day_str}{offset_str}"
        else:
            next_str = "ไม่ระบุ"

        embed.add_field(
            name=title,
            value=f"⭐ {score} | 🎬 {ep_count} ตอน | ⏭ {next_str} | ID: `{anime_id}`",
            inline=False
        )

    embed.set_footer(text="ใช้ /subscribe <ชื่อเรื่อง> เพื่อติดตาม | ใช้ /episodes <id> เพื่อดูตอน")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="episodes", description="ดูว่าอนิเมะออกมากี่ตอนแล้ว")
@app_commands.describe(anime_id="Anime ID จาก /onair หรือ /list")
async def cmd_episodes(interaction: discord.Interaction, anime_id: int):
    await interaction.response.defer()

    anime_info, episodes = await get_episode_list(anime_id)

    if anime_info is None:
        await interaction.followup.send("❌ ไม่พบอนิเมะ ID นี้")
        return

    title = anime_info.get("title", {}).get("romaji", "Unknown")
    total_ep = anime_info.get("episodes") or "ยังไม่ระบุ"
    status = anime_info.get("status", "")
    aired_count = len(episodes)
    image = anime_info.get("coverImage", {}).get("large")
    url = anime_info.get("siteUrl")

    embed = discord.Embed(
        title=f"🎬 {title}",
        url=url,
        color=discord.Color.blue()
    )

    if image:
        embed.set_thumbnail(url=image)

    embed.add_field(name="สถานะ", value=status, inline=True)
    embed.add_field(name="ออกแล้ว", value=f"{aired_count} ตอน", inline=True)
    embed.add_field(name="ทั้งหมด", value=f"{total_ep} ตอน", inline=True)

    # แสดง 5 ตอนล่าสุด
    if episodes:
        # เรียงจากมากไปน้อย แล้วเอา 5 ตอนล่าสุด
        sorted_eps = sorted(episodes, key=lambda e: e["episode"], reverse=True)
        recent_text = "\n".join(
            f"ตอน {ep['episode']}"
            for ep in sorted_eps[:5]
        )
        embed.add_field(name="5 ตอนล่าสุด", value=recent_text, inline=False)

    embed.set_footer(text=f"Anime ID: {anime_id} | ใช้ /subscribe เพื่อติดตาม")
    await interaction.followup.send(embed=embed)

@bot.tree.command(name="setoffset", description="ตั้งเวลาชดเชยสำหรับอนิเมะที่ปล่อยช้ากว่า AniList")
@app_commands.describe(
    anime_id="Anime ID จาก /list",
    offset_minutes="จำนวนนาทีที่ช้ากว่า AniList เช่น 30 หรือ 60 นาที"
)
async def cmd_setoffset(interaction: discord.Interaction, anime_id: int, offset_minutes: int):
    success = set_offset(str(interaction.guild_id), anime_id, offset_minutes)

    if success:
        await interaction.response.send_message(
            f"✅ ตั้งค่าเวลาชดเชยสำหรับ ID `{anime_id}` เป็น **+{offset_minutes} นาที** แล้วครับ"
        )
    else:
        await interaction.response.send_message(
            "❌ ไม่พบอนิเมะ ID นี้ในรายการติดตาม ต้อง `/subscribe` ก่อนนะครับ"
        )

# ==================== SCHEDULER ====================

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

def ensure_scheduler_running():
    global last_scheduler_started_at

    scheduler.add_job(
        check_new_episodes,
        "interval",
        minutes=10,
        id="anime_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )

    if not scheduler.running:
        scheduler.start()
        last_scheduler_started_at = utc_now()
        print("Scheduler started")
    else:
        print("Scheduler already running")

def get_health_status():
    job = scheduler.get_job("anime_check")
    bot_ready = bot.is_ready()
    scheduler_ready = scheduler.running and job is not None

    return {
        "healthy": bot_ready and scheduler_ready,
        "bot_ready": bot_ready,
        "latency_ms": round(bot.latency * 1000, 2) if bot.latency else None,
        "scheduler_running": scheduler.running,
        "anime_check_job_exists": job is not None,
        "next_anime_check_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "last_scheduler_started_at": last_scheduler_started_at.isoformat() if last_scheduler_started_at else None,
        "last_episode_check_started_at": last_episode_check_started_at.isoformat() if last_episode_check_started_at else None,
        "last_episode_check_finished_at": last_episode_check_finished_at.isoformat() if last_episode_check_finished_at else None,
        "last_episode_check_error": last_episode_check_error,
    }

async def check_new_episodes():
    global last_episode_check_started_at, last_episode_check_finished_at, last_episode_check_error

    last_episode_check_started_at = utc_now()
    last_episode_check_error = None
    """ตรวจสอบอนิเมะทุกครึ่งชั่วโมง"""
    print("🔍 กำลังตรวจสอบตอนใหม่...")
    subs = get_subscriptions()

    for sub in subs:
        try:
            anime_id = sub["anime_id"]
            guild_id = sub["guild_id"]
            channel_id = sub["channel_id"]
            last_ep = sub.get("last_episode")

            offset = sub.get("offset_minutes", 0)
            ep_num, ep_title = await get_airing_episodes(anime_id, offset)
            if not ep_num:
                continue

            # มีตอนใหม่!
            if last_ep is None or ep_num > last_ep:
                update_last_episode(guild_id, anime_id, ep_num)

                channel = bot.get_channel(int(channel_id))
                if not channel:
                    continue

                anime_info = await get_latest_episode(anime_id)

                embed = discord.Embed(
                    title=f"🎬 {sub['anime_title']} — ตอนที่ {ep_num} ออกแล้ว!",
                    description=ep_title or "ตอนใหม่เพิ่งอัปโหลดแล้ว!",
                    color=discord.Color.orange(),
                    url=anime_info.get("url") if anime_info else None
                )

                if anime_info and anime_info.get("image"):
                    embed.set_thumbnail(url=anime_info["image"])
                if anime_info and anime_info.get("score"):
                    embed.add_field(name="⭐ คะแนน MAL", value=anime_info["score"])

                embed.set_footer(text="ข้อมูลจาก MyAnimeList")

                await channel.send("@here", embed=embed)
                print(f"✅ แจ้งเตือน {sub['anime_title']} ตอน {ep_num}")

            await asyncio.sleep(1)  # หน่วงเวลาเพื่อไม่ให้ hit rate limit

        except Exception as e:
            print(f"❌ Error ตรวจสอบ {sub.get('anime_title')}: {e}")

    last_episode_check_finished_at = utc_now()

# ==================== EVENTS ====================

@bot.event
async def on_ready():
    print(f"✅ Bot เริ่มทำงาน: {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"📡 Sync {len(synced)} commands แล้ว")
    except Exception as e:
        print(f"❌ Sync error: {e}")

    # เริ่ม scheduler
    ensure_scheduler_running()
    print("⏰ Scheduler เริ่มทำงาน (ตรวจทุก 10 นาที)")

@bot.event
async def on_resumed():
    ensure_scheduler_running()
