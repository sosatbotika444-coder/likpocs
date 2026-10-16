import { useEffect, useState } from 'react';
import { Alert, Button, DatePicker, Descriptions, Drawer, Form, Input, InputNumber, Modal, Popconfirm, Select, Table, Tag, Typography, notification } from 'antd';
import { EditOutlined, EyeOutlined, SwapOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { api, errorMessage } from '../api';
import type { BillingPeriod, Page, Payment, Resident, ResidentDetail, Room, SystemSettings } from '../types';
import { formatDate, formatMoney, statusLabel } from '../locales/uz';
import { useAuth } from '../auth';
import { Actions, PageHeading } from './shared';

const { Text } = Typography;
type ResidentForm = {
  first_name: string; last_name: string; phone?: string; telegram_username?: string; room_id?: string;
  check_in_date?: dayjs.Dayjs | null; billing_start?: dayjs.Dayjs | null; billing_end?: dayjs.Dayjs | null;
  payment_period_days?: number; agreed_price?: number; notes?: string;
};

function cleanDate(value?: dayjs.Dayjs | null) { return value?.format('YYYY-MM-DD') || null; }
function statusTag(status: string) { return <Tag className={`status-tag status-${status.toLowerCase()}`}>{statusLabel(status)}</Tag>; }

export default function Residents() {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [rows, setRows] = useState<Resident[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [billingAllowed, setBillingAllowed] = useState(false);
  const [defaultPeriodDays, setDefaultPeriodDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [roomId, setRoomId] = useState<string>();
  const [showArchived, setShowArchived] = useState(false);
  const [editor, setEditor] = useState<Resident | null | false>(false);
  const [form] = Form.useForm<ResidentForm>();
  const [saving, setSaving] = useState(false);
  const [detail, setDetail] = useState<ResidentDetail | null>(null);
  const [residentPayments, setResidentPayments] = useState<Payment[]>([]);
  const [extension, setExtension] = useState<Resident | null>(null);
  const [extensionForm] = Form.useForm();

  const load = async () => {
    setLoading(true); setError('');
    try {
      const params = { q: search || undefined, payment_status: status, room_id: roomId, archived: showArchived, limit: 500 };
      const [people, roomList, settings] = await Promise.all([api.get<Page<Resident>>('/residents', { params }), api.get<Page<Room>>('/rooms', { params: { limit: 500 } }), api.get<SystemSettings>('/settings')]);
      setRows(people.data.items); setRooms(roomList.data.items); setBillingAllowed(settings.data.billing_change_allowed); setDefaultPeriodDays(settings.data.default_period_days);
    } catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { const timer = setTimeout(() => { void load(); }, 250); return () => clearTimeout(timer); }, [search, status, roomId, showArchived]);

  const openEditor = (resident?: Resident) => {
    setEditor(resident || null);
    form.setFieldsValue(resident ? {
      ...resident,
      phone: resident.phone ?? undefined,
      telegram_username: resident.telegram_username ?? undefined,
      room_id: resident.room_id ?? undefined,
      payment_period_days: resident.payment_period_days ?? undefined,
      agreed_price: resident.agreed_price ?? undefined,
      notes: resident.notes ?? undefined,
      check_in_date: resident.check_in_date ? dayjs(resident.check_in_date) : undefined,
      billing_start: resident.billing_start ? dayjs(resident.billing_start) : undefined,
      billing_end: resident.billing_end ? dayjs(resident.billing_end) : undefined,
    } : { payment_period_days: defaultPeriodDays });
  };

  const save = async (values: ResidentForm) => {
    setSaving(true);
    const body = {
      first_name: values.first_name.trim(), last_name: values.last_name.trim(),
      phone: values.phone?.trim() || null, telegram_username: values.telegram_username?.trim().replace(/^@/, '') || null,
      room_id: values.room_id || null, check_in_date: cleanDate(values.check_in_date),
      ...(user?.role === 'OPERATOR' || billingAllowed ? { payment_period_days: values.payment_period_days || null, agreed_price: values.agreed_price ?? null, billing_start: cleanDate(values.billing_start), billing_end: cleanDate(values.billing_end) } : {}),
      notes: values.notes || '',
    };
    try {
      if (editor) await api.patch(`/residents/${editor.id}`, body); else await api.post('/residents', body);
      notice.success({ message: editor ? 'Yashovchi ma’lumotlari saqlandi.' : 'Yashovchi qo‘shildi.' }); setEditor(false); form.resetFields(); await load();
    } catch (e) { notice.error({ message: 'Saqlab bo‘lmadi', description: errorMessage(e) }); }
    finally { setSaving(false); }
  };

  const showDetail = async (person: Resident) => {
    try {
      const [r, p] = await Promise.all([api.get<ResidentDetail>(`/residents/${person.id}`), api.get<Payment[]>(`/residents/${person.id}/payments`)]);
      setDetail(r.data); setResidentPayments(p.data);
    } catch (e) { notice.error({ message: 'Yashovchi ma’lumotlarini yuklab bo‘lmadi', description: errorMessage(e) }); }
  };

  const archive = async (person: Resident) => {
    try { await api.post(`/residents/${person.id}/archive`); notice.success({ message: 'Yashovchi arxivlandi.' }); await load(); }
    catch (e) { notice.error({ message: errorMessage(e) }); }
  };
  const restore = async (person: Resident) => {
    try { await api.post(`/residents/${person.id}/restore`); notice.success({ message: 'Yashovchi tiklandi.' }); await load(); }
    catch (e) { notice.error({ message: 'Yashovchini tiklab bo‘lmadi', description: errorMessage(e) }); }
  };
  const extend = async (values: { days?: number | null; end_date?: dayjs.Dayjs | null; reason?: string }) => {
    if (!extension) return;
    try {
      await api.post(`/residents/${extension.id}/extend`, { days: values.days || undefined, end_date: values.end_date?.format('YYYY-MM-DD'), reason: values.reason || '' });
      notice.success({ message: 'Yashash muddati uzaytirildi. Bu amal to‘lov sifatida qayd etilmadi.' }); setExtension(null); extensionForm.resetFields(); await load();
      if (detail?.id === extension.id) await showDetail(extension);
    } catch (e) { notice.error({ message: 'Muddatni uzaytirib bo‘lmadi', description: errorMessage(e) }); }
  };

  const columns = [
    { title: 'Yashovchi', dataIndex: 'first_name', sorter: (a: Resident, b: Resident) => a.last_name.localeCompare(b.last_name), render: (_: string, r: Resident) => <div className="resident-cell"><span className="person-avatar">{r.first_name[0]}{r.last_name[0]}</span><span><strong>{r.first_name} {r.last_name}</strong><small>{r.phone || r.telegram_username && `@${r.telegram_username}` || 'Aloqa ma’lumoti yo‘q'}</small></span></div> },
    { title: 'Xona', dataIndex: 'room_number', render: (v: string | null) => v ? <span className="room-pill">{v}</span> : <Text type="secondary">Tayinlanmagan</Text> },
    { title: 'To‘lov holati', dataIndex: 'billing_status', render: (v: string) => statusTag(v) },
    { title: 'Muddat', dataIndex: 'billing_end', render: (v: string | null) => formatDate(v) },
    { title: 'Qarzdorlik', dataIndex: 'balance', align: 'right' as const, render: (v: number) => <strong className={v > 0 ? 'text-danger' : ''}>{formatMoney(v)}</strong> },
    { title: '', key: 'actions', align: 'right' as const, render: (_: unknown, r: Resident) => <Actions><Button type="text" icon={<EyeOutlined />} aria-label="Batafsil" onClick={() => void showDetail(r)}/>{!showArchived && <><Button type="text" icon={<EditOutlined />} aria-label="Tahrirlash" onClick={() => openEditor(r)}/>{(user?.role === 'OPERATOR' || billingAllowed) && <Button type="text" icon={<SwapOutlined />} aria-label="Muddatni uzaytirish" onClick={() => { setExtension(r); extensionForm.setFieldsValue({ days: r.payment_period_days || 30 }); }}/>}<Popconfirm title="Yashovchini arxivlaysizmi?" description="To‘lovlar tarixi saqlanadi." okText="Arxivlash" cancelText="Bekor qilish" onConfirm={() => void archive(r)}><Button type="text" danger aria-label="Arxivlash">Arxiv</Button></Popconfirm></>}{showArchived && user?.role === 'OPERATOR' && <Popconfirm title="Yashovchini tiklaysizmi?" okText="Tiklash" cancelText="Bekor qilish" onConfirm={() => void restore(r)}><Button type="text">Tiklash</Button></Popconfirm>}</Actions> },
  ];

  return <div className="page-stack">{holder}
    <PageHeading eyebrow="YASHASH JOYI HISOBI" title="Yashovchilar" subtitle="Yashovchilar, joylashuv va to‘lov davrlarini boshqaring." action="Yashovchi qo‘shish" onAction={() => openEditor()} />
    {error && <Alert type="error" showIcon message="Ro‘yxatni yuklab bo‘lmadi" description={error} action={<Button size="small" onClick={() => void load()}>Qayta yuklash</Button>} />}
    <div className="toolbar panel"><Input.Search allowClear placeholder="Ism, xona, telefon yoki Telegram bo‘yicha qidirish" value={search} onChange={(e) => setSearch(e.target.value)} className="search-input"/><Select value={status} onChange={setStatus} options={[{value:'all',label:'Barcha holatlar'},{value:'CURRENT',label:'Amalda'},{value:'DUE_SOON',label:'Yaqinlashmoqda'},{value:'DUE_TODAY',label:'Bugun to‘lanadi'},{value:'OVERDUE',label:'Muddati o‘tgan'},{value:'PAID',label:'To‘langan'},{value:'NOT_CONFIGURED',label:'Davr belgilanmagan'}]} /><Select allowClear placeholder="Barcha xonalar" value={roomId} onChange={setRoomId} options={rooms.map((r) => ({ value: r.id, label: `Xona ${r.number}` }))}/><Select value={showArchived} onChange={setShowArchived} options={[{value:false,label:'Faol yashovchilar'},{value:true,label:'Arxivdagilar'}]}/><span className="toolbar-count">Jami: <strong>{rows.length}</strong></span></div>
    <div className="panel table-panel"><Table rowKey="id" loading={loading} columns={columns} dataSource={rows} scroll={{ x: 850 }} pagination={{ pageSize: 10, showSizeChanger: true, showTotal: (n) => `Jami ${n} ta` }} locale={{ emptyText: 'Yashovchilar ro‘yxati bo‘sh' }} /></div>

    <Modal open={editor !== false} title={editor ? 'Yashovchini tahrirlash' : 'Yangi yashovchi'} onCancel={() => { setEditor(false); form.resetFields(); }} onOk={() => form.submit()} confirmLoading={saving} okText="Saqlash" cancelText="Bekor qilish" width={700} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={save} className="resident-form"><div className="form-grid"><Form.Item name="first_name" label="Ism" rules={[{required:true,message:'Ismni kiriting.'}]}><Input autoFocus maxLength={80}/></Form.Item><Form.Item name="last_name" label="Familiya" rules={[{required:true,message:'Familiyani kiriting.'}]}><Input maxLength={100}/></Form.Item><Form.Item name="phone" label="Telefon raqami"><Input placeholder="+998 90 123 45 67"/></Form.Item><Form.Item name="telegram_username" label="Telegram foydalanuvchi nomi"><Input placeholder="@foydalanuvchi"/></Form.Item><Form.Item name="room_id" label="Xona"><Select allowClear placeholder="Xona tanlang" options={rooms.filter((r) => r.available_beds > 0 || r.id === (editor && editor.room_id)).map((r) => ({value:r.id,label:`${r.number}-xona · ${r.available_beds} ta bo‘sh joy`}))}/></Form.Item><Form.Item name="check_in_date" label="Ko‘chib kirgan sana"><DatePicker className="full-width" format="DD.MM.YYYY"/></Form.Item>
        {(user?.role === 'OPERATOR' || billingAllowed) && <><Form.Item name="payment_period_days" label="To‘lov davri (kun)" extra="Istalgan musbat kun sonini kiriting."><InputNumber min={1} max={365000} className="full-width"/></Form.Item><Form.Item name="agreed_price" label="Kelishilgan narx (so‘m)"><InputNumber min={0} className="full-width" controls={false}/></Form.Item><Form.Item name="billing_start" label="Davr boshlanishi"><DatePicker className="full-width" format="DD.MM.YYYY"/></Form.Item><Form.Item name="billing_end" label="Davr tugashi"><DatePicker className="full-width" format="DD.MM.YYYY"/></Form.Item></>}
        <Form.Item name="notes" label="Izoh" className="form-span"><Input.TextArea rows={3} maxLength={5000}/></Form.Item></div></Form>
    </Modal>

    <Drawer title={detail ? `${detail.first_name} ${detail.last_name}` : 'Yashovchi'} open={Boolean(detail)} onClose={() => setDetail(null)} width={620} extra={detail && <Button icon={<EditOutlined/>} onClick={() => { const row = rows.find((r) => r.id === detail.id); if (row) openEditor(row); }}>Tahrirlash</Button>}>
      {detail && <div className="detail-stack"><Descriptions bordered size="small" column={2} items={[{key:'room',label:'Xona',children:detail.room_number || 'Tayinlanmagan'},{key:'status',label:'Holat',children:statusTag(detail.billing_status)},{key:'phone',label:'Telefon',children:detail.phone || '—'},{key:'telegram',label:'Telegram',children:detail.telegram_username ? `@${detail.telegram_username}` : '—'},{key:'period',label:'Davr',children:detail.payment_period_days ? `${detail.payment_period_days} kun` : 'Belgilanmagan'},{key:'price',label:'Kelishilgan narx',children:formatMoney(detail.agreed_price)},{key:'dates',label:'To‘lov davri',children:`${formatDate(detail.billing_start)} — ${formatDate(detail.billing_end)}`},{key:'debt',label:'Qarzdorlik',children:formatMoney(detail.balance)}]}/>
        <section><h3>To‘lovlar tarixi</h3><Table size="small" rowKey="id" dataSource={residentPayments} pagination={false} scroll={{x:450}} columns={[{title:'Sana',dataIndex:'payment_date',render:(v:string)=>formatDate(v)},{title:'Usul',dataIndex:'method',render:(v:string)=>({CASH:'Naqd pul',BANK:'Bank o‘tkazmasi',CLICK:'Click',PAYME:'Payme',OTHER:'Boshqa'}[v]||v)},{title:'Summa',dataIndex:'net_amount',align:'right',render:(v:number)=>formatMoney(v)}]} locale={{emptyText:'To‘lovlar tarixi mavjud emas'}}/></section>
        <section><h3>To‘lov davrlari</h3><Table size="small" rowKey="id" dataSource={detail.billing_history as BillingPeriod[]} pagination={false} scroll={{x:460}} columns={[{title:'Davr',render:(_:unknown,p:BillingPeriod)=>`${formatDate(p.start_date)} — ${formatDate(p.end_date)}`},{title:'Hisoblangan',dataIndex:'charge_amount',render:formatMoney},{title:'Qoldiq',dataIndex:'balance',render:formatMoney},{title:'Holat',dataIndex:'status',render:statusTag}]} locale={{emptyText:'Davrlar sozlanmagan'}}/></section>
        {detail.notes && <div className="notes-box"><strong>Izoh</strong><p>{detail.notes}</p></div>}</div>}
    </Drawer>
    <Modal open={Boolean(extension)} title="Yashash muddatini uzaytirish" onCancel={() => setExtension(null)} onOk={() => extensionForm.submit()} okText="Muddatni saqlash" cancelText="Bekor qilish" destroyOnClose>
      <Alert type="info" showIcon message="Muddat uzaytirish to‘lov hisoblanmaydi. Haqiqiy to‘lovni alohida qayd eting." className="modal-alert"/>
      <Form form={extensionForm} layout="vertical" onFinish={extend} className="extension-form"><Form.Item name="days" label="Qo‘shimcha kunlar"><InputNumber min={1} max={365000} className="full-width"/></Form.Item><div className="or-separator">yoki aniq tugash sanasi</div><Form.Item name="end_date" label="Yangi tugash sanasi"><DatePicker className="full-width" format="DD.MM.YYYY"/></Form.Item><Form.Item name="reason" label="Izoh"><Input.TextArea rows={2}/></Form.Item></Form>
    </Modal>
  </div>;
}
