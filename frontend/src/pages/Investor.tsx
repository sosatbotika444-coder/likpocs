import { useEffect, useState } from 'react';
import { Alert, Col, Row, Segmented, Spin, Table } from 'antd';
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api, errorMessage } from '../api';
import { formatMoney, todayUzbekistan, uz } from '../locales/uz';
import type { InvestorSummary } from '../types';
import { PageHeading, Panel } from './shared';

const monthName = (month: number) => new Intl.DateTimeFormat('uz-UZ', { month: 'long' }).format(new Date(2026, month - 1, 1));

function Metric({ label, value }: { label: string; value: string }) {
  return <div className="metric-card dashboard-metric"><div className="dashboard-metric-head"><span>{label}</span></div><strong>{value}</strong></div>;
}

function rangeStart(months: number): string {
  const today = todayUzbekistan();
  const [year, month] = today.split('-').map(Number);
  const index = year * 12 + (month - 1) - (months - 1);
  return `${Math.floor(index / 12)}-${String((index % 12) + 1).padStart(2, '0')}-01`;
}

export default function Investor() {
  const [data, setData] = useState<InvestorSummary | null>(null);
  const [error, setError] = useState('');
  const [months, setMonths] = useState(6);
  useEffect(() => {
    setData(null); setError('');
    api.get<InvestorSummary>('/investor/summary', { params: { date_from: rangeStart(months), date_to: todayUzbekistan() } })
      .then((response) => setData(response.data)).catch((reason) => setError(errorMessage(reason)));
  }, [months]);
  if (!data && !error) return <div className="page-loading"><Spin size="large" /></div>;
  const rows = (data?.months ?? []).map((item) => ({ ...item, label: `${monthName(item.month)} ${item.year}` }));
  return <div className="page-stack">
    <PageHeading eyebrow={uz.investor.eyebrow} title={uz.investor.title} subtitle={uz.investor.subtitle} />
    <Segmented value={months} onChange={(value) => setMonths(Number(value))} options={[3, 6, 12].map((value) => ({ value, label: uz.investor.period[value as 3 | 6 | 12] }))} />
    {error && <Alert type="error" showIcon message={uz.common.noData} description={error} />}
    {data && <>
      <Row gutter={[12, 12]}>
        <Col xs={24} sm={12} lg={6}><Metric label={uz.investor.revenue} value={formatMoney(data.revenue)} /></Col>
        <Col xs={24} sm={12} lg={6}><Metric label={uz.investor.expenses} value={formatMoney(data.expenses)} /></Col>
        <Col xs={24} sm={12} lg={6}><Metric label={uz.investor.profit} value={formatMoney(data.net_profit)} /></Col>
        <Col xs={24} sm={12} lg={6}><Metric label={uz.investor.debt} value={formatMoney(data.outstanding_debt)} /></Col>
        {data.occupancy_rate !== null && <Col xs={24} sm={12} lg={6}><Metric label={`${uz.investor.occupancy} · ${uz.investor.occupancyNote}`} value={`${data.occupancy_rate}%`} /></Col>}
      </Row>
      <Panel title={uz.investor.trend} className="dashboard-chart-panel">
        <div className="chart-box dashboard-chart-box"><ResponsiveContainer width="100%" height="100%"><AreaChart data={rows} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="#ecefeb" /><XAxis dataKey="label" tick={{ fontSize: 9 }} /><YAxis tick={{ fontSize: 9 }} width={46} />
          <Tooltip formatter={(value) => formatMoney(Number(value))} /><Area type="monotone" dataKey="net_profit" name={uz.investor.profit} stroke="#34745b" fill="#e7f3eb" />
        </AreaChart></ResponsiveContainer></div>
      </Panel>
      <Panel title={uz.investor.trend}>
        <Table rowKey={(row) => `${row.year}-${row.month}`} dataSource={rows} pagination={false} locale={{ emptyText: uz.investor.noData }} columns={[
          { title: 'Oy', dataIndex: 'label' }, { title: uz.investor.revenue, dataIndex: 'revenue', render: formatMoney },
          { title: uz.investor.expenses, dataIndex: 'expenses', render: formatMoney }, { title: uz.investor.profit, dataIndex: 'net_profit', render: formatMoney },
        ]} />
      </Panel>
    </>}
  </div>;
}
