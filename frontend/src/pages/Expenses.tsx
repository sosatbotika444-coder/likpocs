import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import { Alert, Button, DatePicker, Form, Input, InputNumber, Modal, Select, Table, Tag, notification } from 'antd';
import { StopOutlined } from '@ant-design/icons';
import { api, errorMessage } from '../api';
import { useAuth } from '../auth';
import { formatDate, formatMoney, sumMoney, todayUzbekistan, uz } from '../locales/uz';
import type { Expense, ExpenseCategory, Page } from '../types';
import { PageHeading, Panel } from './shared';

type ExpenseForm = { expense_date: Dayjs; category: ExpenseCategory; description: string; amount: string; method: string; reference?: string };
type VoidForm = { reason: string };
const categories: { value: ExpenseCategory; label: string }[] = [
  { value: 'UTILITIES', label: 'Kommunal xizmatlar' }, { value: 'REPAIR', label: "Ta'mirlash" },
  { value: 'SUPPLIES', label: "Xo'jalik mollari" }, { value: 'FOOD', label: 'Oziq-ovqat' },
  { value: 'SALARY', label: 'Ish haqi' }, { value: 'OTHER', label: 'Boshqa' },
];

export default function Expenses() {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [form] = Form.useForm<ExpenseForm>();
  const [voidForm] = Form.useForm<VoidForm>();
  const [rows, setRows] = useState<Expense[]>([]);
  const [total, setTotal] = useState(0);
  const [dates, setDates] = useState<[string | undefined, string | undefined]>([undefined, undefined]);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [includeVoided, setIncludeVoided] = useState(false);
  const [loading, setLoading] = useState(true);
  const expenseKey = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [createOpen, setCreateOpen] = useState(false);
  const [voidTarget, setVoidTarget] = useState<Expense | null>(null);

  const load = useCallback(async () => {
    setLoading(true); setError('');
    try {
      const response = await api.get<Page<Expense>>('/expenses', { params: { date_from: dates[0], date_to: dates[1], include_voided: includeVoided, skip: (page - 1) * pageSize, limit: pageSize } });
      setRows(response.data.items); setTotal(response.data.total);
    } catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  }, [dates, includeVoided, page, pageSize]);

  useEffect(() => { void load(); }, [load]);
  const activeTotal = useMemo(() => sumMoney(rows.filter((row) => !row.voided_at).map((row) => row.amount)), [rows]);

  const create = async (values: ExpenseForm) => {
    setBusy(true);
    try {
      expenseKey.current ??= crypto.randomUUID();
      await api.post('/expenses', {
        expense_date: values.expense_date.format('YYYY-MM-DD'), category: values.category,
        description: values.description.trim(), amount: values.amount, method: values.method,
        reference: values.reference?.trim() ?? '',
      }, { headers: { 'Idempotency-Key': expenseKey.current } });
      expenseKey.current = null; notice.success({ message: 'Xarajat qayd etildi.' });
      setCreateOpen(false); form.resetFields(); await load();
    } catch (e) { notice.error({ message: 'Xarajatni saqlab bo‘lmadi', description: errorMessage(e) }); }
    finally { setBusy(false); }
  };

  const voidExpense = async (values: VoidForm) => {
    if (!voidTarget) return;
    setBusy(true);
    try {
      await api.post(`/expenses/${voidTarget.id}/void`, { reason: values.reason.trim() });
      notice.success({ message: 'Xarajat bekor qilindi. Tarix saqlandi.' });
      setVoidTarget(null); voidForm.resetFields(); await load();
    } catch (e) { notice.error({ message: 'Xarajatni bekor qilib bo‘lmadi', description: errorMessage(e) }); }
    finally { setBusy(false); }
  };

  const columns = [
    { title: 'Sana', dataIndex: 'expense_date', width: 120, render: (v: string) => formatDate(v, true) },
    { title: 'Toifa', dataIndex: 'category', width: 170, render: (v: ExpenseCategory) => categories.find((item) => item.value === v)?.label ?? v },
    { title: 'Xarajat tafsiloti', dataIndex: 'description', render: (v: string, row: Expense) => <div><strong>{v}</strong>{row.reference && <small className="table-subtitle">Hujjat: {row.reference}</small>}{row.void_reason && <small className="table-subtitle">Bekor qilish sababi: {row.void_reason}</small>}</div> },
    { title: 'To‘lov usuli', dataIndex: 'method', width: 130, render: (v: keyof typeof uz.paymentMethod) => uz.paymentMethod[v] ?? v },
    { title: 'Qayd etdi', dataIndex: 'recorded_by_name', width: 150 },
    { title: 'Summa', dataIndex: 'amount', align: 'right' as const, width: 160, render: (v: number, row: Expense) => <span className={row.voided_at ? 'text-muted' : 'text-danger'}>{formatMoney(v)}</span> },
    { title: 'Holat', dataIndex: 'voided_at', width: 120, render: (v: string | null) => v ? <Tag>Bekor qilingan</Tag> : <Tag color="green">Amalda</Tag> },
    ...(user?.role === 'OPERATOR' ? [{ title: '', width: 100, render: (_: unknown, row: Expense) => !row.voided_at && <Button danger type="link" icon={<StopOutlined />} onClick={() => { setVoidTarget(row); voidForm.resetFields(); }}>Bekor qilish</Button> }] : []),
  ];

  return <div className="page-stack">{holder}
    <PageHeading eyebrow="MOLIYAVIY HISOB" title="Xarajatlar" subtitle="Xarajatlarni sana, toifa va to‘lov usuli bo‘yicha qayd eting va kuzating." action="Xarajat qo‘shish" onAction={() => { expenseKey.current = null; form.setFieldsValue({ expense_date: dayjs(todayUzbekistan()), category: 'OTHER', method: 'CASH' }); setCreateOpen(true); }} />
    {error && <Alert type="error" showIcon message="Xarajatlarni yuklab bo‘lmadi" description={error} action={<Button onClick={() => void load()}>Qayta yuklash</Button>} />}
    <div className="toolbar panel"><span className="toolbar-label">Sana oralig‘i</span><DatePicker.RangePicker format="DD.MM.YYYY" onChange={(value) => { setPage(1); setDates([value?.[0]?.format('YYYY-MM-DD'), value?.[1]?.format('YYYY-MM-DD')]); }} /><Button type={includeVoided ? 'primary' : 'default'} onClick={() => { setPage(1); setIncludeVoided((value) => !value); }}>{includeVoided ? 'Bekor qilinganlar ko‘rsatilmoqda' : 'Bekor qilinganlarni ko‘rsatish'}</Button><Button type="link" onClick={() => { setPage(1); setDates([undefined, undefined]); }}>Filtrni tozalash</Button></div>
    <Panel title={`Bu sahifadagi faol xarajatlar · ${formatMoney(activeTotal)}`} extra={<span>{total} ta qayd</span>}>
      <Table rowKey="id" loading={loading} dataSource={rows} columns={columns} scroll={{ x: 1050 }} pagination={{ current: page, pageSize, total, showSizeChanger: true, pageSizeOptions: [20, 50, 100] }} onChange={(pagination) => { setPage(pagination.current ?? 1); setPageSize(pagination.pageSize ?? 20); }} locale={{ emptyText: 'Tanlangan davrda xarajat qayd etilmagan' }} />
    </Panel>
    <Modal open={createOpen} title="Yangi xarajat" onCancel={() => { setCreateOpen(false); expenseKey.current = null; form.resetFields(); }} onOk={() => form.submit()} confirmLoading={busy} okText="Qayd etish" cancelText="Bekor qilish" destroyOnClose>
      <Form form={form} layout="vertical" onValuesChange={() => { expenseKey.current = null; }} onFinish={(values) => void create(values)}>
        <Form.Item name="expense_date" label="Xarajat sanasi" rules={[{ required: true, message: 'Sanani tanlang.' }]}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="category" label="Toifa" rules={[{ required: true, message: 'Toifani tanlang.' }]}><Select options={categories} /></Form.Item>
        <Form.Item name="description" label="Xarajat tafsiloti" rules={[{ required: true, min: 2, max: 500, message: 'Kamida 2 ta belgi kiriting.' }]}><Input maxLength={500} /></Form.Item>
        <Form.Item name="amount" label="Summa (so‘m)" rules={[{ required: true, message: 'Summani kiriting.' }, { validator: (_, value: string) => Number(value) > 0 ? Promise.resolve() : Promise.reject(new Error('Summa noldan katta bo‘lishi kerak.')) }]}><InputNumber<string> stringMode min="0.01" precision={2} style={{ width: '100%' }} /></Form.Item>
        <Form.Item name="method" label="To‘lov usuli" rules={[{ required: true, message: 'Usulni tanlang.' }]}><Select options={uz.paymentMethods.map((item) => ({ ...item }))} /></Form.Item>
        <Form.Item name="reference" label="Chek yoki hujjat raqami"><Input maxLength={120} /></Form.Item>
      </Form>
    </Modal>
    <Modal open={Boolean(voidTarget)} title="Xarajatni bekor qilish" onCancel={() => { setVoidTarget(null); voidForm.resetFields(); }} onOk={() => voidForm.submit()} confirmLoading={busy} okText="Bekor qilish" cancelText="Orqaga" okButtonProps={{ danger: true }} destroyOnClose>
      <p>Moliyaviy yozuv o‘chirilmaydi. Bekor qilish sababi audit tarixida saqlanadi.</p>
      {voidTarget && <p><strong>{formatMoney(voidTarget.amount)}</strong> · {voidTarget.description}</p>}
      <Form form={voidForm} layout="vertical" onFinish={(values) => void voidExpense(values)}><Form.Item name="reason" label="Sabab" rules={[{ required: true, min: 5, max: 1000, message: 'Sababni kamida 5 ta belgi bilan yozing.' }]}><Input.TextArea rows={3} maxLength={1000} /></Form.Item></Form>
    </Modal>
  </div>;
}
