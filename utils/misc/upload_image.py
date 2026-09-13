from aiogram import Bot
from aiogram.types import Document, InputMediaDocument, InputMediaPhoto, PhotoSize

from data import config


async def upload_photo_to_channel(bot: Bot, photo: PhotoSize, caption: str = None):
    """
    Rasmni yopiq Telegram kanalga yuboradi (shaxsiy ma'lumot ochiq internetga chiqmasligi uchun).
    DB'da faqat file_id va message_id saqlanadi.
    Qaytaradi: (file_id, message_id)
    """
    message = await bot.send_photo(chat_id=config.PHOTO_CHANNEL_ID, photo=photo.file_id, caption=caption)
    return message.photo[-1].file_id, message.message_id


async def upload_document_to_channel(bot: Bot, document: Document, caption: str = None):
    """
    Faylni (asl sifatda, siqilmasdan) yopiq Telegram kanalga yuboradi.
    Qaytaradi: (file_id, message_id)
    """
    message = await bot.send_document(chat_id=config.PHOTO_CHANNEL_ID, document=document.file_id, caption=caption)
    return message.document.file_id, message.message_id


async def send_event_media(bot: Bot, chat_id: int, media_rows):
    """
    event_media jadvalidan olingan qatorlarni turi (photo/document) bo'yicha
    guruhlab, albom sifatida yuboradi.
    """
    photos = [m for m in media_rows if m["file_type"] != "document"]
    documents = [m for m in media_rows if m["file_type"] == "document"]

    for i in range(0, len(photos), 10):
        chunk = photos[i:i + 10]
        if len(chunk) == 1:
            await bot.send_photo(chat_id, chunk[0]["file_id"])
        else:
            await bot.send_media_group(chat_id, [InputMediaPhoto(media=m["file_id"]) for m in chunk])

    for i in range(0, len(documents), 10):
        chunk = documents[i:i + 10]
        if len(chunk) == 1:
            await bot.send_document(chat_id, chunk[0]["file_id"])
        else:
            await bot.send_media_group(chat_id, [InputMediaDocument(media=m["file_id"]) for m in chunk])
