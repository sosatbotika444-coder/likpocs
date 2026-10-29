import { useEffect, useState, type ReactNode } from 'react';
import { Alert, Col, Row, Spin, Typography } from 'antd';
import { HomeOutlined, TeamOutlined, WalletOutlined } from '@ant-design/icons';
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Link } from 'react-router-dom';
import { api, errorMessage } from '../api';
import type { Dashboard as DashboardData } from '../types';
import { formatDate, formatMoney } from '../locales/uz';
import { PageHeading, Panel } from './shared';

const { Text } = Typography;
const moneyAxis = (value: number) => new Intl.NumberFormat('uz-UZ', { notation: 'compact', maximumFractionDigits: 1 }).format(value);

function Metric({ label, value, note, icon, tone = '' }: { label: string; value: string | number; note?: string; icon: ReactNode; tone?: string }) {
  return <div className={`metric-card dashboard-metric ${tone}`}>
    <div className="dashboard-metric-head"><span className="dashboard-metric-icon">{icon}</span><span>{label}</span></div>
    <strong>{value}</strong>
    {note && <small>{note}</small>}
  </div>;
}

function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('uz-UZ');
}

export default function Dashboard() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { api.get<DashboardData>('/dashboard').then((r) => setData(r.data)).catch((e) => setError(errorMessage(e))); }, []);
  if (!data && !error) return <div className="page-loading"><Spin size="large" /></div>;

  const assignedBeds = data?.occupancy_by_room.reduce((total, room) => total + room.occupied, 0) ?? 0;

  return <div className="dashboard-workspace">
    <main className="dashboard-primary">
      <PageHeading eyebrow="BUGUNGI HOLAT" title="Boshqaruv paneli" subtitle="Yotoqxona faoliyati va moliyaviy holati bir joyda." />
      {error && <Alert type="error" showIcon message="Ma’lumotlarni yuklab bo‘lmadi" description={error} />}
      {data && <div className="dashboard-main-stack">
        <Row gutter={[9, 9]} className="dashboard-metrics">
          <Col span={8}><Metric label="Yashovchilar" value={data.residents} note={`${data.rooms} ta faol xona`} icon={<TeamOutlined />} /></Col>
          <Col span={8}><Metric label="Xonalar bandligi" value={`${data.occupancy_rate}%`} note={`${data.available_beds} ta bo‘sh o‘rin`} icon={<HomeOutlined />} tone="metric-green" /></Col>
          <Col span={8}><Metric label="Joriy oy tushumi" value={formatMoney(data.actual_revenue)} note="Haqiqiy qabul qilingan to‘lovlar" icon={<WalletOutlined />} tone="metric-green" /></Col>
        </Row>

        <div className="dashboard-chart-grid">
          <Panel title="Xonalar bo‘yicha o‘rinlar" className="dashboard-chart-panel">
            <div className="chart-box dashboard-chart-box"><ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.occupancy_by_room} margin={{ top: 6, right: 2, left: -24, bottom: 0 }}>
                <CartesianGrid vertical={false} stroke="#ecefeb" />
                <XAxis dataKey="room" tick={{ fontSize: 8, fill: '#929995' }} axisLine={false} tickLine={false} />
                <YAxis allowDecimals={false} tick={{ fontSize: 8, fill: '#929995' }} axisLine={false} tickLine={false} width={27} />
                <Tooltip contentStyle={{ border: '1px solid #e8ece8', borderRadius: 7, fontSize: 9, boxShadow: '0 3px 12px #0000000a' }} />
                <Bar dataKey="occupied" name="Band" stackId="beds" fill="#42a47a" radius={[3, 3, 0, 0]} />
                <Bar dataKey="available" name="Bo‘sh" stackId="beds" fill="#e0e9e1" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer></div>
          </Panel>
          <Panel title="Yotoqxona bandligi" className="dashboard-chart-panel dashboard-donut-panel">
            <div className="chart-box dashboard-chart-box"><ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={[{ name: 'Band', value: assignedBeds }, { name: 'Bo‘sh', value: data.available_beds }]} dataKey="value" nameKey="name" cx="50%" cy="43%" innerRadius={29} outerRadius={43} paddingAngle={2} stroke="none">
                  <Cell fill="#42a47a" />
                  <Cell fill="#e5d488" />
                </Pie>
                <Tooltip contentStyle={{ border: '1px solid #e8ece8', borderRadius: 7, fontSize: 9, boxShadow: '0 3px 12px #0000000a' }} />
                <Legend verticalAlign="bottom" iconType="circle" iconSize={5} wrapperStyle={{ color: '#929995', fontSize: 7, lineHeight: '9px' }} />
              </PieChart>
            </ResponsiveContainer></div>
          </Panel>
        </div>
        <Panel title="Haqiqiy tushum dinamikasi" className="dashboard-chart-panel dashboard-revenue-panel">
          <div className="chart-box dashboard-chart-box"><ResponsiveContainer width="100%" height="100%">
            <AreaChart data={data.revenue_trend} margin={{ top: 6, right: 5, left: -20, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="#ecefeb" />
              <XAxis dataKey="month" tick={{ fontSize: 8, fill: '#929995' }} axisLine={false} tickLine={false} />
              <YAxis tickFormatter={moneyAxis} tick={{ fontSize: 8, fill: '#929995' }} axisLine={false} tickLine={false} width={38} />
              <Tooltip formatter={(value) => formatMoney(Number(value))} contentStyle={{ border: '1px solid #e8ece8', borderRadius: 7, fontSize: 9, boxShadow: '0 3px 12px #0000000a' }} />
              <Area type="monotone" dataKey="amount" name="Tushum" stroke="#42a47a" strokeWidth={1.8} fill="#e7f3eb" fillOpacity={0.55} activeDot={{ r: 3 }} />
            </AreaChart>
          </ResponsiveContainer></div>
        </Panel>
        <div className="dashboard-footnote"><Text type="secondary">Tushum faqat amalda qayd etilgan to‘lovlarni ko‘rsatadi. Barcha summalar so‘mda.</Text></div>
      </div>}
    </main>

    {data && <aside className="dashboard-secondary">
      <Panel title="Yangi yashovchilar" className="dashboard-side-panel">
        <div className="resident-mini-list">
          {data.recent_residents.slice(0, 4).map((resident) => {
            const name = `${resident.first_name} ${resident.last_name}`;
            return <div className="resident-mini" key={resident.id}>
              <span className="resident-mini-avatar">{initials(name)}</span>
              <span className="resident-mini-copy"><strong>{name}</strong><small>{resident.room_number ? `${resident.room_number}-xona` : 'Xona belgilanmagan'}</small></span>
            </div>;
          })}
          {!data.recent_residents.length && <div className="dashboard-empty">Yangi yashovchilar yo‘q</div>}
        </div>
      </Panel>

      <Panel title="Moliyaviy ko‘rsatkichlar" className="dashboard-side-panel">
        <div className="dashboard-finance-list">
          <div><span>Qarzdorlik</span><strong className="text-danger">{formatMoney(data.outstanding_debt)}</strong></div>
          <div><span>Joriy oy xarajatlari</span><strong>{formatMoney(data.actual_expenses)}</strong></div>
          <div><span>Sof pul oqimi</span><strong>{formatMoney(data.net_cash_flow)}</strong></div>
          <div><span>Kutilayotgan to‘lovlar</span><strong>{formatMoney(data.expected_payments)}</strong></div>
          <div><span>Muddati o‘tgan</span><strong className="text-danger">{data.overdue} ta</strong></div>
          <div><span>Bugun to‘lanadi</span><strong>{data.due_today} ta</strong></div>
          <div><span>Yaqin 7 kunda</span><strong>{data.due_soon} ta</strong></div>
        </div>
      </Panel>

      <Panel title="So‘nggi to‘lovlar" extra={<Link to="/payments">Barchasi</Link>} className="dashboard-side-panel">
        <div className="payment-mini-list">
          {data.recent_payments.slice(0, 4).map((payment) => <div className="payment-mini" key={payment.id}>
            <span className="payment-mini-avatar">{initials(payment.resident_name)}</span>
            <span className="payment-mini-copy"><strong>{payment.resident_name}</strong><small>{formatDate(payment.payment_date, true)}</small></span>
            <strong className="payment-mini-amount">{formatMoney(payment.net_amount)}</strong>
          </div>)}
          {!data.recent_payments.length && <div className="dashboard-empty">Hali to‘lovlar yo‘q</div>}
        </div>
      </Panel>
    </aside>}
  </div>;
}
