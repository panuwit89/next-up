import os
from pymongo import MongoClient
from dotenv import load_dotenv

# โหลดตัวแปรจากไฟล์ .env
load_dotenv()

# เชื่อมต่อกับ MongoDB
MONGO_URI = os.getenv("MONGO_URI")
if not MONGO_URI:
    raise ValueError("ไม่พบ MONGO_URI ในไฟล์ .env หรือ Environment Variables")

client = MongoClient(MONGO_URI)

# ตั้งชื่อ Database และ Collection
db = client["anime_bot_db"]
collection = db["subscriptions"]

def subscribe(guild_id: str, channel_id: str, anime_id: int, anime_title: str):
    """เพิ่มหรืออัปเดตการแจ้งเตือนอนิเมะ"""
    # replace_one แบบ upsert=True จะทำการค้นหา ถ้าเจอจะเขียนทับ ถ้าไม่เจอจะสร้างใหม่ (คล้ายกับ db[key] = {...} เดิม)
    collection.replace_one(
        {"guild_id": guild_id, "anime_id": anime_id},
        {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "anime_id": anime_id,
            "anime_title": anime_title,
            "last_episode": None,
            "offset_minutes": 0 # เพิ่มค่าเริ่มต้นไว้กัน error ในฟังก์ชันอื่น
        },
        upsert=True
    )

def unsubscribe(guild_id: str, anime_id: int):
    """ลบการแจ้งเตือน"""
    result = collection.delete_one({"guild_id": guild_id, "anime_id": anime_id})
    return result.deleted_count > 0 # deleted_count จะมากกว่า 0 ถ้ามีการลบข้อมูลออกไปจริงๆ

def update_last_episode(guild_id: str, anime_id: int, episode: int):
    """อัปเดตเลขตอนล่าสุด"""
    collection.update_one(
        {"guild_id": guild_id, "anime_id": anime_id},
        {"$set": {"last_episode": episode}}
    )

def set_offset(guild_id: str, anime_id: int, offset_minutes: int):
    """ตั้งค่าเวลาชดเชย (offset)"""
    result = collection.update_one(
        {"guild_id": guild_id, "anime_id": anime_id},
        {"$set": {"offset_minutes": offset_minutes}}
    )
    return result.matched_count > 0 # matched_count เช็คว่าค้นหาข้อมูลเจอหรือไม่

def get_offset(guild_id: str, anime_id: int) -> int:
    """ดึงค่าเวลาชดเชย"""
    doc = collection.find_one({"guild_id": guild_id, "anime_id": anime_id})
    if doc:
        return doc.get("offset_minutes", 0)
    return 0

def get_subscriptions():
    """ดึงข้อมูลการแจ้งเตือนทั้งหมด (คืนค่าเป็นลิสต์ของดิกชันนารี)"""
    return list(collection.find({}, {"_id": 0})) # {"_id": 0} คือการบอกว่าไม่ต้องดึงเอา _id ที่ mongodb สร้างให้ออกมาด้วย เพื่อให้โครงสร้างเหมือน json เดิม

def get_guild_subscriptions(guild_id: str):
    """ดึงข้อมูลการแจ้งเตือนเฉพาะของ Server (Guild) นั้นๆ"""
    return list(collection.find({"guild_id": guild_id}, {"_id": 0}))
