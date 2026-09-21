# Admin rollari

Super admin: `5589013665` (`SUPER_ADMIN_ID`). Eski `ADMINS` ro‘yxati boshqa akkauntlarga super admin vakolatini bermaydi.

## Telegram orqali boshqarish

1. Super admin akkauntidan `/admin` → **Adminlar va ruxsatlar** (yoki `/admins`).
2. **Telegram ID orqali qo‘shish** → ID → bosh koordinator yoki yordamchi admin rolini tanlang.
3. Yordamchi admin uchun panelda ko‘rinadigan nom kiriting.
4. Ro‘yxatdan koordinatorni tanlab kerakli huquqlarni yoqing/o‘chiring. **Kirishni to‘xtatish** barcha admin vakolatlarini to‘xtatadi; **Kirishni tiklash** saqlangan ruxsatlarni qaytaradi.
5. Rolni almashtirish uchun o‘sha Telegram ID ni qayta qo‘shing. Bu individual cheklovlarni rolning standart ruxsatlariga qaytaradi.

Yangi koordinator botga `/start`, keyin `/admin` yuboradi. Botga yozmagan akkauntga ham ID orqali rol berish mumkin.

## Vakolatlar

- Super admin: adminlarni tayinlash, sozlamalar, guruhlar va barcha amallar. O‘zini paneldan bloklay olmaydi.
- Super admin **Faollar** bo‘limida tasdiqlangan talabalarni 15 tadan ko‘radi, F.I.Sh, username, guruh yoki Telegram ID bo‘yicha qidiradi va batafsil ma’lumotini ochadi.
- **Faollarni ko‘rish**, **faollar ballini boshqarish** va **faollar Excel eksporti** huquqlari super admin tomonidan boshqa adminlarga alohida beriladi yoki olib qo‘yiladi. Ball qo‘shish/ayirishda izoh majburiy; o‘zgarish muallifi va vaqti bazada saqlanadi.
- **Faolni ro‘yxatdan o‘chirish** alohida, standart holatda o‘chiq huquqdir. O‘chirish ikki bosqichda tasdiqlanadi; tarixiy tadbir va ball ma’lumotlari saqlanadi, ochiq tadbirlardagi kutilayotgan yozuvlar bekor qilinadi.
- Bosh koordinator: barcha yo‘nalishlarda yaratish, tahrirlash, tasdiqlash, davomat, yakunlash, hisobot, xabar va oy talabalarini boshqarish. Har bir huquqni super admin cheklashi mumkin.
- Yordamchi admin: tadbir yaratadi; faqat o‘zi yaratgan yoki mas’ul sifatida biriktirilgan tadbirlarni ko‘radi va boshqaradi. Tasdiqlash, barcha talabalar eksporti, admin boshqaruvi va tizim sozlamalari berilmaydi.

Tadbir avval `pending` holatda saqlanadi. Tasdiqlash huquqi bor yaratuvchi uni darhol tasdiqlaydi; qolganlar yaratgan tadbir **Tasdiqlash kutilmoqda** bo‘limida ko‘rinadi. Tasdiqlanmaguncha ro‘yxatdan o‘tish va e’lon qilish yopiq. E’lon qilingan tadbirni tahrirlash uchun tahrirlash hamda tasdiqlash ruxsati kerak. Yakunlangan tadbir davomatini o‘zgartirish yopiq.

Oldingi tadbirlar tasdiqlangan holatda saqlanadi; ularga kirish amaldagi rol va biriktirilgan mas’ullik bo‘yicha tekshiriladi.

Ruxsatlar har bir mos kelgan handlerda, jumladan callback va FSM davomida qayta tekshiriladi. Xabar yuborish davrida ruxsat bekor qilinsa, qolgan yuborishlar to‘xtaydi. Oldin boshlangan tarmoq so‘rovi yoki oldin yuborilgan xabar ortga qaytarilmaydi. Rol/ruxsat o‘zgarishlari `admin_access_audit` jadvalida saqlanadi.

## Tekshiruv

- `.venv\Scripts\python.exe -m unittest discover -s tests -v` — tarmoqsiz ruxsat va Telegram router oqimi testlari.
- `.venv\Scripts\python.exe tests/db_access_smoke.py` — sozlangan bazada alohida sxema yaratib, migratsiya va SQL amallarini sinaydi; yakunda tranzaksiyani bekor qiladi.

Baza migratsiyasi `app.py` ishga tushganda qo‘llanadi. Yangi jadvallar va ustunlar qo‘shiladi; foydalanuvchilar hamda mavjud tadbirlar o‘chirilmaydi.

Bot kiruvchi guruh xabarlari va komandalariga javob bermaydi. Telegram komandalar menyusi faqat bot bilan shaxsiy chatda ko‘rsatiladi; bot guruhlarga faqat tizimdagi e’lon va natijalarni o‘zi yuboradi.
