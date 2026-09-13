from environs import Env

# environs kutubxonasidan foydalanish
env = Env()
env.read_env()

# .env fayl ichidan quyidagilarni o'qiymiz
BOT_TOKEN = env.str("BOT_TOKEN")
SUPER_ADMIN_ID = env.int("SUPER_ADMIN_ID", 5589013665)
ADMINS = [str(SUPER_ADMIN_ID)]
IP = env.str("IP", "0.0.0.0")
# Talaba rasmlari (selfie, tasdiqlovchi rasm) shu yopiq kanalga yuboriladi,
# DB'da faqat file_id/message_id saqlanadi
PHOTO_CHANNEL_ID = env.int("PHOTO_CHANNEL_ID", 0)
# Admin/mas'ul shaxs amallari (e'lon, broadcast, sozlama o'zgarishi va h.k.) shu kanalga yozib boriladi
LOG_CHANNEL_ID = env.int("LOG_CHANNEL_ID", 0)

DB_USER = env.str("DB_USER")
DB_PASS = env.str("DB_PASS")
DB_HOST = env.str("DB_HOST")
DB_NAME = env.str("DB_NAME")
DB_PORT = env.int("DB_PORT", 5432)
DB_SSL = env.bool("DB_SSL", True)
