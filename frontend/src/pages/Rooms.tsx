import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, InputNumber, Modal, Popconfirm, Progress, Select, Table, Tag, notification } from 'antd';
import { EditOutlined } from '@ant-design/icons';
import { api, errorMessage } from '../api';
import type { Dormitory, Page, Room } from '../types';
import { formatMoney } from '../locales/uz';
import { useAuth } from '../auth';
import { Actions, PageHeading } from './shared';

type RoomForm = { number: string; dormitory_id?: string; floor: number; capacity: number; price?: number; notes?: string };

export default function Rooms() {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [rows, setRows] = useState<Room[]>([]);
  const [dormitories, setDormitories] = useState<Dormitory[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [status, setStatus] = useState('all');
  const [editor, setEditor] = useState<Room | null | false>(false);
  const [form] = Form.useForm<RoomForm>();
  const [saving, setSaving] = useState(false);

  const load = async () => {
    setLoading(true); setError('');
    try { setRows((await api.get<Page<Room>>('/rooms', { params: { status, limit: 500 } })).data.items); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [status]);
  useEffect(() => { void api.get<Dormitory[]>('/dormitories', { params: { include_inactive: user?.role === 'OPERATOR' } }).then((result) => setDormitories(result.data)).catch(() => setDormitories([])); }, [user?.role]);

  const edit = (room?: Room) => { setEditor(room || null); form.setFieldsValue(room ? { number: room.number, dormitory_id: room.dormitory_id, floor: room.floor, capacity: room.capacity, price: room.price ?? undefined, notes: room.notes } : { dormitory_id: dormitories.find((item)=>item.is_active)?.id, floor: 1, capacity: 4 }); };
  const save = async (values: RoomForm) => {
    setSaving(true);
    try {
      if (editor) await api.patch(`/rooms/${editor.id}`, values); else await api.post('/rooms', values);
      notice.success({ message: editor ? 'Xona ma’lumotlari saqlandi.' : 'Xona yaratildi.' }); setEditor(false); form.resetFields(); await load();
    } catch (e) { notice.error({ message: 'Xonani saqlab bo‘lmadi', description: errorMessage(e) }); }
    finally { setSaving(false); }
  };
  const archive = async (room: Room) => {
    try { await api.delete(`/rooms/${room.id}`); notice.success({ message: 'Xona arxivlandi.' }); await load(); }
    catch (e) { notice.error({ message: 'Xonani arxivlab bo‘lmadi', description: errorMessage(e) }); }
  };

  const columns = [
    { title: 'Yotoqxona', dataIndex: 'dormitory_id', render: (id: string) => dormitories.find((item) => item.id === id)?.name || '—' },
    { title: 'Xona', dataIndex: 'number', render: (v: string, r: Room) => <div className="room-cell"><span className="room-icon">⌂</span><span><strong>{v}-xona</strong><small>{r.floor}-qavat</small></span></div> },
    { title: 'Bandlik', dataIndex: 'resident_count', width: 240, render: (_: number, r: Room) => <div className="occupancy-cell"><div><strong>{r.resident_count}</strong><span> / {r.capacity} o‘rin</span></div><Progress percent={Math.round(r.resident_count / r.capacity * 100)} showInfo={false} strokeColor={r.available_beds ? '#34745b' : '#c57947'} size="small"/></div> },
    { title: 'Bo‘sh o‘rinlar', dataIndex: 'available_beds', render: (v: number) => <Tag color={v ? 'green' : 'default'}>{v} ta</Tag> },
    { title: 'Bir o‘rin narxi / davr', dataIndex: 'price', render: (v: number | null) => v == null ? '—' : formatMoney(v) },
    { title: 'Holat', render: (_: unknown, r: Room) => r.available_beds ? <Tag className="status-tag status-current">Joy bor</Tag> : <Tag className="status-tag status-overdue">To‘la</Tag> },
    { title: '', align: 'right' as const, render: (_: unknown, r: Room) => <Actions><Button type="text" icon={<EditOutlined/>} aria-label="Tahrirlash" onClick={() => edit(r)}/>{user?.role === 'OPERATOR' && <Popconfirm title="Xonani arxivlaysizmi?" description="Yashovchilar birinchi bo‘lib boshqa xonaga ko‘chirilishi kerak." okText="Arxivlash" cancelText="Bekor qilish" onConfirm={() => void archive(r)}><Button type="text" danger>Arxiv</Button></Popconfirm>}</Actions> },
  ];

  return <div className="page-stack">{holder}
    <PageHeading eyebrow="JOYLASHTIRISH" title="Xonalar" subtitle="Sig‘im, bandlik va bo‘sh o‘rinlarni kuzating." action="Xona qo‘shish" onAction={() => edit()} />
    {error && <Alert type="error" showIcon message="Xonalarni yuklab bo‘lmadi" description={error} action={<Button onClick={() => void load()}>Qayta yuklash</Button>}/>}
    <div className="toolbar panel"><span className="toolbar-label">Xona holati</span><Select value={status} onChange={setStatus} options={[{value:'all',label:'Barcha xonalar'},{value:'available',label:'Bo‘sh joy bor'},{value:'full',label:'To‘liq band'}]}/><span className="toolbar-count">Jami: <strong>{rows.length}</strong></span></div>
    <div className="panel table-panel"><Table rowKey="id" loading={loading} dataSource={rows} columns={columns} scroll={{x:750}} pagination={{pageSize:10,showTotal:(n)=>`Jami ${n} ta`}} locale={{emptyText:'Xonalar ro‘yxati bo‘sh'}}/></div>
    <Modal open={editor !== false} title={editor ? 'Xonani tahrirlash' : 'Yangi xona'} onCancel={() => {setEditor(false);form.resetFields();}} onOk={() => form.submit()} confirmLoading={saving} okText="Saqlash" cancelText="Bekor qilish" destroyOnClose>
      <Form form={form} layout="vertical" onFinish={save}><div className="form-grid"><Form.Item name="dormitory_id" label="Yotoqxona" rules={[{required:true,message:"Yotoqxonani tanlang."}]}><Select options={dormitories.filter((item)=>item.is_active).map((item)=>({value:item.id,label:item.name}))}/></Form.Item><Form.Item name="number" label="Xona raqami" rules={[{required:true,message:'Xona raqamini kiriting.'}]}><Input maxLength={32}/></Form.Item><Form.Item name="floor" label="Qavat" rules={[{required:true,message:'Qavatni kiriting.'}]}><InputNumber min={0} className="full-width"/></Form.Item><Form.Item name="capacity" label="Sig‘imi (o‘rin)" rules={[{required:true,message:'Sig‘imni kiriting.'}]}><InputNumber min={1} max={500} className="full-width"/></Form.Item><Form.Item name="price" label="Bir o‘rin narxi (so‘m / to‘lov davri)" extra="Ariza tasdiqlanganda shu tarif hisobga olinadi. To‘lov davri tizim sozlamasidan olinadi."><InputNumber min={0} controls={false} className="full-width"/></Form.Item><Form.Item name="notes" label="Izoh" className="form-span"><Input.TextArea rows={3}/></Form.Item></div></Form>
    </Modal>
  </div>;
}
