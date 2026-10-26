import { useState } from 'react';
import { Alert, Button, DatePicker, Select, Space, notification } from 'antd';
import { DownloadOutlined } from '@ant-design/icons';
import { api, errorMessage } from '../api';
import { PageHeading, Panel } from './shared';

const reportTypes = [
  {key:'residents',title:'Yashovchilar ro‘yxati',detail:'Aloqa, xona va to‘lov holati bilan to‘liq ro‘yxat.'},
  {key:'rooms',title:'Xonalar bandligi',detail:'Har bir xonaning sig‘imi va hozirgi bandligi.'},
  {key:'payments',title:'To‘lovlar tarixi',detail:'Tanlangan oraliqda qabul qilingan barcha to‘lovlar.'},
  {key:'debts',title:'Qarzdorliklar',detail:'Ochiq to‘lov davri va qolgan qarzlar.'},
  {key:'overdue',title:'Muddati o‘tgan to‘lovlar',detail:'Muddati o‘tgan davrlar va kechikish kunlari.'},
  {key:'revenue',title:'Haqiqiy tushum',detail:'Kunlik, haftalik yoki oylik amaldagi tushum.'},
  {key:'expenses',title:'Xarajatlar',detail:'Sana oralig‘idagi xarajatlar, toifalar va to‘lov usullari.'},
];

export default function Reports() {
  const [notice, holder] = notification.useNotification();
  const [dates, setDates] = useState<[string|undefined,string|undefined]>([undefined,undefined]);
  const [interval, setInterval] = useState('month');
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const download = async (kind:string, format:'xlsx'|'csv'|'pdf') => {
    const key = `${kind}-${format}`; setBusy(key); setError('');
    try {
      const response = await api.get(`/reports/${kind}.${format}`, {params:{date_from:dates[0],date_to:dates[1],interval},responseType:'blob'});
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a'); link.href=url; link.download=`rs-best-hostel-${kind}-${new Date().toISOString().slice(0,10)}.${format}`; link.click(); URL.revokeObjectURL(url);
      notice.success({message:'Hisobot yuklab olindi.'});
    } catch (e) { setError(errorMessage(e)); notice.error({message:'Hisobotni yaratib bo‘lmadi',description:errorMessage(e)}); }
    finally { setBusy(''); }
  };
  return <div className="page-stack">{holder}
    <PageHeading eyebrow="TAHLIL VA EKSPORT" title="Hisobotlar" subtitle="Ma’lumotlarni sana oralig‘i bo‘yicha Excel, CSV yoki PDF formatida yuklab oling."/>
    {error&&<Alert type="error" showIcon message="Hisobot tayyorlanmadi" description={error}/>}
    <div className="toolbar panel"><span className="toolbar-label">Sana oralig‘i</span><DatePicker.RangePicker format="DD.MM.YYYY" onChange={(v)=>setDates([v?.[0]?.format('YYYY-MM-DD'),v?.[1]?.format('YYYY-MM-DD')])}/><Select value={interval} onChange={setInterval} options={[{value:'day',label:'Kunlik'},{value:'week',label:'Haftalik'},{value:'month',label:'Oylik'}]} /><Button type="link" onClick={()=>setDates([undefined,undefined])}>Tozalash</Button></div>
    <div className="report-grid">{reportTypes.map((item)=><Panel key={item.key} title={item.title} className="report-card"><p>{item.detail}</p><Space wrap>{(['xlsx','csv','pdf'] as const).map((format)=><Button key={format} icon={<DownloadOutlined/>} loading={busy===`${item.key}-${format}`} onClick={()=>void download(item.key,format)}>{format.toUpperCase()}</Button>)}</Space></Panel>)}</div>
    <div className="dashboard-footnote">Eksportdagi ustun nomlari o‘zbek tilida. CSV fayllari UTF-8 kodlashida saqlanadi.</div>
  </div>;
}
