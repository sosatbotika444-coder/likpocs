import { useEffect, useMemo, useState } from 'react';
import { Alert, Button, DatePicker, Form, Input, InputNumber, Modal, Select, Table, Tag, notification } from 'antd';
import { api, errorMessage } from '../api';
import type { Page, Payment, Resident } from '../types';
import { formatDate, formatMoney, todayUzbekistan } from '../locales/uz';
import { useAuth } from '../auth';
import { Actions, PageHeading } from './shared';

type PaymentForm = { resident_id: string; amount: number; payment_date: string; method: string; notes?: string };

export default function Payments() {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [rows, setRows] = useState<Payment[]>([]);
  const [residents, setResidents] = useState<Resident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [range, setRange] = useState<[string | undefined, string | undefined]>([undefined, undefined]);
  const [editor, setEditor] = useState(false);
  const [adjusting, setAdjusting] = useState<Payment | null>(null);
  const [form] = Form.useForm<PaymentForm>();
  const [adjustForm] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [total, setTotal] = useState(0);

  const load = async () => {
    setLoading(true); setError('');
    try {
      const params = { date_from: range[0], date_to: range[1], limit: 500 };
      const [payments, people] = await Promise.all([api.get<Page<Payment>>('/payments', { params }), api.get<Page<Resident>>('/residents', { params: { limit: 500 } })]);
      setRows(payments.data.items); setTotal(payments.data.total); setResidents(people.data.items);
    } catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  };
  useEffect(() => { void load(); }, [range]);

  const save = async (values: PaymentForm) => {
    setSaving(true);
    try { await api.post('/payments', values); notice.success({message:'To‘lov qayd etildi.'}); setEditor(false); form.resetFields(); await load(); }
    catch (e) { notice.error({message:'To‘lovni qayd etib bo‘lmadi',description:errorMessage(e)}); }
    finally { setSaving(false); }
  };
  const adjust = async (values: {amount_delta:number;reason:string}) => {
    if (!adjusting) return;
    setSaving(true);
    try { await api.post(`/payments/${adjusting.id}/adjustments`, values); notice.success({message:'To‘lovga tuzatish auditi bilan qo‘shildi.'}); setAdjusting(null); adjustForm.resetFields(); await load(); }
    catch (e) { notice.error({message:'Tuzatishni saqlab bo‘lmadi',description:errorMessage(e)}); }
    finally { setSaving(false); }
  };

  const columns = useMemo(() => [
    { title:'Sana',dataIndex:'payment_date',render:(v:string)=><div className="date-cell"><strong>{formatDate(v)}</strong></div> },
    { title:'Yashovchi',dataIndex:'resident_name',render:(v:string)=><strong>{v}</strong> },
    { title:'To‘lov usuli',dataIndex:'method',render:(v:string)=><Tag className="method-tag">{({CASH:'Naqd pul',BANK:'Bank o‘tkazmasi',CLICK:'Click',PAYME:'Payme',OTHER:'Boshqa'} as Record<string,string>)[v]||v}</Tag> },
    { title:'Qamrab olingan davr',render:(_:unknown,r:Payment)=>r.covered_start?`${formatDate(r.covered_start)} — ${formatDate(r.covered_end)}`:'—' },
    { title:'Qayd etdi',dataIndex:'recorded_by_name' },
    { title:'Summa',dataIndex:'net_amount',align:'right' as const,render:(v:number,r:Payment)=><div className="money-cell"><strong>{formatMoney(v)}</strong>{r.net_amount!==r.amount&&<small>Asl summa {formatMoney(r.amount)}</small>}</div> },
    ...(user?.role==='OPERATOR'?[{title:'',align:'right' as const,render:(_:unknown,r:Payment)=><Actions><Button type="link" onClick={()=>{setAdjusting(r);adjustForm.resetFields();}}>Tuzatish</Button></Actions>}]:[]),
  ],[user?.role]);

  const eligible = residents.filter((r)=>r.billing_status!=='NOT_CONFIGURED' && r.balance>0);
  return <div className="page-stack">{holder}
    <PageHeading eyebrow="MOLIYA" title="To‘lovlar" subtitle="Haqiqiy tushumlar va qaydlar tarixi." action="To‘lov qayd etish" onAction={()=>{form.setFieldsValue({payment_date:todayUzbekistan(),method:'CASH'});setEditor(true);}}/>
    <div className="summary-strip"><span>Ko‘rsatilgan qaydlar <strong>{total}</strong></span><span>Haqiqiy tushum <strong>{formatMoney(rows.reduce((sum,p)=>sum+p.net_amount,0))}</strong></span><span>Bu hisobot davrida</span></div>
    {error&&<Alert type="error" showIcon message="To‘lovlarni yuklab bo‘lmadi" description={error} action={<Button onClick={()=>void load()}>Qayta yuklash</Button>}/>}
    <div className="toolbar panel"><span className="toolbar-label">Davr</span><DatePicker.RangePicker format="DD.MM.YYYY" onChange={(v)=>setRange([v?.[0]?.format('YYYY-MM-DD'),v?.[1]?.format('YYYY-MM-DD')])}/><Button type="link" onClick={()=>setRange([undefined,undefined])}>Filtrni tozalash</Button></div>
    <div className="panel table-panel"><Table rowKey="id" loading={loading} columns={columns} dataSource={rows} scroll={{x:950}} pagination={{pageSize:15,showTotal:(n)=>`Jami ${n} ta`}} locale={{emptyText:'Tanlangan davrda to‘lovlar yo‘q'}}/></div>
    <Modal open={editor} title="Yangi to‘lov" onCancel={()=>setEditor(false)} onOk={()=>form.submit()} confirmLoading={saving} okText="To‘lovni saqlash" cancelText="Bekor qilish" destroyOnClose>
      <Form form={form} layout="vertical" onFinish={save}><Form.Item name="resident_id" label="Yashovchi" rules={[{required:true,message:'Yashovchini tanlang.'}]}><Select showSearch optionFilterProp="label" placeholder="Qarzdorligi bor yashovchini tanlang" options={eligible.map((r)=>({value:r.id,label:`${r.first_name} ${r.last_name} · ${r.room_number||'Xona yo‘q'} · ${formatMoney(r.balance)}`}))}/></Form.Item><Form.Item name="amount" label="Summa (so‘m)" rules={[{required:true,message:'Summani kiriting.'}]}><InputNumber min={1} controls={false} className="full-width"/></Form.Item><div className="form-grid"><Form.Item name="payment_date" label="To‘lov sanasi" rules={[{required:true,message:'Sanani tanlang.'}]}><Input type="date"/></Form.Item><Form.Item name="method" label="To‘lov usuli" rules={[{required:true,message:'Usulni tanlang.'}]}><Select options={[{value:'CASH',label:'Naqd pul'},{value:'BANK',label:'Bank o‘tkazmasi'},{value:'CLICK',label:'Click'},{value:'PAYME',label:'Payme'},{value:'OTHER',label:'Boshqa'}]}/></Form.Item></div><Form.Item name="notes" label="Izoh"><Input.TextArea rows={2}/></Form.Item></Form>
      {!eligible.length&&<Alert type="warning" showIcon message="To‘lov davri va qarzdorligi sozlangan yashovchi topilmadi."/>}
    </Modal>
    <Modal open={Boolean(adjusting)} title="To‘lovni tuzatish" onCancel={()=>setAdjusting(null)} onOk={()=>adjustForm.submit()} confirmLoading={saving} okText="Tuzatishni qayd etish" cancelText="Bekor qilish" destroyOnClose>
      <Alert type="warning" showIcon message="Tarixiy to‘lov o‘zgartirilmaydi. Tuzatish alohida audit qaydi sifatida saqlanadi." className="modal-alert"/>
      {adjusting&&<p className="adjust-payment-line">{adjusting.resident_name} · {formatMoney(adjusting.net_amount)}</p>}
      <Form form={adjustForm} layout="vertical" onFinish={adjust}><Form.Item name="amount_delta" label="Farq (so‘m)" extra="Kamaytirish uchun manfiy qiymat kiriting." rules={[{required:true,message:'Farq summasini kiriting.'}]}><InputNumber controls={false} className="full-width"/></Form.Item><Form.Item name="reason" label="Tuzatish sababi" rules={[{required:true,min:5,message:'Kamida 5 ta belgi kiriting.'}]}><Input.TextArea rows={3}/></Form.Item></Form>
    </Modal>
  </div>;
}
