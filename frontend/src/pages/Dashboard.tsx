import { useEffect, useState } from 'react';
import { Alert, Col, Row, Spin, Table, Typography } from 'antd';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis, BarChart, Bar } from 'recharts';
import { api, errorMessage } from '../api';
import type { Dashboard as DashboardData } from '../types';
import { formatDate, formatMoney } from '../locales/uz';
import { PageHeading, Panel } from './shared';

const { Text } = Typography;
const moneyAxis = (value: number) => new Intl.NumberFormat('uz-UZ', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

function Metric({ label, value, note, tone = '' }: { label: string; value: string | number; note?: string; tone?: string }) {
  return <div className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.get<DashboardData>('/dashboard').then((r) => setData(r.data)).catch((e) => setError(errorMessage(e))); }, []);
  if (!data && !error) return <div className="page-loading"><Spin size="large" /></div>;
  return <div className="page-stack">
    <PageHeading eyebrow="BUGUNGI HOLAT" title="Boshqaruv paneli" subtitle="Yotoqxona faoliyati va moliyaviy holati bir joyda." />
    {error && <Alert type="error" showIcon message="Ma’lumotlarni yuklab bo‘lmadi" description={error} />}
    {data && <>
      <Row gutter={[14, 14]}>
        <Col xs={12} md={6}><Metric label="Yashovchilar" value={data.residents} note={`${data.rooms} ta faol xona`} /></Col>
        <Col xs={12} md={6}><Metric label="Xonalar bandligi" value={`${data.occupancy_rate}%`} note={`${data.available_beds} ta bo‘sh o‘rin`} tone="metric-green" /></Col>
        <Col xs={12} md={6}><Metric label="To‘lov muddati o‘tgan" value={data.overdue} note={`${data.due_today} ta bugun to‘lanadi`} tone="metric-amber" /></Col>
        <Col xs={12} md={6}><Metric label="Joriy oy tushumi" value={formatMoney(data.actual_revenue)} note="Haqiqiy qabul qilingan to‘lovlar" tone="metric-blue" /></Col>
      </Row>
      <Row gutter={[14, 14]}>
        <Col xs={24} xl={15}><Panel title="Haqiqiy tushum dinamikasi"><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data.revenue_trend} margin={{ top: 8, right: 12, left: 2, bottom: 0 }}><defs><linearGradient id="revenueFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#34745b" stopOpacity={0.24}/><stop offset="100%" stopColor="#34745b" stopOpacity={0.015}/></linearGradient></defs><CartesianGrid vertical={false} stroke="#e9eee8"/><XAxis dataKey="month" tick={{ fontSize: 11 }} axisLine={false} tickLine={false}/><YAxis tickFormatter={moneyAxis} tick={{ fontSize: 11 }} axisLine={false} tickLine={false} width={48}/><Tooltip formatter={(value) => formatMoney(Number(value))}/><Area type="monotone" dataKey="amount" name="Tushum" stroke="#34745b" strokeWidth={2.5} fill="url(#revenueFill)"/></AreaChart></ResponsiveContainer></div></Panel></Col>
        <Col xs={24} xl={9}><Panel title="Xonalar bandligi"><div className="chart-box"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.occupancy_by_room} margin={{ top: 8, right: 8, left: -22, bottom: 0 }}><CartesianGrid vertical={false} stroke="#e9eee8"/><XAxis dataKey="room" tick={{ fontSize: 11 }} axisLine={false} tickLine={false}/><YAxis allowDecimals={false} tick={{ fontSize: 11 }} axisLine={false} tickLine={false}/><Tooltip/><Bar dataKey="occupied" name="Band" stackId="beds" fill="#34745b" radius={[3,3,0,0]}/><Bar dataKey="available" name="Bo‘sh" stackId="beds" fill="#dfe9df" radius={[3,3,0,0]}/></BarChart></ResponsiveContainer></div></Panel></Col>
      </Row>
      <Row gutter={[14, 14]}>
        <Col xs={24} lg={12}><Panel title="Moliyaviy ko‘rsatkichlar"><div className="finance-list"><div><span>Qarzdorlik</span><strong className="text-danger">{formatMoney(data.outstanding_debt)}</strong></div><div><span>Kutilayotgan to‘lovlar</span><strong>{formatMoney(data.expected_payments)}</strong></div><div><span>Yaqin 7 kundagi muddatlar</span><strong>{data.due_soon} ta yashovchi</strong></div></div></Panel></Col>
        <Col xs={24} lg={12}><Panel title="So‘nggi to‘lovlar" extra={<a href="/payments">Barchasi</a>}><Table size="small" pagination={false} rowKey="id" dataSource={data.recent_payments} locale={{ emptyText: 'Hali to‘lovlar yo‘q' }} columns={[{ title: 'Yashovchi', dataIndex: 'resident_name', render: (v: string) => <strong>{v}</strong> }, { title: 'Sana', dataIndex: 'payment_date', render: (v: string) => formatDate(v) }, { title: 'Summa', dataIndex: 'net_amount', align: 'right', render: (v: number) => <strong>{formatMoney(v)}</strong> }]} /></Panel></Col>
      </Row>
      <div className="dashboard-footnote"><Text type="secondary">Kutilayotgan to‘lovlar ochiq davrlar bo‘yicha hisoblangan. Tushum faqat amalda qayd etilgan to‘lovlarni ko‘rsatadi.</Text></div>
    </>}
  </div>;
}
