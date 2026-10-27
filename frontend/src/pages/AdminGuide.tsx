import { Alert, Card, Col, Divider, Row, Tag, Typography } from 'antd';
import { PageHeading } from './shared';

const { Paragraph, Text } = Typography;

const buttonGuides = [
  {
    title: 'Bosh sahifa',
    actions: [
      ['Ko‘rsatkich kartalari', 'Yashovchilar, band o‘rinlar, qarzdorlik, tushum va xarajatlarni umumlashtiradi. Tushum qabul qilingan to‘lovlardan olinadi.'],
      ['So‘nggi to‘lovlar · Barchasi', 'To‘lovlar sahifasiga o‘tib, sana oralig‘i va jami tushumni ko‘ring.'],
    ],
  },
  {
    title: 'Yashovchilar',
    actions: [
      ['Yashovchi qo‘shish', 'Shaxsiy ma’lumot, xona, kirish sanasi va kelishilgan to‘lov davrini kiriting. Saqlash yangi profil yaratadi.'],
      ['Ism ustiga bosish · ko‘z belgisi', 'Yashovchi kartasini ochadi: xona, qarz, hisob davrlari va to‘lovlar tarixi.'],
      ['Qalam · Tahrirlash', 'Aloqa, xona va profil ma’lumotlarini o‘zgartiradi. Xonani almashtirishda bo‘sh joy tekshiriladi.'],
      ['Ikki yo‘nalishli strelka · Muddatni uzaytirish', 'Joriy hisob davrining tugash sanasini uzaytiradi. Bu amal to‘lov yozmaydi; tushumni “To‘lov qayd etish” orqali kiriting.'],
      ['Chiqish belgisi · Muddatidan oldin chiqish', 'Chiqish sanasini kiriting. Shu sanadan xona bo‘sh hisoblanadi va yangi davr ochilmaydi. Joriy hisob, qarz va to‘lovlar saqlanadi; to‘lovsiz va boshlanmagan davrlar audit bilan yopiladi. Qisman yoki to‘liq to‘langan davrlar o‘zgartirilmaydi.'],
      ['Arxiv', 'Profilni arxiv ro‘yxatiga yashiradi. Bu chiqish jarayoni emas va tarixni o‘chirmaydi.'],
      ['Qayta joylashtirish', 'Chiqib ketgan yashovchiga bugundan boshlab xona tayinlaydi.'],
      ['Tiklash', 'Arxivdagi profilni faol ro‘yxatga qaytaradi; xona bandligi qayta tekshiriladi.'],
      ['Qidirish va filtrlar', 'Ism, xona, telefon, Telegram, to‘lov holati yoki ro‘yxat turiga qarab toping.'],
    ],
  },
  {
    title: 'Xonalar',
    actions: [
      ['Xona qo‘shish', 'Yotoqxona, raqam, qavat, sig‘im va narxni kiriting.'],
      ['Qalam · Tahrirlash', 'Xona ma’lumotlarini yangilaydi. Sig‘im band o‘rinlardan kam qilinmaydi.'],
      ['Arxiv', 'Xonani yangi joylashtirishdan chiqaradi. Avval xonadagi yashovchilarni ko‘chiring.'],
      ['Bandlik va bo‘sh o‘rinlar', 'Xona sig‘imi hamda mavjud bo‘sh joylarni ko‘rsatadi.'],
    ],
  },
  {
    title: 'Qabul va arizalar',
    actions: [
      ['Taklif yaratish', 'Ariza kampaniyasi va maxsus havola yaratadi. Havola faqat yaratilganda ko‘rsatiladi; nusxasini xavfsiz saqlang.'],
      ['Yangi taklif · Havola yaratish', 'Faol kampaniya, havola tugash vaqti va arizalar limitini belgilang; yuborish uchun maxsus havola yaratiladi.'],
      ['Qidirish · holat · kampaniya', 'Arizalar navbatini toraytiradi; yangilash belgisi ro‘yxatni qayta yuklaydi.'],
      ['Arizani ochish · Ko‘rish', 'Ariza, hujjatlar va AI taklif qilgan maydonlarni ko‘rsatadi. Qiymatlarni asl hujjat bilan solishtirib tekshiring.'],
      ['Tekshiruvni boshlash', 'Arizani ko‘rib chiqilmoqda holatiga o‘tkazadi.'],
      ['Tasdiqlash', 'Arizani tasdiqlaydi va kiritilgan xona hamda to‘lov shartlari bilan yashovchi profilini yaratadi.'],
      ['Yashovchini ochish', 'Tasdiqlangan arizadan yaratilgan profilni “Yashovchilar”da ochadi.'],
      ['Aniqlik so‘rash', 'Yetishmayotgan maydonlarni tanlab talabaga qayta to‘ldirish uchun yuboradi.'],
      ['Rad etish', 'Arizani rad qiladi; oynada sababni kiriting.'],
      ['Kirish kodini yangilash', 'Ariza holatini ko‘rish kodi yo‘qolganida yangi kod chiqaradi. Shaxsni tekshirib, kodni talabaga alohida yetkazing.'],
      ['Pauza', 'Taklif havolasi orqali yangi ariza yuborishni vaqtincha to‘xtatadi.'],
      ['Davom', 'To‘xtatilgan taklif havolasini qayta faollashtiradi.'],
      ['Bekor qilish', 'Taklif havolasini qaytarib bo‘lmaydigan tarzda bekor qiladi.'],
      ['Himoyalangan ko‘rish', 'Yuklangan hujjatni himoyalangan rejimda ochadi yoki yuklab oladi. Hujjatlarni faqat ish uchun ko‘ring.'],
      ['Kampaniya yaratish', 'Ariza shakli, talab qilinadigan hujjatlar, rozilik matni va qo‘shimcha maydonlarni sozlaydi.'],
      ['Maydon qo‘shish · O‘chirish', 'Ariza shakliga maydon qo‘shadi yoki hali saqlanmagan maydonni olib tashlaydi.'],
      ['Yotoqxona qo‘shish · Tahrirlash', 'Qabul kampaniyasi uchun yotoqxona nomi va manzilini yaratadi yoki o‘zgartiradi.'],
    ],
  },
  {
    title: 'To‘lovlar',
    actions: [
      ['To‘lov qayd etish', 'Yashovchi, summa, sana va to‘lov usulini tanlang. Summa hisobdagi qarzdan oshmasligi kerak. Saqlash haqiqiy tushumni qayd etadi.'],
      ['Sana oralig‘i · Filtrni tozalash', 'Ko‘rsatiladigan to‘lovlarni sana bo‘yicha tanlaydi yoki filtrni olib tashlaydi.'],
      ['Tuzatish', 'Operator uchun: noto‘g‘ri yoki qaytarilgan to‘lovga sabab yozib, audit izi bilan tuzatish kiritadi.'],
    ],
  },
  {
    title: 'Xarajatlar',
    actions: [
      ['Xarajat qo‘shish', 'Sana, toifa, izoh, summa va to‘lov usulini kiritib xarajatni qayd etadi.'],
      ['Bekor qilinganlarni ko‘rsatish', 'Bekor qilingan yozuvlarni ham ro‘yxatda ko‘rsatadi yoki yashiradi.'],
      ['Bekor qilish', 'Xarajatni o‘chirmaydi: sabab bilan bekor qilingan deb belgilaydi.'],
      ['Filtrni tozalash', 'Sana oralig‘ini olib tashlaydi.'],
    ],
  },
  {
    title: 'Hisobotlar',
    actions: [
      ['Sana oralig‘i va hisobot turi', 'Kerakli davr va ko‘rsatkichlarni tanlaydi.'],
      ['XLSX · CSV · PDF', 'Har bir format tugmasi tanlangan hisobotni Excel, CSV yoki PDF fayli sifatida yuklab oladi. Eksportni ulashishdan avval shaxsiy ma’lumotlarni tekshiring.'],
    ],
  },
  {
    title: 'Sozlamalar va operator vositalari',
    actions: [
      ['Saqlash', 'Tizim nomi, standart to‘lov muddati va ruxsat etilgan sozlamalarni saqlaydi.'],
      ['O‘zgarishlarni saqlash', 'Tahrirlangan umumiy sozlamalarni saqlaydi. Ruxsat bo‘lmasa, tugma o‘chiq turadi.'],
      ['Foydalanuvchi qo‘shish · tahrirlash', 'Operator administrator hisoblarini yaratadi yoki ruxsatlarini yangilaydi. Har bir xodimga alohida hisob bering.'],
      ['Foydalanuvchi yaratish', 'Yangi administrator uchun ism, elektron pochta va vaqtinchalik parolni saqlaydi.'],
      ['Audit jurnali', 'Ma’lumotlar va moliyaviy amallarni kim va qachon bajarganini ko‘rsatadi.'],
      ['Bildirishnomalar', 'Bildirishnomalar ro‘yxatini ochadi; tanlash ularni o‘qilgan deb belgilaydi.'],
      ['Hisob ma’lumotlari · Tizimdan chiqish', 'Profil sozlamalariga o‘tadi yoki joriy hisobdan xavfsiz chiqadi.'],
    ],
  },
];

export default function AdminGuide() {
  return <div className="page-stack admin-guide">
    <PageHeading eyebrow="YORDAM MARKAZI" title="Administrator uchun qo‘llanma" subtitle="Asosiy jarayonlar va interfeysdagi har bir muhim amal bo‘yicha qisqa yo‘riqnoma." />
    <Alert showIcon type="info" message="Ishni shu tartibda bajaring" description="Avval xonalar va narxlarni sozlang → arizani tekshirib tasdiqlang yoki yashovchini qo‘shing → xonaga joylashtiring → haqiqiy to‘lov va xarajatlarni alohida qayd eting → hisobotlarni tekshiring." />
    <Card className="guide-principles" bordered={false}>
      <Row gutter={[18, 12]}>
        <Col xs={24} md={8}><Tag color="green">Hisob-kitob</Tag><Paragraph>Kelishilgan hisob davri — qarz hisobidir. Yashash muddatini uzaytirish pul tushganini bildirmaydi; haqiqiy pulni “To‘lov qayd etish” orqali kiriting.</Paragraph></Col>
        <Col xs={24} md={8}><Tag color="gold">Erta chiqish</Tag><Paragraph>Chiqish sanasi xona bo‘sh bo‘ladigan kun sifatida olinadi. Joriy hisob va qarz saqlanadi, keyingi hisob davrlari yaratilmaydi. Qaytarim yoki qayta hisob-kitob moliyaviy tuzatish sifatida alohida qayd qilinadi.</Paragraph></Col>
        <Col xs={24} md={8}><Tag color="blue">Tarix</Tag><Paragraph>Arxivlash va xarajatni bekor qilish yozuvni o‘chirmaydi. To‘lov, qaror va o‘zgarishlar tarixini tegishli kartada yoki audit jurnalida ko‘ring.</Paragraph></Col>
      </Row>
    </Card>
    <div className="guide-heading"><Text type="secondary">Tugmalar bo‘yicha yo‘riqnoma</Text><Divider /></div>
    <Row gutter={[16, 16]}>
      {buttonGuides.map((section, index) => <Col xs={24} lg={index === 1 || index === 3 ? 24 : 12} key={section.title}>
        <Card className="guide-card" title={<span><span className="guide-index">{String(index + 1).padStart(2, '0')}</span>{section.title}</span>}>
          <dl>{section.actions.map(([label, detail]) => <div className="guide-action" key={label}><dt>{label}</dt><dd>{detail}</dd></div>)}</dl>
        </Card>
      </Col>)}
    </Row>
    <Alert type="warning" showIcon message="Chiqishdan keyin qarz yoki ortiqcha to‘lovni ko‘rib chiqing" description="Yotoqxona shartnomasiga qarab yakuniy summa farq qilishi mumkin. Tizim chiqish paytida to‘lovni avtomatik qaytarmaydi yoki joriy hisobni kamaytirmaydi; zarur tuzatishni sabab bilan moliyaviy bo‘limda qayd qiling." />
  </div>;
}
