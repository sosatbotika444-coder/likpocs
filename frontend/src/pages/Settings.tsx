import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Popconfirm, Table, Tabs, Tag, notification } from 'antd';
import { api, errorMessage } from '../api';
import type { AuditEvent, Page, SystemSettings, User } from '../types';
import { auditActionLabel, auditDetailLabel, auditEntityLabel, formatDate, uz } from '../locales/uz';
import { useAuth } from '../auth';
import { PageHeading, Panel } from './shared';

type TabKey = 'general' | 'users' | 'audit';
type GeneralForm = { dorm_name: string; default_period_days: number; currency: 'UZS' };
type UserForm = { email?: string; full_name: string; password?: string };

function auditValue(field: string, value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => auditDetailLabel(String(item))).join(', ');
  if (field === 'role' && value === 'ADMIN') return 'Administrator';
  if (field === 'role' && value === 'OPERATOR') return 'Operator';
  if (field === 'method' && typeof value === 'string' && value in uz.paymentMethod) return uz.paymentMethod[value as keyof typeof uz.paymentMethod];
  return String(value);
}

export default function SettingsPage({ initialTab = 'general' }: { initialTab?: TabKey }) {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [tab, setTab] = useState<TabKey>(initialTab);
  const [users, setUsers] = useState<User[]>([]);
  const [audits, setAudits] = useState<AuditEvent[]>([]);
  const [auditTotal, setAuditTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [userModal, setUserModal] = useState(false);
  const [editingUser, setEditingUser] = useState<User | null>(null);
  const [form] = Form.useForm<GeneralForm>();
  const [userForm] = Form.useForm<UserForm>();

  const loadGeneral = async () => {
    setLoading(true); setError('');
    try { const r = await api.get<SystemSettings>('/settings'); form.setFieldsValue(r.data); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  const loadUsers = async () => {
    setLoading(true); setError('');
    try { setUsers((await api.get<User[]>('/users')).data); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  const loadAudit = async () => {
    setLoading(true); setError('');
    try { const r = await api.get<Page<AuditEvent>>('/audit', { params: { limit: 100 } }); setAudits(r.data.items); setAuditTotal(r.data.total); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => {
    if (tab === 'general') void loadGeneral();
    if (tab === 'users' && user?.role === 'OPERATOR') void loadUsers();
    if (tab === 'audit' && user?.role === 'OPERATOR') void loadAudit();
  }, [tab, user?.role]);
  useEffect(() => { if (user?.role !== 'OPERATOR' && tab !== 'general') setTab('general'); }, [user?.role, tab]);

  const saveGeneral = async (values: GeneralForm) => {
    try { await api.put<SystemSettings>('/settings', values); notice.success({ message: 'Sozlamalar saqlandi.' }); }
    catch (e) { notice.error({ message: 'Sozlamalarni saqlab bo‘lmadi', description: errorMessage(e) }); }
  };
  const openUser = (target?: User) => {
    setEditingUser(target || null);
    userForm.setFieldsValue(target ? { full_name: target.full_name, email: target.email, password: '' } : {});
    setUserModal(true);
  };
  const saveUser = async (values: UserForm) => {
    try {
      if (editingUser) {
        const payload: { full_name: string; password?: string } = { full_name: values.full_name };
        if (values.password) payload.password = values.password;
        await api.patch(`/users/${editingUser.id}`, payload);
        notice.success({ message: 'Foydalanuvchi ma’lumotlari yangilandi.' });
      } else {
        await api.post('/users', { ...values, role: 'ADMIN' });
        notice.success({ message: 'Administrator qo‘shildi.' });
      }
      setUserModal(false); setEditingUser(null); userForm.resetFields(); await loadUsers();
    } catch (e) { notice.error({ message: 'Foydalanuvchini saqlab bo‘lmadi', description: errorMessage(e) }); }
  };
  const toggleUser = async (target: User) => {
    try {
      await api.patch(`/users/${target.id}`, { is_active: !target.is_active });
      notice.success({ message: target.is_active ? 'Foydalanuvchi faolsizlantirildi.' : 'Foydalanuvchi faollashtirildi.' });
      await loadUsers();
    } catch (e) { notice.error({ message: errorMessage(e) }); }
  };

  const userColumns = [
    { title: 'Foydalanuvchi', dataIndex: 'full_name', render: (v: string, r: User) => <div className="resident-cell"><span className="person-avatar person-small">{v.split(' ').map((x) => x[0]).slice(0, 2).join('')}</span><span><strong>{v}</strong><small>{r.email}</small></span></div> },
    { title: 'Roli', dataIndex: 'role', render: (v: string) => <Tag>{v === 'OPERATOR' ? 'Operator' : 'Administrator'}</Tag> },
    { title: 'Holati', dataIndex: 'is_active', render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? 'Faol' : 'Faolsiz'}</Tag> },
    { title: 'Qo‘shilgan', dataIndex: 'created_at', render: (v: string) => formatDate(v, true) },
    { title: '', align: 'right' as const, render: (_: unknown, r: User) => r.is_primary ? <Tag color="blue">Asosiy operator</Tag> : <div className="user-actions"><Button type="link" onClick={() => openUser(r)}>Tahrirlash</Button><Popconfirm title={r.is_active ? 'Hisobni faolsizlantirasizmi?' : 'Hisobni faollashtirasizmi?'} okText="Tasdiqlash" cancelText="Bekor qilish" onConfirm={() => void toggleUser(r)}><Button type="link">{r.is_active ? 'Faolsizlantirish' : 'Faollashtirish'}</Button></Popconfirm></div> },
  ];
  const auditColumns = [
    { title: 'Vaqt', dataIndex: 'created_at', width: 180, render: (v: string) => new Intl.DateTimeFormat('uz-UZ', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(v)) },
    { title: 'Foydalanuvchi', dataIndex: 'actor_name', render: (v: string) => v || 'Tizim' },
    { title: 'Amal', dataIndex: 'action', render: (v: string) => <Tag>{auditActionLabel(v)}</Tag> },
    { title: 'Bo‘lim', dataIndex: 'entity_type', render: (v: string) => auditEntityLabel(v) },
    { title: 'Batafsil', dataIndex: 'details', render: (v: Record<string, unknown>) => Object.entries(v || {}).map(([k, val]) => `${auditDetailLabel(k)}: ${auditValue(k, val)}`).join(' · ') || '—' },
  ];

  const generalTab = { key: 'general', label: 'Umumiy', children: <Panel title="Yotoqxona ma’lumotlari"><Form form={form} layout="vertical" onFinish={saveGeneral} className="settings-form"><Form.Item name="dorm_name" label="Yotoqxona nomi" rules={[{ required: true, message: 'Nomini kiriting.' }]}><Input maxLength={160}/></Form.Item><Form.Item name="default_period_days" label="Standart to‘lov davri (kun)" rules={[{ required: true, message: 'Kun sonini kiriting.' }]}><Input type="number" min={1} max={365000}/></Form.Item><Form.Item name="currency" label="Valyuta"><Input disabled/></Form.Item><div className="settings-actions"><Button type="primary" htmlType="submit" disabled={user?.role !== 'OPERATOR'}>O‘zgarishlarni saqlash</Button>{user?.role !== 'OPERATOR' && <span>Sozlamalarni faqat operator o‘zgartira oladi.</span>}</div></Form></Panel> };
  const items = user?.role === 'OPERATOR' ? [
    generalTab,
    { key: 'users', label: 'Foydalanuvchilar', children: <Panel title="Administratorlar" extra={<Button type="primary" onClick={() => openUser()}>Administrator qo‘shish</Button>}><Table rowKey="id" loading={loading} dataSource={users} columns={userColumns} pagination={{ pageSize: 10 }} scroll={{ x: 750 }} locale={{ emptyText: 'Foydalanuvchilar topilmadi' }}/></Panel> },
    { key: 'audit', label: 'Faollik jurnali', children: <Panel title={`Tizimdagi amallar · ${auditTotal} ta`}><Table rowKey="id" loading={loading} dataSource={audits} columns={auditColumns} pagination={{ pageSize: 15 }} scroll={{ x: 900 }} locale={{ emptyText: 'Faollik qaydlari topilmadi' }}/></Panel> },
  ] : [generalTab];

  return <div className="page-stack">{holder}<PageHeading eyebrow="TIZIM BOSHQARUVI" title={tab === 'users' ? 'Foydalanuvchilar' : tab === 'audit' ? 'Faollik jurnali' : 'Sozlamalar'} subtitle="Yotoqxona va tizim boshqaruvi sozlamalari."/>
    {error && <Alert type="error" showIcon message="Ma’lumotni yuklab bo‘lmadi" description={error} action={<Button onClick={() => tab === 'general' ? void loadGeneral() : tab === 'users' ? void loadUsers() : void loadAudit()}>Qayta yuklash</Button>}/>}
    <Tabs activeKey={tab} onChange={(v) => setTab(v as TabKey)} items={items}/>
    <Modal open={userModal} title={editingUser ? 'Administratorni tahrirlash' : 'Administrator qo‘shish'} onCancel={() => { setUserModal(false); setEditingUser(null); userForm.resetFields(); }} onOk={() => userForm.submit()} okText={editingUser ? 'O‘zgarishlarni saqlash' : 'Foydalanuvchi yaratish'} cancelText="Bekor qilish" destroyOnClose>
      <Form form={userForm} layout="vertical" onFinish={saveUser}><Form.Item name="full_name" label="To‘liq ism" rules={[{ required: true, min: 2, message: 'Ismni kiriting.' }]}><Input/></Form.Item>
        {!editingUser && <Form.Item name="email" label="Elektron pochta" rules={[{ required: true, type: 'email', message: 'To‘g‘ri elektron pochta kiriting.' }]}><Input type="email"/></Form.Item>}
        <Form.Item name="password" label={editingUser ? 'Yangi parol (ixtiyoriy)' : 'Vaqtinchalik parol'} extra="Parol kamida 12 ta belgidan iborat bo‘lishi kerak." rules={[{ required: !editingUser, min: 12, message: 'Parol kamida 12 ta belgidan iborat bo‘lsin.' }]}><Input.Password autoComplete="new-password"/></Form.Item>
      </Form>
    </Modal>
  </div>;
}
