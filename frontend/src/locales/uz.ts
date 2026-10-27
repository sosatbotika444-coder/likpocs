export const uz = {
  brand: { name: 'RS Best Hostel', subtitle: 'yotoqxona boshqaruvi' },
  nav: {
    dashboard: 'Boshqaruv paneli', residents: 'Yashovchilar', rooms: 'Xonalar',
    payments: 'To‘lovlar', expenses: 'Xarajatlar', reports: 'Hisobotlar', settings: 'Sozlamalar',
    users: 'Foydalanuvchilar', audit: 'Faollik jurnali',
    admissions: 'Qabul',
  },
  common: {
    add: 'Qo‘shish', create: 'Yaratish', save: 'Saqlash', cancel: 'Bekor qilish',
    edit: 'Tahrirlash', archive: 'Arxivlash', restore: 'Tiklash', search: 'Qidirish',
    filter: 'Filtrlash', clear: 'Tozalash', export: 'Yuklab olish', loading: 'Yuklanmoqda…',
    retry: 'Qayta urinish', actions: 'Amallar', details: 'Batafsil', all: 'Barchasi',
    yes: 'Ha', no: 'Yo‘q', today: 'Bugun', noData: 'Ma’lumot topilmadi',
    confirmArchive: 'Arxivga ko‘chirilsinmi? Tarixiy to‘lovlar saqlanadi.',
    confirmDeactivate: 'Foydalanuvchini faolsizlantirasizmi?',
  },
  status: {
    PAID: 'To‘langan', CURRENT: 'Amalda', DUE_SOON: 'Yaqinlashmoqda',
    DUE_TODAY: 'Bugun to‘lanadi', OVERDUE: 'Muddati o‘tgan',
    NOT_CONFIGURED: 'Davr yoki narx belgilanmagan', OPEN: 'Ochiq', CLOSED: 'Yopilgan',
  },
  role: { OPERATOR: 'Operator', ADMIN: 'Administrator' },
  paymentMethod: { CASH: 'Naqd pul', BANK: 'Bank o‘tkazmasi', CLICK: 'Click', PAYME: 'Payme', OTHER: 'Boshqa' },
  paymentMethods: [
    { value: 'CASH', label: 'Naqd pul' }, { value: 'BANK', label: 'Bank o‘tkazmasi' },
    { value: 'CLICK', label: 'Click' }, { value: 'PAYME', label: 'Payme' }, { value: 'OTHER', label: 'Boshqa' },
  ],
  validation: {
    required: 'Bu maydonni to‘ldirish shart.',
    positiveInteger: 'Musbat butun son kiriting.',
    positiveAmount: 'Summani noldan katta kiriting.',
    dateOrder: 'Tugash sanasi boshlanish sanasidan keyin bo‘lishi kerak.',
  },
  login: {
    eyebrow: 'RS BEST HOSTEL · ISH BOSHQARUVI', title: 'Yotoqxona ishlarini bir joyda yuriting.',
    subtitle: 'Yashovchilar, xonalar, qabul va hisob-kitoblar uchun kundalik ish maydoni.', email: 'Elektron pochta',
    password: 'Parol', submit: 'Tizimga kirish', security: 'Xavfsiz boshqaruv muhiti',
  },
  dashboard: {
    eyebrow: 'XUSH KELIBSIZ', title: 'Ishlar maromida', subtitle: 'Bugungi muhim ko‘rsatkichlar bir joyda.',
    residents: 'Yashovchilar', rooms: 'Xonalar', occupancy: 'Bandlik', availableBeds: 'Bo‘sh o‘rinlar',
    dueToday: 'Bugun to‘lanadi', dueSoon: 'Yaqin to‘lovlar', overdue: 'Muddati o‘tgan',
    revenue: 'Joriy oy tushumi', expected: 'Kutilayotgan to‘lovlar', debt: 'Qarzdorlik',
    revenueTrend: 'Haqiqiy tushum', occupancyByRoom: 'Xonalar bandligi',
    recentPayments: 'So‘nggi to‘lovlar', newResidents: 'Yangi yashovchilar',
    attention: 'E’tibor talab qiladi', seeAll: 'Barchasini ko‘rish',
  },
  audit: {
    action: {
      LOGIN: 'Tizimga kirdi', OPERATOR_BOOTSTRAPPED: 'Asosiy operator yaratildi',
      USER_CREATED: 'Foydalanuvchi yaratildi', USER_UPDATED: 'Foydalanuvchi yangilandi',
      ROOM_CREATED: 'Xona yaratildi', ROOM_UPDATED: 'Xona yangilandi', ROOM_ARCHIVED: 'Xona arxivlandi',
      RESIDENT_CREATED: 'Yashovchi qo‘shildi', RESIDENT_UPDATED: 'Yashovchi ma’lumoti yangilandi',
      RESIDENT_ARCHIVED: 'Yashovchi arxivlandi', RESIDENT_RESTORED: 'Yashovchi tiklandi',
      BILLING_CYCLE_CREATED: 'To‘lov davri yaratildi', BILLING_PERIOD_CREATED: 'To‘lov jadvali sozlandi',
      BILLING_SCHEDULE_CHANGED: 'To‘lov jadvali o‘zgartirildi', BILLING_PRICE_CHANGED: 'Kelishilgan narx o\u2018zgartirildi', BILLING_EXTENDED: 'Yashash muddati uzaytirildi',
      PAYMENT_RECORDED: 'To‘lov qayd etildi', EXPENSE_RECORDED: 'Xarajat qayd etildi', EXPENSE_VOIDED: 'Xarajat bekor qilindi', PAYMENT_ADJUSTED: 'To‘lovga tuzatish kiritildi',
      SETTINGS_UPDATED: 'Sozlamalar yangilandi',
    },
    entity: { User: 'Foydalanuvchi', Room: 'Xona', Resident: 'Yashovchi', BillingPeriod: 'To‘lov davri', Payment: 'To‘lov', SystemSetting: 'Tizim sozlamasi', Expense: 'Xarajat' },
    fields: {
      name: 'Ism-familiya', email: 'Elektron pochta', role: 'Rol', changed_fields: 'O‘zgargan maydonlar',
      number: 'Xona raqami', resident_id: 'Yashovchi raqami', amount: 'Summa', amount_delta: 'Tuzatish summasi',
      method: 'To‘lov usuli', adjustment_id: 'Tuzatish raqami', reason: 'Sabab', days_added: 'Qo‘shimcha kun',
      old_end: 'Avvalgi tugash sanasi', new_end: 'Yangi tugash sanasi', old_amount: 'Avvalgi summa', new_amount: 'Yangi summa', category: 'Toifa', dorm_name: 'Yotoqxona nomi',
      first_name: 'Ism', last_name: 'Familiya', phone: 'Telefon', telegram_username: 'Telegram nomi',
      room_id: 'Xona raqami', check_in_date: 'Ko‘chib kirgan sana', billing_start: 'Davr boshlanishi',
      billing_end: 'Davr tugashi', payment_period_days: 'To‘lov davri', agreed_price: 'Kelishilgan narx', notes: 'Izoh',
    },
  },
} as const;

export type PaymentMethod = keyof typeof uz.paymentMethod;
export type BillingStatus = keyof typeof uz.status;

function moneyToMinorUnits(value: number | string | null | undefined): bigint {
  const match = /^(-?)(\d+)(?:[.,](\d+))?$/.exec(String(value ?? 0).trim());
  if (!match) return 0n;
  const units = BigInt(match[2]) * 100n + BigInt((match[3] ?? '').padEnd(2, '0').slice(0, 2));
  return match[1] ? -units : units;
}

export function isPositiveMoney(value: number | string | null | undefined): boolean {
  return moneyToMinorUnits(value) > 0n;
}

export function sumMoney(values: (number | string | null | undefined)[]): string {
  const total = values.reduce((sum, value) => sum + moneyToMinorUnits(value), 0n);
  const sign = total < 0n ? '-' : '';
  const absolute = total < 0n ? -total : total;
  return `${sign}${absolute / 100n}.${(absolute % 100n).toString().padStart(2, '0')}`;
}

export function formatMoney(value: number | string | null | undefined): string {
  const raw = String(value ?? 0).trim();
  const match = /^(-?)(\d+)(?:[.,](\d+))?$/.exec(raw);
  if (!match) return `${new Intl.NumberFormat('uz-UZ', { maximumFractionDigits: 2 }).format(Number(value ?? 0))} so'm`;
  const whole = new Intl.NumberFormat('uz-UZ', { maximumFractionDigits: 0 }).format(Number(match[2]));
  const decimal = new Intl.NumberFormat('uz-UZ').formatToParts(1.1).find((part) => part.type === 'decimal')?.value ?? ',';
  const fraction = (match[3] ?? '').padEnd(2, '0').slice(0, 2);
  return `${match[1]}${whole}${decimal}${fraction} so'm`;
}

export function formatDate(value?: string | null, withYear = false): string {
  if (!value) return '—';
  const parts = value.slice(0, 10).split('-').map(Number);
  if (parts.length !== 3 || parts.some(Number.isNaN)) return '—';
  return new Intl.DateTimeFormat('uz-UZ', { day: 'numeric', month: 'short', ...(withYear ? { year: 'numeric' } : {}) }).format(new Date(parts[0], parts[1] - 1, parts[2], 12));
}

export function todayUzbekistan(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tashkent', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
}

export function statusLabel(status: string): string {
  return status in uz.status ? uz.status[status as keyof typeof uz.status] : status;
}

export function auditActionLabel(action: string): string {
  return action in uz.audit.action ? uz.audit.action[action as keyof typeof uz.audit.action] : 'Boshqa amal';
}

export function auditEntityLabel(entity: string): string {
  return entity in uz.audit.entity ? uz.audit.entity[entity as keyof typeof uz.audit.entity] : 'Boshqa bo‘lim';
}

export function auditDetailLabel(field: string): string {
  return field in uz.audit.fields ? uz.audit.fields[field as keyof typeof uz.audit.fields] : 'Qo‘shimcha ma’lumot';
}
