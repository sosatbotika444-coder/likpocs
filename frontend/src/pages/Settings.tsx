import { useEffect, useState } from 'react';
import { Alert, Button, Form, Input, Modal, Popconfirm, Select, Table, Tabs, Tag, notification } from 'antd';
import { api, errorMessage } from '../api';
import type { AuditEvent, OperatorContractSignature, Page, SystemSettings, TelegramLinkCode, TelegramStatus, User } from '../types';
import { auditActionLabel, auditDetailLabel, auditEntityLabel, formatDate, uz } from '../locales/uz';
import { useAuth } from '../auth';
import { PageHeading, Panel } from './shared';

type TabKey = 'general' | 'users' | 'audit' | 'telegram';
type GeneralForm = { dorm_name: string; default_period_days: number; currency: 'UZS' };
type OperatorSignatureForm = { full_name: string };
type UserForm = { email?: string; full_name: string; password?: string; role?: 'ADMIN' | 'INVESTOR' };

function TelegramPanel() {
  const [notice, holder] = notification.useNotification();
  const [status, setStatus] = useState<TelegramStatus | null>(null);
  const [code, setCode] = useState<TelegramLinkCode | null>(null);
  const load = async () => { try { setStatus((await api.get<TelegramStatus>('/telegram/status')).data); } catch (e) { notice.error({ message: errorMessage(e) }); } };
  useEffect(() => { void load(); }, []);
  const issue = async () => { try { setCode((await api.post<TelegramLinkCode>('/telegram/link-code')).data); } catch (e) { notice.error({ message: errorMessage(e) }); } };
  const unlink = async () => { try { await api.delete('/telegram/link'); setCode(null); await load(); } catch (e) { notice.error({ message: errorMessage(e) }); } };
  return <Panel title={uz.telegram.title}>{holder}
    <p>{uz.telegram.subtitle}</p>
    {status && !status.configured && <Alert type="warning" showIcon message={uz.telegram.notConfigured} />}
    {status && <p><Tag color={status.linked ? 'green' : 'default'}>{status.linked ? uz.telegram.linked : uz.telegram.notLinked}</Tag>{status.username && `@${status.username}`}</p>}
    <div className="settings-actions">
      <Button type="primary" disabled={!status?.configured} onClick={() => void issue()}>{uz.telegram.getCode}</Button>
      {status?.linked && <Popconfirm title={uz.telegram.unlink + '?'} okText="Ha" cancelText="Yo‘q" onConfirm={() => void unlink()}><Button danger>{uz.telegram.unlink}</Button></Popconfirm>}
    </div>
    {code && <Alert style={{ marginTop: 12 }} type="info" showIcon message={<strong style={{ fontSize: 22, letterSpacing: 3 }}>{code.code}</strong>}
      description={<>{uz.telegram.steps}<br />{uz.telegram.expires}: {new Intl.DateTimeFormat('uz-UZ', { timeStyle: 'short', timeZone: 'Asia/Tashkent' }).format(new Date(code.expires_at))}
        {code.link && <><br /><a href={code.link} target="_blank" rel="noreferrer">{uz.telegram.openBot}</a></>}</>} />}
  </Panel>;
}

function auditValue(field: string, value: unknown): string {
  if (Array.isArray(value)) return value.map((item) => auditDetailLabel(String(item))).join(', ');
  if (field === 'role' && value === 'INVESTOR') return 'Investor';
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
  const [operatorSignatureForm] = Form.useForm<OperatorSignatureForm>();
  const [userForm] = Form.useForm<UserForm>();

  const loadGeneral = async () => {
    setLoading(true); setError('');
    try { const r = await api.get<SystemSettings>('/settings'); form.setFieldsValue(r.data); }
    catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  const loadOperatorSignature = async () => {
    try { const r = await api.get<OperatorContractSignature>('/settings/operator-contract-signature'); operatorSignatureForm.setFieldsValue(r.data); }
    catch (e) { setError(errorMessage(e)); }
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
    if (tab === 'general' && user?.role !== 'INVESTOR') void loadGeneral();
    if (tab === 'general' && user?.role === 'OPERATOR') void loadOperatorSignature();
    if (tab === 'users' && user?.role === 'OPERATOR') void loadUsers();
    if (tab === 'audit' && user?.role === 'OPERATOR') void loadAudit();
  }, [tab, user?.role]);
  useEffect(() => {
    if (user?.role !== 'OPERATOR' && tab !== 'general' && tab !== 'telegram') setTab('general');
    if (user?.role === 'INVESTOR' && tab !== 'telegram') setTab('telegram');
  }, [user?.role, tab]);

  const saveGeneral = async (values: GeneralForm) => {
    try { await api.put<SystemSettings>('/settings', values); notice.success({ message: 'Sozlamalar saqlandi.' }); }
    catch (e) { notice.error({ message: 'Sozlamalarni saqlab bo‘lmadi', description: errorMessage(e) }); }
  };
  const saveOperatorSignature = async (values: OperatorSignatureForm) => {
    try { await api.put<OperatorContractSignature>('/settings/operator-contract-signature', values); notice.success({ message: uz.operatorSignature.saved }); }
    catch (e) { notice.error({ message: errorMessage(e) }); }
  };
  const openUser = (target?: User) => {
    setEditingUser(target || null);
    userForm.setFieldsValue(target ? { full_name: target.full_name, email: target.email, password: '', role: target.role === 'INVESTOR' ? 'INVESTOR' : 'ADMIN' } : { role: 'ADMIN' });
    setUserModal(true);
  };
  const saveUser = async (values: UserForm) => {
    try {
      if (editingUser) {
        const payload: { full_name: string; password?: string; role?: 'ADMIN' | 'INVESTOR' } = { full_name: values.full_name };
        if (values.password) payload.password = values.password;
        if (values.role && values.role !== editingUser.role) payload.role = values.role;
        await api.patch(`/users/${editingUser.id}`, payload);
        notice.success({ message: 'Foydalanuvchi ma’lumotlari yangilandi.' });
      } else {
        await api.post('/users', { ...values, role: values.role || 'ADMIN' });
        notice.success({ message: `${uz.role[values.role || 'ADMIN']} qo‘shildi.` });
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
    { title: 'Roli', dataIndex: 'role', render: (v: string) => <Tag color={v === 'INVESTOR' ? 'gold' : v === 'OPERATOR' ? 'blue' : 'default'}>{uz.role[v as keyof typeof uz.role] ?? v}</Tag> },
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

  const generalTab = { key: 'general', label: 'Umumiy', children: <div className="page-stack"><Panel title="Yotoqxona ma’lumotlari"><Form form={form} layout="vertical" onFinish={saveGeneral} className="settings-form"><Form.Item name="dorm_name" label="Yotoqxona nomi" rules={[{ required: true, message: 'Nomini kiriting.' }]}><Input maxLength={160}/></Form.Item><Form.Item name="default_period_days" label="Standart to‘lov davri (kun)" rules={[{ required: true, message: 'Kun sonini kiriting.' }]}><Input type="number" min={1} max={365000}/></Form.Item><Form.Item name="currency" label="Valyuta"><Input disabled/></Form.Item><div className="settings-actions"><Button type="primary" htmlType="submit" disabled={user?.role !== 'OPERATOR'}>O‘zgarishlarni saqlash</Button>{user?.role !== 'OPERATOR' && <span>Sozlamalarni faqat operator o‘zgartira oladi.</span>}</div></Form></Panel>{user?.role === 'OPERATOR' && <Panel title={uz.operatorSignature.title}><p className="muted">{uz.operatorSignature.subtitle}</p><Form form={operatorSignatureForm} layout="vertical" onFinish={saveOperatorSignature} className="settings-form"><Form.Item name="full_name" label={uz.operatorSignature.field} rules={[{ required: true, min: 2, message: 'To‘liq F.I.Sh. ni kiriting.' }]}><Input maxLength={200} autoComplete="name"/></Form.Item><Button type="primary" htmlType="submit">{uz.operatorSignature.save}</Button></Form></Panel>}</div> };
  const telegramTab = { key: 'telegram', label: 'Telegram', children: <TelegramPanel /> };
  const items = user?.role === 'OPERATOR' ? [
    generalTab, telegramTab,
    { key: 'users', label: 'Foydalanuvchilar', children: <Panel title="Xodimlar va investorlar" extra={<Button type="primary" onClick={() => openUser()}>Foydalanuvchi qo‘shish</Button>}><Table rowKey="id" loading={loading} dataSource={users} columns={userColumns} pagination={{ pageSize: 10 }} scroll={{ x: 750 }} locale={{ emptyText: 'Foydalanuvchilar topilmadi' }}/></Panel> },
    { key: 'audit', label: 'Faollik jurnali', children: <Panel title={`Tizimdagi amallar · ${auditTotal} ta`}><Table rowKey="id" loading={loading} dataSource={audits} columns={auditColumns} pagination={{ pageSize: 15 }} scroll={{ x: 900 }} locale={{ emptyText: 'Faollik qaydlari topilmadi' }}/></Panel> },
  ] : user?.role === 'INVESTOR' ? [telegramTab] : [generalTab, telegramTab];

  return <div className="page-stack">{holder}<PageHeading eyebrow="TIZIM BOSHQARUVI" title={tab === 'users' ? 'Foydalanuvchilar' : tab === 'audit' ? 'Faollik jurnali' : 'Sozlamalar'} subtitle="Yotoqxona va tizim boshqaruvi sozlamalari."/>
    {error && <Alert type="error" showIcon message="Ma’lumotni yuklab bo‘lmadi" description={error} action={<Button onClick={() => tab === 'general' ? void loadGeneral() : tab === 'users' ? void loadUsers() : void loadAudit()}>Qayta yuklash</Button>}/>}
    <Tabs activeKey={tab} onChange={(v) => setTab(v as TabKey)} items={items}/>
    <Modal open={userModal} title={editingUser ? 'Administratorni tahrirlash' : 'Administrator qo‘shish'} onCancel={() => { setUserModal(false); setEditingUser(null); userForm.resetFields(); }} onOk={() => userForm.submit()} okText={editingUser ? 'O‘zgarishlarni saqlash' : 'Foydalanuvchi yaratish'} cancelText="Bekor qilish" destroyOnClose>
      <Form form={userForm} layout="vertical" onFinish={saveUser}><Form.Item name="full_name" label="To‘liq ism" rules={[{ required: true, min: 2, message: 'Ismni kiriting.' }]}><Input/></Form.Item>
        <Form.Item name="role" label="Roli" rules={[{ required: true }]}><Select disabled={editingUser?.role === 'OPERATOR'} options={[{ value: 'ADMIN', label: uz.role.ADMIN }, { value: 'INVESTOR', label: uz.role.INVESTOR }]} /></Form.Item>
        {!editingUser && <Form.Item name="email" label="Elektron pochta" rules={[{ required: true, type: 'email', message: 'To‘g‘ri elektron pochta kiriting.' }]}><Input type="email"/></Form.Item>}
        <Form.Item name="password" label={editingUser ? 'Yangi parol (ixtiyoriy)' : 'Vaqtinchalik parol'} extra="Parol kamida 12 ta belgidan iborat bo‘lishi kerak." rules={[{ required: !editingUser, min: 12, message: 'Parol kamida 12 ta belgidan iborat bo‘lsin.' }]}><Input.Password autoComplete="new-password"/></Form.Item>
      </Form>
    </Modal>
  </div>;
}
