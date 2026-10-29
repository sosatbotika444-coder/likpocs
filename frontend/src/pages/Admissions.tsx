import { useEffect, useMemo, useRef, useState } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import { Alert, Button, Checkbox, Col, DatePicker, Descriptions, Drawer, Form, Input, InputNumber, Modal, Progress, Row, Select, Space, Spin, Steps, Table, Tabs, Tag, Typography, notification } from 'antd';
import { CopyOutlined, DownloadOutlined, PlusOutlined, ReloadOutlined, SearchOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { api, errorMessage } from '../api';
import { formatDate, formatMoney } from '../locales/uz';
import { useAuth } from '../auth';
import type { AdmissionSettings, AdmissionSummary, Application, ApplicationFile, ApplicationQueueItem, Campaign, CustomField, Dormitory, Invitation, Page, PublicApplication, PublicApplicationFile, PublicCampaign, Room } from '../types';
import { Actions, EmptyBlock, PageHeading, Panel } from './shared';

const { Text } = Typography;
const statusLabels: Record<string, string> = {
  DRAFT: 'Qoralama', SUBMITTED: 'Yuborildi', IN_REVIEW: 'Tekshiruvda', NEEDS_INFO: 'Aniqlik kerak',
  APPROVED: 'Tasdiqlandi', REJECTED: 'Rad etildi', CANCELLED: 'Bekor qilindi', ARCHIVED: 'Arxiv',
};
const aiStatusLabels: Record<string, string> = {
  COMPLETED: 'Maydonlar topildi', NO_FIELDS: 'Ma\u2019lumot topilmadi',
  NOT_CONFIGURED: 'AI sozlanmagan', CONSENT_REQUIRED: 'AI roziligi berilmagan',
  PROCESSING: 'AI tahlil qilmoqda', FAILED: 'AI tahlili bajarilmadi', DELETED: 'O\u2018chirildi',
};
const dataLabels: Record<string, string> = {
  first_name_latin: 'Ism (lotin)', last_name_latin: 'Familiya (lotin)', middle_name_latin: 'Otasining ismi (lotin)',
  first_name_cyrillic: 'Ism (kirill)', last_name_cyrillic: 'Familiya (kirill)', middle_name_cyrillic: 'Otasining ismi (kirill)',
  birth_date: 'Tug‘ilgan sana', nationality: 'Fuqarolik', gender: 'Jins', phone: 'Telefon', email: 'Elektron pochta',
  address: 'Manzil', emergency_name: 'Favqulodda aloqa', emergency_phone: 'Favqulodda telefon', institution: 'Ta’lim muassasasi',
  faculty: 'Fakultet yoki yo‘nalish', course: 'Kurs', study_group: 'Guruh', study_start: 'O‘qish boshlanishi', study_end: 'O‘qish tugashi',
  requested_move_in: 'Ko‘chib kirish sanasi', requested_move_out: 'Ko‘chib chiqish sanasi', preferences: 'Joylashish istaklari',
  photo: 'Yashovchi surati', additional_data: 'Qo‘shimcha ma’lumot',
};
const copyText = async (value: string) => { await navigator.clipboard.writeText(value); };
const isoDate = (value: Dayjs | string | null | undefined): string | null => value && dayjs.isDayjs(value) ? value.format('YYYY-MM-DD') : value ? String(value).slice(0, 10) : null;
const publicDateFields = ['birth_date', 'study_start', 'study_end', 'requested_move_in', 'requested_move_out'];

function statusTag(status: string) {
  const color = status === 'APPROVED' ? 'green' : status === 'REJECTED' ? 'red' : status === 'NEEDS_INFO' ? 'orange' : status === 'IN_REVIEW' ? 'blue' : 'default';
  return <Tag color={color}>{statusLabels[status] || status}</Tag>;
}

function AdmissionMetric({ label, value, note, tone = '' }: { label: string; value: string | number; note?: string; tone?: string }) {
  return <div className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong>{note && <small>{note}</small>}</div>;
}

function PublicIntake() {
  const [form] = Form.useForm<Record<string, unknown>>();
  const [notice, holder] = notification.useNotification();
  const [campaign, setCampaign] = useState<PublicCampaign | null>(null);
  const [application, setApplication] = useState<PublicApplication | null>(null);
  const [files, setFiles] = useState<PublicApplicationFile[]>([]);
  const [csrf, setCsrf] = useState('');
  const [step, setStep] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [accessCode, setAccessCode] = useState('');
  const [codeEntry, setCodeEntry] = useState('');
  const [accessRequired, setAccessRequired] = useState(false);
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [retryingFileIds, setRetryingFileIds] = useState<string[]>([]);
  const processingPolls = useRef<Set<string>>(new Set());
  const [autofilledFields, setAutofilledFields] = useState<string[]>([]);
  const [aiProcessingConsent, setAIProcessingConsent] = useState(false);
  const exchangeStarted = useRef(false);
  const isClarification = application?.status === 'NEEDS_INFO';

  const applyExtractedData = (uploadedFiles: PublicApplicationFile[]) => {
    const values: Record<string, unknown> = {};
    const filled: string[] = [];
    for (const file of uploadedFiles) {
      if (file.kind !== 'DOCUMENT') continue;
      for (const [field, extracted] of Object.entries(file.extracted_data || {})) {
        if (!extracted || !(field in dataLabels) || field in values) continue;
        const existing = form.getFieldValue(field);
        if (existing !== undefined && existing !== null && existing !== '') continue;
        const value = field === 'birth_date' ? dayjs(extracted) : extracted;
        if (dayjs.isDayjs(value) && !value.isValid()) continue;
        values[field] = value;
        filled.push(field);
      }
    }
    if (filled.length) {
      form.setFieldsValue(values as never);
      setAutofilledFields((current) => [...new Set([...current, ...filled])]);
    }
    return filled;
  };

  const hydrate = (data: PublicApplication, campaignData: PublicCampaign, csrfToken: string) => {
    setApplication(data);
    setCampaign(campaignData);
    setAIProcessingConsent(false);
    setCsrf(csrfToken);
    const values: Record<string, unknown> = { ...data };
    for (const field of publicDateFields) values[field] = data[field as keyof PublicApplication] ? dayjs(data[field as keyof PublicApplication] as string) : null;
    for (const field of campaignData.custom_fields) {
      const value = data.additional_data?.[field.key] ?? null;
      values[field.key] = field.kind === 'date' && value ? dayjs(String(value)) : value;
    }
    form.setFieldsValue(values as never);
    setAutofilledFields([]);
    setAccessRequired(false);
  };

  const loadSession = async () => {
    const result = await api.get<{ csrf_token: string; campaign: PublicCampaign; application: PublicApplication }>('/public/application');
    hydrate(result.data.application, result.data.campaign, result.data.csrf_token);
    const uploaded = await api.get<PublicApplicationFile[]>('/public/application/files');
    setFiles(uploaded.data);
    applyExtractedData(uploaded.data);
  };

  useEffect(() => {
    if (exchangeStarted.current) return;
    exchangeStarted.current = true;
    const token = window.location.hash.slice(1);
    if (token) {
      window.history.replaceState(window.history.state, '', window.location.pathname);
      const keyName = 'dormflow.public.draft-key';
      const draftKey = sessionStorage.getItem(keyName) || crypto.randomUUID();
      sessionStorage.setItem(keyName, draftKey);
      void api.post<{ csrf_token: string; campaign: PublicCampaign; application: PublicApplication }>('/public/invitations/exchange', { token, draft_key: draftKey })
        .then(async (result) => {
          hydrate(result.data.application, result.data.campaign, result.data.csrf_token);
          const uploaded = (await api.get<PublicApplicationFile[]>('/public/application/files')).data;
          setFiles(uploaded);
          applyExtractedData(uploaded);
        })
        .catch((error: unknown) => { setAccessRequired(true); notice.error({ message: 'Taklif havolasi ochilmadi', description: errorMessage(error) }); })
        .finally(() => setLoading(false));
    } else {
      void loadSession().catch(() => setAccessRequired(true)).finally(() => setLoading(false));
    }
  }, []);

  const enterWithCode = async () => {
    setBusy(true);
    try {
      await api.post('/public/application/access-code', { access_code: codeEntry.trim() });
      await loadSession();
      notice.success({ message: 'Arizangiz ochildi.' });
    } catch (error) { notice.error({ message: 'Kirish kodi tekshirilmadi', description: errorMessage(error) }); }
    finally { setBusy(false); }
  };

  const payloadFrom = (values: Record<string, unknown>, pickedFields?: string[]) => {
    const payload: Record<string, unknown> = {};
    const allowed = pickedFields ? new Set(pickedFields) : null;
    for (const field of publicDateFields) {
      if (!allowed || allowed.has(field)) payload[field] = isoDate(values[field] as Dayjs | string | null | undefined);
    }
    const directFields = ['first_name_latin', 'last_name_latin', 'middle_name_latin', 'first_name_cyrillic', 'last_name_cyrillic', 'middle_name_cyrillic', 'nationality', 'gender', 'phone', 'email', 'address', 'emergency_name', 'emergency_phone', 'institution', 'faculty', 'course', 'study_group', 'preferences'];
    for (const field of directFields) if ((!allowed || allowed.has(field)) && field in values) payload[field] = values[field];
    const custom = campaign?.custom_fields || [];
    const requestedCustom = pickedFields?.filter((field) => custom.some((item) => item.key === field));
    if (!allowed || allowed.has('additional_data') || (requestedCustom?.length ?? 0) > 0) {
      const existing = application?.additional_data || {};
      const additional: Record<string, string | boolean | null> = { ...existing };
      for (const field of custom) {
        if (!allowed || allowed.has('additional_data') || requestedCustom?.includes(field.key)) {
          const value = values[field.key];
          if (value !== undefined) additional[field.key] = field.kind === 'date' ? isoDate(value as Dayjs | string | null) : value as string | boolean | null;
        }
      }
      payload.additional_data = additional;
    }
    return payload;
  };

  const saveDraft = async (fields?: string[]) => {
    const values = form.getFieldsValue(true);
    const payload = payloadFrom(values, fields);
    await api.patch('/public/application', payload, { headers: { 'X-CSRF-Token': csrf } });
    return payload;
  };

  const waitForAI = async (fileId: string, initial: PublicApplicationFile) => {
    let current = initial;
    for (let attempt = 0; attempt < 65 && current.ai_status === 'PROCESSING'; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 800));
      const result = await api.get<PublicApplicationFile[]>('/public/application/files');
      const updated = result.data.find((item) => item.id === fileId);
      if (!updated) return current;
      current = updated;
      setFiles((existing) => existing.map((item) => item.id === fileId ? updated : item));
    }
    return current;
  };

  const retryAI = async (file: PublicApplicationFile) => {
    if (!aiProcessingConsent) {
      notice.warning({ message: 'Avval AI tahliliga rozilik bering.' });
      return;
    }
    setRetryingFileIds((current) => [...current, file.id]);
    try {
      const result = await api.post<PublicApplicationFile>(`/public/application/files/${file.id}/extract`, null, {
        headers: { 'X-CSRF-Token': csrf, 'X-AI-Processing-Consent': 'true' },
      });
      setFiles((current) => current.map((item) => item.id === file.id ? result.data : item));
      notice.info({ message: 'Hujjat AI tahliliga yuborildi.' });
    } catch (error) {
      notice.error({ message: 'AI tahlilini qayta boshlash imkoni bo‘lmadi', description: errorMessage(error) });
    } finally {
      setRetryingFileIds((current) => current.filter((id) => id !== file.id));
    }
  };

  useEffect(() => {
    for (const file of files) {
      if (file.ai_status !== 'PROCESSING' || processingPolls.current.has(file.id)) continue;
      processingPolls.current.add(file.id);
      void waitForAI(file.id, file)
        .then((completed) => {
          applyExtractedData([completed]);
          if (completed.ai_status === 'FAILED') notice.warning({ message: 'AI tahlili bajarilmadi. Qayta urining yoki maydonlarni qo‘lda to‘ldiring.' });
          else if (completed.ai_status === 'NO_FIELDS') notice.info({ message: 'Hujjatdan maydon topilmadi.' });
          else if (completed.ai_status === 'COMPLETED') notice.success({ message: 'Hujjat tahlili yakunlandi.' });
        })
        .catch(() => notice.warning({ message: 'Hujjat saqlandi. AI natijasini yuklashda xatolik yuz berdi.' }))
        .finally(() => processingPolls.current.delete(file.id));
    }
  }, [files]);

  const next = async () => {
    setBusy(true);
    try {
      await form.validateFields(step === 0 ? ['first_name_latin', 'last_name_latin', 'birth_date', 'phone'] : ['institution', 'requested_move_in']);
      await saveDraft(isClarification ? application?.requested_fields : undefined);
      setStep((current) => Math.min(2, current + 1));
    } catch (error) { if (error instanceof Error && !('errorFields' in error)) notice.error({ message: 'Qoralama saqlanmadi', description: errorMessage(error) }); }
    finally { setBusy(false); }
  };

  const upload = async (file: File, kind: 'PHOTO' | 'DOCUMENT', documentType = '') => {
    if (!csrf || !campaign) return;
    const key = kind === 'PHOTO' ? 'PHOTO' : documentType;
    setProgress((current) => ({ ...current, [key]: 1 }));
    const body = new FormData();
    body.append('kind', kind);
    body.append('document_type', documentType);
    body.append('upload', file);
    let uploaded = false;
    try {
      const result = await api.post<PublicApplicationFile>('/public/application/files', body, {
        headers: { 'X-CSRF-Token': csrf, ...(kind === 'DOCUMENT' && aiProcessingConsent ? { 'X-AI-Processing-Consent': 'true' } : {}) },
        onUploadProgress: (event) => setProgress((current) => ({ ...current, [key]: event.total ? Math.min(95, Math.round((event.loaded * 95) / event.total)) : 45 })),
      });
      uploaded = true;
      setFiles((current) => [...current.filter((item) => !(item.kind === kind && (kind === 'PHOTO' || item.document_type === documentType))), result.data]);
      const savedFile = result.data;
      const filled = applyExtractedData([savedFile]);
      const message = filled.length
        ? `Hujjat yuklandi. ${filled.length} ta maydon to’ldirildi.`
        : result.data.ai_status === 'CONSENT_REQUIRED'
          ? 'Hujjat saqlandi. Avtomatik to’ldirish uchun AI roziligini belgilang.'
          : savedFile.ai_status === 'FAILED'
            ? 'Hujjat saqlandi. AI tahlili bajarilmadi; qayta urinib ko’ring.'
          : savedFile.ai_status === 'PROCESSING'
              ? 'Hujjat saqlandi. AI tahlili fon rejimida davom etmoqda.'
              : savedFile.ai_status === 'NO_FIELDS'
                ? 'Hujjat saqlandi, ammo undan maydon topilmadi.'
                : 'Hujjat xavfsiz saqlandi.';
      if (savedFile.ai_status === 'FAILED') notice.warning({ message });
      else notice.success({ message, description: filled.length ? 'Ma’lumotlarni hujjat bilan solishtirib tekshiring.' : undefined });
    } catch (error) { notice.error({ message: uploaded ? 'Hujjat saqlandi, lekin AI natijasini olishda xatolik yuz berdi' : 'Fayl yuklanmadi', description: errorMessage(error) }); }
    finally { setProgress((current) => { const nextValue = { ...current }; delete nextValue[key]; return nextValue; }); }
  };

  const submit = async (values: Record<string, unknown>) => {
    setBusy(true);
    try {
      const changed = payloadFrom(values, isClarification ? application?.requested_fields : undefined);
      if (isClarification && Object.keys(changed).length) await api.post('/public/application/respond', changed, { headers: { 'X-CSRF-Token': csrf } });
      else await saveDraft();
      const result = await api.post<{ reference: string; status: string; access_code: string }>('/public/application/submit', { consent: isClarification || values.consent === true }, { headers: { 'X-CSRF-Token': csrf } });
      setApplication((current) => current ? { ...current, status: result.data.status } : current);
      setAccessCode(result.data.access_code || '');
      sessionStorage.removeItem('dormflow.public.draft-key');
    } catch (error) { notice.error({ message: 'Arizani yuborib bo‘lmadi', description: errorMessage(error) }); }
    finally { setBusy(false); }
  };

  const customFields = campaign?.custom_fields || [];
  const identityDocumentType = campaign?.document_types.find((item) => item === 'ID') || campaign?.document_types.find((item) => item !== 'STUDY_PROOF');
  const isFileRequested = (key: string) => !isClarification || application?.requested_fields.includes(key);

  if (loading) return <main className="public-page"><Spin size="large"/></main>;
  if (accessCode && application) return <main className="public-page"><div className="public-card">{holder}<div className="eyebrow">ARIZA YUBORILDI</div><h1>Arizangiz qabul qilindi</h1><p>Ariza raqami: <strong>{application.reference}</strong></p><Alert type="warning" showIcon message="Kirish kodini xavfsiz joyda saqlang" description="Kod faqat shu oynada ko‘rsatiladi. Ariza holatini ko‘rish va aniqliklarga javob berish uchun kerak bo‘ladi."/><div className="access-code"><code>{accessCode}</code><Button icon={<CopyOutlined/>} onClick={() => void copyText(accessCode).then(() => notice.success({message:'Kod nusxalandi.'}))}>Nusxalash</Button></div><Button type="primary" block onClick={() => setAccessCode('')}>Kod saqlandi</Button></div></main>;
  if (application && ['SUBMITTED', 'IN_REVIEW', 'APPROVED', 'REJECTED', 'CANCELLED', 'ARCHIVED'].includes(application.status)) return <main className="public-page"><div className="public-card">{holder}<div className="eyebrow">RS BEST HOSTEL · QABUL</div><h1>Ariza holati</h1><p>Ariza raqami: <strong>{application.reference}</strong></p><Alert type={application.status === 'REJECTED' ? 'error' : application.status === 'APPROVED' ? 'success' : 'info'} showIcon message={statusLabels[application.status] || application.status} description={application.review_reason || 'Arizangiz xodim tomonidan ko‘rib chiqiladi.'}/></div></main>;
  if (accessRequired || !application || !campaign) return <main className="public-page"><div className="public-card">{holder}<div className="eyebrow">RS BEST HOSTEL · QABUL</div><h1>Ariza holatini tekshirish</h1><p>Taklif havolasini oching yoki ariza yuborilganda berilgan kirish kodini kiriting.</p><Form layout="vertical" onFinish={() => void enterWithCode()}><Form.Item label="Kirish kodi" required><Input value={codeEntry} onChange={(event) => setCodeEntry(event.target.value)} autoComplete="one-time-code"/></Form.Item><Button type="primary" htmlType="submit" loading={busy} block>Kodni tekshirish</Button></Form></div></main>;

  const fileButtons = (requestedOnly: boolean, includePhoto = true, documentTypes = campaign.document_types) => <div className="public-upload-list">
    {includePhoto && (!requestedOnly || isFileRequested('photo')) && <section className="public-upload-item"><div><strong>Yashovchi surati</strong><small>Kamera bilan oling yoki rasm yuklang.</small></div><label className="upload-control"><input type="file" accept="image/jpeg,image/png,image/webp" capture="user" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, 'PHOTO'); event.currentTarget.value = ''; }}/><span>{files.some((item) => item.kind === 'PHOTO') ? 'Suratni almashtirish' : 'Surat tanlash'}</span></label>{progress.PHOTO !== undefined && <Progress percent={progress.PHOTO} size="small"/>}{files.filter((item) => item.kind === 'PHOTO').map((item) => <Tag key={item.id} color="green">{item.original_name}</Tag>)}</section>}
    {documentTypes.filter((documentType) => !requestedOnly || isFileRequested(`document:${documentType}`)).map((documentType) => <section className="public-upload-item" key={documentType}><div><strong>{documentType === 'ID' ? 'Pasport yoki ID karta' : documentType === 'STUDY_PROOF' ? 'O‘qish joyidan ma’lumotnoma' : documentType}</strong><small>PDF, JPEG, PNG yoki WebP.</small></div><label className="upload-control"><input type="file" accept="application/pdf,image/jpeg,image/png,image/webp" capture="environment" onChange={(event) => { const file = event.target.files?.[0]; if (file) void upload(file, 'DOCUMENT', documentType); event.currentTarget.value = ''; }}/><span>{files.some((item) => item.kind === 'DOCUMENT' && item.document_type === documentType) ? 'Hujjatni almashtirish' : 'Hujjat tanlash'}</span></label>{progress[documentType] !== undefined && <Progress percent={progress[documentType]} size="small"/>}{files.filter((item) => item.kind === 'DOCUMENT' && item.document_type === documentType).map((item) => <div className="public-file-result" key={item.id}><Tag color="green">{item.original_name}</Tag><Tag color={item.ai_status === 'FAILED' ? 'red' : item.ai_status === 'COMPLETED' ? 'green' : 'default'}>{aiStatusLabels[item.ai_status] || item.ai_status}</Tag>{item.ai_status === 'PROCESSING' && <small>Hujjat tekshirilmoqda. Maydonlar tayyor bo‘lganda avtomatik kiritiladi.</small>}{item.ai_status === 'FAILED' && <Button size="small" loading={retryingFileIds.includes(item.id)} onClick={() => void retryAI(item)}>AI tahlilini qayta urinish</Button>}</div>)}</section>)}
  </div>;


  const aiConsentControl = campaign.ai_processing_available ? <div className="ai-consent-box"><Alert type="warning" showIcon message="Avtomatik to’ldirish OpenRouter orqali ishlaydi" description="Rozilik bersangiz, hujjat sahifalari OpenRouter orqali tashqi AI provayderiga uzatiladi. AI topgan qiymatlar ariza maydonlariga qo’yiladi. Roziliksiz ham faylni yuklab, ma’lumotlarni qo’lda kiritishingiz mumkin."/><Checkbox checked={aiProcessingConsent} onChange={(event)=>setAIProcessingConsent(event.target.checked)}>Hujjatimni OpenRouter orqali tashqi AI provayderida tahlil qilishga roziman.</Checkbox></div> : null;
  const renderRequestedInputs = () => <div className="form-grid">{application.requested_fields.filter((field) => !field.startsWith('document:') && field !== 'photo').map((field) => {
    const custom = customFields.find((item) => item.key === field);
    if (custom) return <Form.Item key={field} name={field} label={custom.label} rules={[{required:custom.required}]}>{custom.kind === 'select' ? <Select options={custom.options.map((option)=>({value:option,label:option}))}/> : custom.kind === 'checkbox' ? <Checkbox/> : custom.kind === 'date' ? <DatePicker className="full-width"/> : <Input/>}</Form.Item>;
    if (field === 'additional_data') return customFields.map((item) => <Form.Item key={item.key} name={item.key} label={item.label}>{item.kind === 'select' ? <Select options={item.options.map((option)=>({value:option,label:option}))}/> : item.kind === 'checkbox' ? <Checkbox/> : item.kind === 'date' ? <DatePicker className="full-width"/> : <Input/>}</Form.Item>);
    if (!(field in dataLabels) || field === 'photo' || field === 'additional_data') return null;
    return <Form.Item key={field} name={field} label={dataLabels[field]}>{publicDateFields.includes(field) ? <DatePicker className="full-width"/> : field === 'gender' ? <Select options={[{value:'FEMALE',label:'Ayol'},{value:'MALE',label:'Erkak'}]}/> : <Input/>}</Form.Item>;
  })}</div>;

  return <main className="public-page"><div className="public-card public-card-wide">{holder}<div className="eyebrow">RS BEST HOSTEL · {campaign.name.toLocaleUpperCase('uz-UZ')}</div><h1>{isClarification ? 'Arizani to‘ldiring' : 'Yotoqxonaga ariza'}</h1>
    {isClarification && <Alert type="warning" showIcon message="Qo‘shimcha ma’lumot so‘raldi" description={application.review_reason}/>}
    {!isClarification && autofilledFields.length > 0 && <Alert type="success" showIcon message={`Hujjatdan ${autofilledFields.length} ta maydon to‘ldirildi`} description={`Tekshiring: ${autofilledFields.map((field) => dataLabels[field] || field).join(', ')}.`} action={step > 0 ? <Button size="small" type="link" onClick={() => setStep(0)}>Maydonlarni ko‘rish</Button> : undefined}/>}
    {!isClarification && <><Steps current={step} size="small" items={[{title:'Shaxsiy ma’lumot'},{title:'O‘qish va muddat'},{title:'Fayllar va rozilik'}]}/><div className="public-progress-label">{step + 1} / 3</div></>}
    <Form form={form} layout="vertical" onFinish={(values) => void submit(values)}>
      {isClarification ? <><h2>So‘ralgan maydonlar</h2>{renderRequestedInputs()}{aiConsentControl}<h2>Fayllar</h2>{fileButtons(true)}</> : <>
        {step === 0 && <>{identityDocumentType && <div className="identity-document-box"><strong>Vaqtingizni tejang</strong>{aiConsentControl}<p>Pasport yoki ID kartani yuklang. O‘qilgan ism, familiya va boshqa topilgan ma’lumotlar maydonlarga tushadi. Ularni tekshirib, qolganini o‘zingiz kiriting.</p>{fileButtons(false, false, [identityDocumentType])}</div>}<div className="form-grid">
          <Form.Item name="first_name_latin" label="Ism (lotin)" rules={[{required:true,message:'Ismingizni kiriting.'}]}><Input autoComplete="given-name" maxLength={80}/></Form.Item><Form.Item name="last_name_latin" label="Familiya (lotin)" rules={[{required:true,message:'Familiyangizni kiriting.'}]}><Input autoComplete="family-name" maxLength={100}/></Form.Item>
          <Form.Item name="middle_name_latin" label="Otasining ismi (lotin)"><Input maxLength={100}/></Form.Item><Form.Item name="birth_date" label="Tug‘ilgan sana" rules={[{required:true,message:'Tug‘ilgan sanani tanlang.'}]}><DatePicker className="full-width" format="DD.MM.YYYY"/></Form.Item>
          <Form.Item name="first_name_cyrillic" label="Ism (kirill)"><Input maxLength={80}/></Form.Item><Form.Item name="last_name_cyrillic" label="Familiya (kirill)"><Input maxLength={100}/></Form.Item><Form.Item name="middle_name_cyrillic" label="Otasining ismi (kirill)"><Input maxLength={100}/></Form.Item><Form.Item name="nationality" label="Fuqarolik"><Input maxLength={100}/></Form.Item>
          <Form.Item name="gender" label="Jins (ixtiyoriy)"><Select allowClear options={[{value:'FEMALE',label:'Ayol'},{value:'MALE',label:'Erkak'}]}/></Form.Item><Form.Item name="phone" label="Telefon" rules={[{required:true,message:'Telefon raqamini kiriting.'}]}><Input type="tel" autoComplete="tel" placeholder="+998 90 123 45 67" maxLength={40}/></Form.Item><Form.Item name="email" label="Elektron pochta"><Input type="email" autoComplete="email" maxLength={320}/></Form.Item><Form.Item name="address" label="Manzil"><Input maxLength={500}/></Form.Item>
          <Form.Item name="emergency_name" label="Favqulodda aloqa uchun yaqin inson"><Input maxLength={160}/></Form.Item><Form.Item name="emergency_phone" label="Favqulodda telefon"><Input type="tel" maxLength={40}/></Form.Item>
        </div></>}
        {step === 1 && <div className="form-grid"><Form.Item name="institution" label="Ta’lim muassasasi" rules={[{required:true,message:'Ta’lim muassasasini kiriting.'}]}><Input maxLength={200}/></Form.Item><Form.Item name="faculty" label="Fakultet yoki yo‘nalish"><Input maxLength={160}/></Form.Item><Form.Item name="course" label="Kurs"><Input maxLength={40}/></Form.Item><Form.Item name="study_group" label="Guruh"><Input maxLength={80}/></Form.Item><Form.Item name="study_start" label="O‘qish davri boshlanishi"><DatePicker className="full-width"/></Form.Item><Form.Item name="study_end" label="O‘qish davri tugashi"><DatePicker className="full-width"/></Form.Item><Form.Item name="requested_move_in" label="Ko‘chib kirish sanasi" rules={[{required:true,message:'Taxminiy sanani kiriting.'}]}><DatePicker className="full-width"/></Form.Item><Form.Item name="requested_move_out" label="Ko‘chib chiqish sanasi"><DatePicker className="full-width"/></Form.Item><Form.Item name="preferences" label="Joylashish bo‘yicha istaklar" className="form-span"><Input.TextArea rows={3} maxLength={2000}/></Form.Item>{customFields.map((field) => <Form.Item key={field.key} name={field.key} label={field.label} valuePropName={field.kind === 'checkbox' ? 'checked' : 'value'} rules={field.required ? [field.kind === 'checkbox' ? {validator:(_, value)=>value ? Promise.resolve() : Promise.reject(new Error('Ushbu maydonni belgilang.'))} : {required:true}] : []}>{field.kind === 'select' ? <Select options={field.options.map((option)=>({value:option,label:option}))}/> : field.kind === 'checkbox' ? <Checkbox/> : field.kind === 'date' ? <DatePicker className="full-width"/> : <Input/>}</Form.Item>)}</div>}
        {step === 2 && <><Alert type="info" showIcon message="Hujjatdan ayrim maydonlar to’ldirilishi mumkin" description="Topilgan ma’lumotlarni hujjat bilan solishtiring. Ariza avtomatik tasdiqlanmaydi."/>{aiConsentControl}<h2>Surat va hujjatlar</h2>{fileButtons(false)}<Form.Item name="consent" valuePropName="checked" rules={[{validator:(_, value)=>value ? Promise.resolve() : Promise.reject(new Error('Rozilikni tasdiqlang.'))}]}><Checkbox>{campaign.consent_text} - {campaign.consent_version}</Checkbox></Form.Item></>}
      </>}
      <div className="public-form-actions">{step > 0 && !isClarification && <Button onClick={() => setStep((current)=>Math.max(0,current-1))}>Orqaga</Button>}{step < 2 && !isClarification ? <Button type="primary" onClick={() => void next()} loading={busy}>Saqlash va davom etish</Button> : <Button type="primary" htmlType="submit" loading={busy}>{isClarification ? 'Javobni yuborish' : 'Arizani yuborish'}</Button>}</div>
    </Form>
  </div></main>;
}

type CampaignFormValues = { name: string; dormitory_id: string; document_types: string[]; consent_version: string; consent_text: string; custom_fields?: {key:string;label:string;kind:CustomField['kind'];required:boolean;options?:string[]}[] };

function StaffAdmissions() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [notice, holder] = notification.useNotification();
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [dormitories, setDormitories] = useState<Dormitory[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [queue, setQueue] = useState<ApplicationQueueItem[]>([]);
  const [total, setTotal] = useState(0);
  const [settings, setSettings] = useState<AdmissionSettings | null>(null);
  const [summary, setSummary] = useState<AdmissionSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('all');
  const [campaignFilter, setCampaignFilter] = useState<string | undefined>();
  const [page, setPage] = useState(1);
  const [detail, setDetail] = useState<Application | null>(null);
  const [duplicates, setDuplicates] = useState<{id:string;first_name:string;last_name:string;phone:string|null;room_number:string|null;agreed_price:number|null;payment_period_days:number|null}[]>([]);
  const [busy, setBusy] = useState(false);
  const [campaignOpen, setCampaignOpen] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [dormOpen, setDormOpen] = useState(false);
  const [editingDormitory, setEditingDormitory] = useState<string | null>(null);
  const [link, setLink] = useState('');
  const [actionKind, setActionKind] = useState<'info'|'approve'|'reject'|null>(null);
  const [campaignForm] = Form.useForm<CampaignFormValues>();
  const [inviteForm] = Form.useForm<Record<string, unknown>>();
  const [dormForm] = Form.useForm<{name:string;address?:string}>();
  const [actionForm] = Form.useForm<Record<string, unknown>>();
  const selectedResidentId = Form.useWatch('resident_id', actionForm);

  const loadLists = async () => {
    setLoading(true);
    try {
      const [campaignResult, invitationResult, dormResult, roomResult, settingsResult, queueResult, summaryResult] = await Promise.all([
        api.get<Campaign[]>('/admissions/campaigns'), api.get<Invitation[]>('/admissions/invitations'), api.get<Dormitory[]>('/dormitories', { params: { include_inactive: user?.role === 'OPERATOR' } }),
        api.get<Page<Room>>('/rooms', { params: { limit: 500 } }), api.get<AdmissionSettings>('/admissions/settings'),
        api.get<Page<ApplicationQueueItem>>('/admissions/applications', { params: { status, campaign_id: campaignFilter, q: query || undefined, skip: (page - 1) * 20, limit: 20 } }),
        api.get<AdmissionSummary>('/admissions/summary'),
      ]);
      setCampaigns(campaignResult.data); setInvitations(invitationResult.data); setDormitories(dormResult.data); setRooms(roomResult.data.items); setSettings(settingsResult.data); setQueue(queueResult.data.items); setTotal(queueResult.data.total); setSummary(summaryResult.data);
    } catch (error) { notice.error({ message: 'Qabul ma’lumotlari yuklanmadi', description: errorMessage(error) }); }
    finally { setLoading(false); }
  };
  useEffect(() => { void loadLists(); }, [status, campaignFilter, query, page]);

  const openDetail = async (id: string) => {
    try {
      const [applicationResult, duplicatesResult] = await Promise.all([
        api.get<Application>(`/admissions/applications/${id}`), api.get(`/admissions/applications/${id}/duplicates`),
      ]);
      setDetail(applicationResult.data); setDuplicates(duplicatesResult.data);
    } catch (error) { notice.error({ message: 'Ariza ochilmadi', description: errorMessage(error) }); }
  };
  const refreshDetail = async () => { if (detail) await openDetail(detail.id); await loadLists(); };
  const mutateStatus = async (invitation: Invitation, action: 'pause'|'resume'|'revoke') => {
    try { await api.post(`/admissions/invitations/${invitation.id}/${action}`); notice.success({message:'Taklif holati yangilandi.'}); await loadLists(); }
    catch (error) { notice.error({message:'Taklif holati o‘zgarmadi',description:errorMessage(error)}); }
  };
  const createInvite = async (values: Record<string, unknown>) => {
    setBusy(true);
    try {
      const result = await api.post<Invitation>('/admissions/invitations', { campaign_id: values.campaign_id, expires_at: (values.expires_at as Dayjs).toISOString(), max_submissions: values.max_submissions });
      setLink(result.data.link || ''); setInviteOpen(false); inviteForm.resetFields(); await loadLists();
    } catch (error) { notice.error({message:'Taklif yaratilmadi',description:errorMessage(error)}); }
    finally { setBusy(false); }
  };
  const createCampaign = async (values: CampaignFormValues) => {
    setBusy(true);
    try {
      await api.post('/admissions/campaigns', { ...values, custom_fields: (values.custom_fields || []).map((field) => ({ ...field, options: field.kind === 'select' ? (field.options || []) : [] })) });
      setCampaignOpen(false); campaignForm.resetFields(); notice.success({message:'Qabul kampaniyasi yaratildi.'}); await loadLists();
    } catch (error) { notice.error({message:'Kampaniya yaratilmadi',description:errorMessage(error)}); }
    finally { setBusy(false); }
  };
  const editDormitory = (row?: Dormitory) => {
    setEditingDormitory(row?.id || null);
    dormForm.setFieldsValue(row ? { name: row.name, address: row.address } : { name: '', address: '' });
    setDormOpen(true);
  };
  const saveDormitory = async (values: {name:string;address?:string}) => {
    try {
      if (editingDormitory) await api.patch(`/dormitories/${editingDormitory}`, values);
      else await api.post('/dormitories', values);
      dormForm.resetFields(); setEditingDormitory(null); setDormOpen(false); await loadLists();
    } catch (error) { notice.error({message:'Yotoqxona saqlanmadi',description:errorMessage(error)}); }
  };
  const runAction = async (values: Record<string, unknown>) => {
    if (!detail || !actionKind) return;
    setBusy(true);
    try {
      if (actionKind === 'info') await api.post(`/admissions/applications/${detail.id}/request-info`, { reason: values.reason, fields: values.fields });
      if (actionKind === 'reject') await api.post(`/admissions/applications/${detail.id}/reject`, { reason: values.reason });
      if (actionKind === 'approve') await api.post(`/admissions/applications/${detail.id}/approve`, {
        reason: values.reason, room_id: values.room_id, move_in: isoDate(values.move_in as Dayjs) as string,
        move_out: isoDate(values.move_out as Dayjs), resident_id: values.resident_id || null,
        ...(values.resident_id ? {} : user?.role === 'OPERATOR' || settings?.billing_change_allowed ? { agreed_price: values.agreed_price, payment_period_days: values.payment_period_days } : {}),
      });
      setActionKind(null); actionForm.resetFields(); await refreshDetail(); notice.success({message:'Ariza yangilandi.'});
    } catch (error) { notice.error({message:'Amal bajarilmadi',description:errorMessage(error)}); }
    finally { setBusy(false); }
  };
  const download = async (file: ApplicationFile) => {
    if (!detail) return;
    try {
      const basePath = `/admissions/applications/${detail.id}/files/${file.id}`;
      if (settings?.storage_backend === 's3') {
        const signed = await api.get<{ url: string }>(`${basePath}/signed-url`);
        const link = document.createElement('a'); link.href = signed.data.url; link.rel = 'noopener'; link.click();
        return;
      }
      const result = await api.get(basePath, { responseType: 'blob' });
      const objectUrl = URL.createObjectURL(result.data as Blob); const anchor = document.createElement('a'); anchor.href = objectUrl; anchor.download = file.original_name; anchor.click(); URL.revokeObjectURL(objectUrl);
    } catch (error) { notice.error({message:'Hujjat yuklab olinmadi',description:errorMessage(error)}); }
  };
  const fieldOptions = useMemo(() => {
    const standard = Object.entries(dataLabels).map(([value,label])=>({value,label}));
    const custom = campaigns.flatMap((campaign)=>campaign.custom_fields.map((field)=>({value:field.key,label:field.label})));
    const documents = campaigns.flatMap((campaign)=>campaign.document_types.map((type)=>({value:`document:${type}`,label:`Hujjat: ${type}`})));
    return [...standard,...custom,...documents];
  }, [campaigns]);

  const queueColumns = [
    { title: 'Ariza', dataIndex: 'reference', render: (value:string,row:ApplicationQueueItem) => <Button type="link" onClick={()=>void openDetail(row.id)}>{value}</Button> },
    { title: 'Talaba', render: (_:unknown,row:ApplicationQueueItem)=><div className="resident-cell"><span className="person-avatar person-small">{row.first_name_latin.slice(0,1)}{row.last_name_latin.slice(0,1)}</span><span><strong>{row.first_name_latin} {row.last_name_latin}</strong><small>{row.phone}</small></span></div> },
    { title: 'Holat', dataIndex: 'status', render: statusTag },
    { title: 'Sana', dataIndex: 'created_at', render: (value:string)=>formatDate(value.slice(0,10),true) },
    { title: '', align:'right' as const, render:(_:unknown,row:ApplicationQueueItem)=><Button onClick={()=>void openDetail(row.id)}>Ko‘rish</Button> },
  ];
  const inviteColumns = [
    {title:'Kampaniya',render:(_:unknown,row:Invitation)=>campaigns.find((item)=>item.id===row.campaign_id)?.name||'—'},
    {title:'Yuborilgan',render:(_:unknown,row:Invitation)=>`${row.submission_count} / ${row.max_submissions}`},
    {title:'Tugash sanasi',dataIndex:'expires_at',render:(value:string)=>formatDate(value.slice(0,10),true)},
    {title:'Holat',dataIndex:'status',render:(value:string)=><Tag color={value==='ACTIVE'?'green':value==='REVOKED'?'red':'default'}>{value}</Tag>},
    {title:'',align:'right' as const,render:(_:unknown,row:Invitation)=><Actions>{row.status==='ACTIVE'?<Button onClick={()=>void mutateStatus(row,'pause')}>Pauza</Button>:row.status==='PAUSED'?<Button onClick={()=>void mutateStatus(row,'resume')}>Davom</Button>:null}{['ACTIVE','PAUSED'].includes(row.status)&&<Button danger onClick={()=>Modal.confirm({title:'Taklif bekor qilinsinmi?',onOk:()=>mutateStatus(row,'revoke')})}>Bekor qilish</Button>}</Actions>},
  ];
  const fileColumns = [
    {title:'Fayl',dataIndex:'original_name',render:(value:string,file:ApplicationFile)=><div><strong>{value}</strong><div><Text type="secondary">{file.kind==='PHOTO'?'Surat':file.document_type} · {Math.ceil(file.size_bytes/1024)} KB</Text></div></div>},
    {title:'Virus tekshiruvi',dataIndex:'scan_status',render:(value:string)=><Tag>{value==='NOT_CONFIGURED'?'Tekshirilmagan':value}</Tag>},
    {title:'AI taklifi',dataIndex:'ai_status',render:(value:string,file:ApplicationFile)=><div><Tag color={value==='COMPLETED'?'green':value==='FAILED'?'red':'default'}>{aiStatusLabels[value]||value}</Tag>{Object.keys(file.extracted_data||{}).length>0&&<details className="ai-result"><summary>{Object.keys(file.extracted_data||{}).length} ta maydon</summary>{Object.entries(file.extracted_data||{}).map(([key,item])=><div key={key}><strong>{dataLabels[key]||key}: </strong>{item}</div>)}<Text type="secondary">Topilgan qiymatlarni asl hujjat bilan solishtiring.</Text></details>}</div>},
    {title:'',align:'right' as const,render:(_:unknown,file:ApplicationFile)=><Button icon={<DownloadOutlined/>} onClick={()=>void download(file)}>Himoyalangan ko‘rish</Button>},
  ];
  const dormitoryColumns = [
    { title: 'Yotoqxona', dataIndex: 'name', render: (name:string, row:Dormitory) => <span>{name}{row.is_default && <Tag className="dorm-default-tag">Asosiy</Tag>}</span> },
    { title: 'Manzil', dataIndex: 'address', render: (value:string) => value || 'Kiritilmagan' },
    { title: 'Holat', dataIndex: 'is_active', render: (active:boolean) => <Tag color={active ? 'green' : 'default'}>{active ? 'Faol' : 'Faol emas'}</Tag> },
    { title: '', align: 'right' as const, render: (_:unknown, row:Dormitory) => <Space><Button onClick={()=>editDormitory(row)}>Tahrirlash</Button><Select disabled={row.is_default} value={row.is_active ? 'ACTIVE' : 'INACTIVE'} onChange={(value)=>void api.patch(`/dormitories/${row.id}`,{is_active:value==='ACTIVE'}).then(loadLists).catch((error:unknown)=>notice.error({message:errorMessage(error)}))} options={[{value:'ACTIVE',label:'Faol'},{value:'INACTIVE',label:'Faol emas'}]}/></Space> },
  ];
  const appDormiRooms = rooms.filter((room)=>room.dormitory_id===detail?.dormitory_id && room.is_active);
  const canDecide = detail && ['SUBMITTED','IN_REVIEW','NEEDS_INFO'].includes(detail.status);
  const statusSummary = [
    ['Yuborildi', summary?.by_status.SUBMITTED || 0],
    ['Tekshiruvda', summary?.by_status.IN_REVIEW || 0],
    ['Aniqlik kerak', summary?.by_status.NEEDS_INFO || 0],
    ['Tasdiqlandi', summary?.by_status.APPROVED || 0],
    ['Rad etildi', summary?.by_status.REJECTED || 0],
    ['Qoralama', summary?.by_status.DRAFT || 0],
    ['Bekor qilindi', summary?.by_status.CANCELLED || 0],
    ['Arxivlandi', summary?.by_status.ARCHIVED || 0],
  ];
  const statisticsPanel = summary ? <div className="page-stack">
    <Text type="secondary">Moliyaviy summalar ariza orqali qo‘shilgan yashovchilarga tegishli. Umumiy hostel daromadi va xarajatlari Boshqaruv panelida ko‘rsatiladi.</Text>
    <Row gutter={[14, 14]}>
      <Col xs={12} md={6}><AdmissionMetric label="Jami yuborilgan ariza" value={summary.total_applications} note={`${summary.applications_this_month} tasi shu oy`} /></Col>
      <Col xs={12} md={6}><AdmissionMetric label="Ko‘rib chiqilmoqda" value={summary.pending_applications} note="Yuborildi, tekshiruvda yoki aniqlik kerak" tone="metric-amber" /></Col>
      <Col xs={12} md={6}><AdmissionMetric label="Shu oy tasdiqlandi" value={summary.approved_this_month} note={`${summary.approved_applications} ta jami tasdiqlangan`} tone="metric-green" /></Col>
      <Col xs={12} md={6}><AdmissionMetric label="Yashovchilar bilan bog‘landi" value={summary.linked_residents} note="Tasdiqlangan arizalardan" /></Col>
    </Row>
    <Row gutter={[14, 14]}>
      <Col xs={24} md={8}><AdmissionMetric label="Kutilayotgan hisob" value={formatMoney(summary.expected_payments)} note="Ochiq to‘lov davrlari summasi" tone="metric-blue" /></Col>
      <Col xs={24} md={8}><AdmissionMetric label="Qarzdorlik" value={formatMoney(summary.outstanding_debt)} note="Ochiq davrlardagi qoldiq" tone="metric-amber" /></Col>
      <Col xs={24} md={8}><AdmissionMetric label="Shu oy haqiqiy tushum" value={formatMoney(summary.actual_revenue_this_month)} note="Faqat qayd etilgan to‘lovlar" tone="metric-green" /></Col>
    </Row>
    <Panel title="Arizalar holati bo‘yicha">
      <div className="finance-list">{statusSummary.map(([label, count])=><div key={label}><span>{label}</span><strong>{count}</strong></div>)}</div>
      <p className="dashboard-footnote">Tasdiqlash yashovchini ro‘yxatga qo‘shadi va belgilangan tarif bo‘yicha hisob ochadi. Pul kelib tushgani faqat «To‘lovlar» bo‘limida qayd qilinganda tushumga qo‘shiladi. Xarajatlar «Boshqaruv paneli» va «Xarajatlar» bo‘limida yuritiladi.</p>
    </Panel>
  </div> : <div className="page-loading"><Spin/></div>;

  return <div className="page-stack">{holder}
    <PageHeading eyebrow="TALABALAR BILAN ISHLASH" title="Qabul va arizalar" subtitle="Takliflar, arizalar va joylashtirishni bitta navbatda boshqaring." action="Taklif yaratish" onAction={()=>{inviteForm.setFieldsValue({max_submissions:25});setInviteOpen(true);}}/>
    {settings && <div className="admission-status-strip"><span>Fayl ombori: <strong>{settings.storage_configured?'tayyor':'sozlanmagan'}</strong></span><span>Saqlash muddati: <strong>{settings.retention_days ? `${settings.retention_days} kun` : 'belgilanmagan'}</strong></span><span>AI: <strong>{settings.ai_configured?'sozlangan':'sozlanmagan'}</strong></span><span>Antivirus: <strong>{settings.antivirus_configured?'tayyor':'sozlanmagan'}</strong></span></div>}
    {!settings?.uploads_enabled && <Alert type="warning" showIcon message="Fayl yuklash sozlamalarini tekshiring" description="Yuklash uchun xususiy fayl ombori va saqlash muddati sozlangan bo‘lishi kerak."/>}
    <Tabs items={[
      {key:'statistics',label:'Statistika',children:statisticsPanel},
      {key:'applications',label:`Arizalar · ${total}`,children:<><div className="toolbar panel"><Input className="search-input" value={search} onChange={(event)=>setSearch(event.target.value)} onPressEnter={()=>{setPage(1);setQuery(search);}} prefix={<SearchOutlined/>} placeholder="Ariza raqami, ism yoki telefon"/><Button onClick={()=>{setPage(1);setQuery(search);}}>Qidirish</Button><Select value={status} onChange={(value)=>{setStatus(value);setPage(1);}} options={[{value:'all',label:'Barcha holatlar'},...Object.entries(statusLabels).map(([value,label])=>({value,label}))]}/><Select allowClear placeholder="Barcha kampaniyalar" value={campaignFilter} onChange={(value)=>{setCampaignFilter(value);setPage(1);}} options={campaigns.map((item)=>({value:item.id,label:item.name}))}/><Button icon={<ReloadOutlined/>} onClick={()=>void loadLists()}/></div><div className="panel table-panel"><Table rowKey="id" loading={loading} dataSource={queue} columns={queueColumns} scroll={{x:780}} pagination={{current:page,pageSize:20,total,onChange:setPage,showTotal:(value)=>`Jami ${value} ta`}} locale={{emptyText:<EmptyBlock title="Hozircha arizalar yo‘q" detail="Yangi takliflar orqali arizalar shu yerda ko‘rinadi."/>}}/></div></>},
      {key:'invitations',label:`Takliflar · ${invitations.length}`,children:<><div className="toolbar panel"><Text type="secondary">Havola tokeni bazada ochiq saqlanmaydi; nusxa faqat yaratilganda ko‘rsatiladi.</Text><Button type="primary" icon={<PlusOutlined/>} onClick={()=>setInviteOpen(true)}>Yangi taklif</Button></div><div className="panel table-panel"><Table rowKey="id" dataSource={invitations} columns={inviteColumns} scroll={{x:760}} pagination={{pageSize:10}} locale={{emptyText:'Takliflar yaratilmagan'}}/></div></>},
      ...(user?.role==='OPERATOR'?[{key:'campaigns',label:`Kampaniyalar · ${campaigns.length}`,children:<><div className="toolbar panel"><Button type="primary" icon={<PlusOutlined/>} onClick={()=>{campaignForm.setFieldsValue({document_types:['ID','STUDY_PROOF'],consent_version:'2026-01',consent_text:'Shaxsiy ma’lumotlarimni qabul arizasini ko‘rib chiqish va joylashtirish maqsadida qayta ishlashga roziman.'});setCampaignOpen(true);}}>Kampaniya yaratish</Button><Button onClick={()=>editDormitory()}>Yotoqxona qo‘shish</Button></div><div className="panel table-panel"><Table rowKey="id" dataSource={campaigns} columns={[{title:'Kampaniya',dataIndex:'name'},{title:'Yotoqxona',render:(_:unknown,row:Campaign)=>dormitories.find((item)=>item.id===row.dormitory_id)?.name||'—'},{title:'Hujjatlar',dataIndex:'document_types',render:(items:string[])=>items.join(', ')||'—'},{title:'Holat',dataIndex:'status',render:(value:string)=><Tag>{value}</Tag>},{title:'',render:(_:unknown,row:Campaign)=><Select size="small" value={row.status} onChange={(value)=>void api.patch(`/admissions/campaigns/${row.id}/status`,null,{params:{status_value:value}}).then(loadLists).catch((error:unknown)=>notice.error({message:errorMessage(error)}))} options={['ACTIVE','PAUSED','CLOSED'].map((value)=>({value,label:value}))}/>}]} pagination={{pageSize:10}} locale={{emptyText:'Kampaniyalar yaratilmagan'}}/></div><Panel title="Yotoqxonalar"><Table rowKey="id" dataSource={dormitories} columns={dormitoryColumns} pagination={{pageSize:8}} locale={{emptyText:'Yotoqxonalar yaratilmagan'}}/></Panel></>}]:[]),
    ]}/>

    <Drawer open={Boolean(detail)} onClose={()=>setDetail(null)} width={Math.min(780,window.innerWidth-20)} title={detail ? `${detail.reference} · ${statusLabels[detail.status]||detail.status}` : ''} extra={detail && <Space>{canDecide && detail.status==='SUBMITTED' && <Button onClick={()=>void api.post(`/admissions/applications/${detail.id}/start-review`).then(refreshDetail).catch((error:unknown)=>notice.error({message:errorMessage(error)}))}>Tekshiruvni boshlash</Button>}{canDecide && <Button type="primary" onClick={()=>{actionForm.resetFields();setActionKind('approve');actionForm.setFieldsValue({move_in:detail.requested_move_in?dayjs(detail.requested_move_in):dayjs(),payment_period_days:settings?.default_period_days||30});}}>Tasdiqlash</Button>}{detail.status==='APPROVED'&&detail.resident_id&&<Button onClick={()=>navigate('/residents?resident_id='+detail.resident_id)}>Yashovchini ochish</Button>}</Space>}>
      {detail && <div className="detail-stack admission-detail">{holder}<div>{statusTag(detail.status)} <Text type="secondary">Yuborildi: {formatDate(detail.created_at.slice(0,10),true)}</Text></div><Alert type="info" showIcon message="AI topgan maydonlar xodimga yordamchi taklif sifatida ko’rsatiladi" description="Har bir qiymatni asl hujjat bilan solishtiring. Yakuniy qarorni xodim qabul qiladi."/><Descriptions bordered size="small" column={2} items={[
        {key:'name',label:'F.I.Sh. (lotin)',children:`${detail.last_name_latin} ${detail.first_name_latin} ${detail.middle_name_latin}`},{key:'name_cyr',label:'F.I.Sh. (kirill)',children:`${detail.last_name_cyrillic} ${detail.first_name_cyrillic} ${detail.middle_name_cyrillic}`},
        {key:'dob',label:'Tug‘ilgan sana',children:formatDate(detail.birth_date,true)},{key:'phone',label:'Telefon',children:detail.phone},{key:'email',label:'Pochta',children:detail.email||'—'},
        {key:'address',label:'Manzil',children:detail.address||'—'},{key:'emergency',label:'Favqulodda aloqa',children:`${detail.emergency_name||'—'} · ${detail.emergency_phone||'—'}`},
        {key:'school',label:'Ta’lim',children:`${detail.institution}${detail.faculty?` · ${detail.faculty}`:''}`},{key:'course',label:'Kurs va guruh',children:`${detail.course||'—'} · ${detail.study_group||'—'}`},
        {key:'stay',label:'So‘ralgan muddat',children:`${formatDate(detail.requested_move_in,true)} — ${formatDate(detail.requested_move_out,true)}`},{key:'consent',label:'Rozilik',children:detail.consent_version||'—'},
        ...Object.entries(detail.additional_data||{}).map(([key,value])=>({key:`extra-${key}`,label:campaigns.flatMap((item)=>item.custom_fields).find((field)=>field.key===key)?.label||key,children:String(value??'—')})),
      ]}/>
      <Panel title="Surat va hujjatlar"><Table rowKey="id" size="small" pagination={false} dataSource={detail.files} columns={fileColumns} locale={{emptyText:'Biriktirilgan fayl yo‘q'}}/></Panel>
      <Panel title="Ichki qayd"><Input.TextArea key={`${detail.id}-${detail.internal_notes}`} rows={3} defaultValue={detail.internal_notes} onBlur={(event)=>{if(event.target.value!==detail.internal_notes)void api.put(`/admissions/applications/${detail.id}/notes`,{internal_notes:event.target.value}).then(refreshDetail).catch((error:unknown)=>notice.error({message:errorMessage(error)}));}}/><small>Bu qayd talabaga ko‘rinmaydi.</small></Panel>
      {detail.events.length>0&&<Panel title="Holatlar tarixi"><Table rowKey={(row)=>`${row.to_status}-${row.created_at}`} size="small" pagination={false} dataSource={detail.events} columns={[{title:'Holat',dataIndex:'to_status',render:statusTag},{title:'Sana',dataIndex:'created_at',render:(value:string)=>formatDate(value.slice(0,10),true)},{title:'Asos',dataIndex:'reason'}]}/></Panel>}
      {canDecide&&<div className="toolbar"><Button onClick={()=>{actionForm.resetFields();setActionKind('info');}}>Aniqlik so‘rash</Button><Button danger onClick={()=>{actionForm.resetFields();setActionKind('reject');}}>Rad etish</Button><Button icon={<ReloadOutlined/>} onClick={()=>{void api.post<{access_code:string}>(`/admissions/applications/${detail.id}/tracking-code`,{reason:'Talaba kirish kodini yo‘qotdi'}).then((result)=>Modal.info({title:'Yangi kirish kodi',content:<div><p>Kod faqat bir marta ko‘rsatiladi. Shaxsni qo‘lda tekshirib talabaga yetkazing.</p><Input readOnly value={result.data.access_code}/></div>})).catch((error:unknown)=>notice.error({message:errorMessage(error)}))}}>Kirish kodini yangilash</Button></div>}
      {duplicates.length>0&&<Panel title="O‘xshash yashovchilar"><p>Bu yozuvlar faqat tekshirish uchun taklif qilindi; avtomatik bog‘lanish bajarilmadi.</p>{duplicates.map((candidate)=><div className="duplicate-candidate" key={candidate.id}><span><strong>{candidate.last_name} {candidate.first_name}</strong><small>{candidate.phone||'Telefon yo‘q'} · {candidate.room_number?`${candidate.room_number}-xona`:'Xona belgilanmagan'}</small></span></div>)}</Panel>}
      </div>}
    </Drawer>
    <Modal open={inviteOpen} title="Cheklangan taklif yaratish" onCancel={()=>setInviteOpen(false)} onOk={()=>inviteForm.submit()} confirmLoading={busy} okText="Havola yaratish" cancelText="Bekor qilish" destroyOnClose><Form form={inviteForm} layout="vertical" onFinish={createInvite}><Form.Item name="campaign_id" label="Kampaniya" rules={[{required:true}]}><Select options={campaigns.filter((item)=>item.status==='ACTIVE').map((item)=>({value:item.id,label:`${item.name} · ${dormitories.find((dorm)=>dorm.id===item.dormitory_id)?.name||''}`}))}/></Form.Item><Form.Item name="expires_at" label="Havola amal qilish muddati" rules={[{required:true}]}><DatePicker showTime className="full-width"/></Form.Item><Form.Item name="max_submissions" label="Arizalar limiti" rules={[{required:true}]}><InputNumber min={1} max={10000} className="full-width"/></Form.Item></Form></Modal>
    <Modal open={Boolean(link)} title="Yangi taklif havolasi" onCancel={()=>setLink('')} footer={<Button type="primary" onClick={()=>void copyText(link).then(()=>notice.success({message:'Havola nusxalandi.'}))}>Havolani nusxalash</Button>}><Alert type="warning" showIcon message="Havola faqat shu oynada ko‘rsatiladi. Uni talabaga xavfsiz yuboring."/><Input readOnly value={link} className="link-field"/></Modal>
    <Modal open={campaignOpen} title="Qabul kampaniyasi" onCancel={()=>setCampaignOpen(false)} onOk={()=>campaignForm.submit()} confirmLoading={busy} okText="Yaratish" cancelText="Bekor qilish" width={640} destroyOnClose><Form form={campaignForm} layout="vertical" onFinish={createCampaign}><Form.Item name="name" label="Kampaniya nomi" rules={[{required:true}]}><Input maxLength={160}/></Form.Item><Form.Item name="dormitory_id" label="Yotoqxona" rules={[{required:true}]}><Select options={dormitories.filter((item)=>item.is_active).map((item)=>({value:item.id,label:item.name}))}/></Form.Item><Form.Item name="document_types" label="Talab qilinadigan hujjatlar" rules={[{required:true}]}><Select mode="tags" options={[{value:'ID',label:'Pasport yoki ID'},{value:'STUDY_PROOF',label:'O‘qish joyidan ma’lumotnoma'}]}/></Form.Item><Form.Item name="consent_version" label="Rozilik matni versiyasi" rules={[{required:true}]}><Input maxLength={40}/></Form.Item><Form.Item name="consent_text" label="Rozilik matni" rules={[{required:true}]}><Input.TextArea rows={3}/></Form.Item><Form.List name="custom_fields">{(fields,{add,remove})=><><Text strong>Qo‘shimcha maydonlar</Text>{fields.map(({key,name,...rest})=><div className="custom-field-row" key={key}><Form.Item {...rest} name={[name,'key']} rules={[{required:true}]}><Input placeholder="kalit_lowercase"/></Form.Item><Form.Item {...rest} name={[name,'label']} rules={[{required:true}]}><Input placeholder="Maydon nomi"/></Form.Item><Form.Item {...rest} name={[name,'kind']} rules={[{required:true}]}><Select options={['text','date','select','checkbox'].map((value)=>({value,label:value}))}/></Form.Item><Form.Item {...rest} name={[name,'options']} label="Tanlov variantlari"><Select mode="tags" tokenSeparators={[',']}/></Form.Item><Form.Item {...rest} name={[name,'required']} valuePropName="checked"><Checkbox>Shart</Checkbox></Form.Item><Button danger onClick={()=>remove(name)}>O‘chirish</Button></div>)}<Button icon={<PlusOutlined/>} onClick={()=>add({kind:'text',required:false})}>Maydon qo‘shish</Button></>}</Form.List></Form></Modal>
    <Modal open={dormOpen} title={editingDormitory ? "Yotoqxonani tahrirlash" : "Yangi yotoqxona"} onCancel={()=>setDormOpen(false)} onOk={()=>dormForm.submit()} okText="Saqlash" cancelText="Bekor qilish"><Form form={dormForm} layout="vertical" onFinish={saveDormitory}><Form.Item name="name" label="Nomi" rules={[{required:true}]}><Input maxLength={160}/></Form.Item><Form.Item name="address" label="Manzil"><Input maxLength={500}/></Form.Item></Form></Modal>
    <Modal open={Boolean(actionKind)} title={actionKind==='info'?'Talabadan aniqlik so‘rash':actionKind==='approve'?'Arizani tasdiqlash':'Arizani rad etish'} onCancel={()=>{setActionKind(null);actionForm.resetFields();}} onOk={()=>actionForm.submit()} confirmLoading={busy} okText="Tasdiqlash" cancelText="Bekor qilish" destroyOnClose>
      <Form form={actionForm} layout="vertical" onFinish={runAction}>
        {actionKind==='info'&&<Form.Item name="fields" label="Talaba to‘ldirishi kerak bo‘lgan maydonlar" rules={[{required:true}]}><Select mode="multiple" options={fieldOptions}/></Form.Item>}
        {actionKind==='approve'&&<><Alert type="info" message="Tasdiqlanganda yashovchi ro‘yxatga qo‘shiladi va birinchi hisob ochiladi. Haqiqiy tushum faqat to‘lov qayd etilganda hisoblanadi." className="modal-alert"/><Form.Item name="room_id" label="Xona" rules={[{required:true}]}><Select onChange={(roomId)=>{const resident=duplicates.find((item)=>item.id===selectedResidentId);const room=appDormiRooms.find((item)=>item.id===roomId);actionForm.setFieldsValue({agreed_price:resident?.agreed_price??room?.price??undefined,payment_period_days:resident?.payment_period_days??actionForm.getFieldValue('payment_period_days')});}} options={appDormiRooms.map((room)=>({value:room.id,label:`${room.number}-xona · ${room.available_beds} bo‘sh o‘rin`}))}/></Form.Item><Form.Item name="move_in" label="Yashash boshlanishi" rules={[{required:true}]}><DatePicker className="full-width"/></Form.Item><Form.Item name="move_out" label="Yashash tugashi"><DatePicker className="full-width"/></Form.Item><Form.Item name="agreed_price" label="Tarif (so‘m / to‘lov davri)" rules={[{required:true,message:"Xona narxini yoki operator belgilagan tarifni kiriting."}]} extra="Xona narxi avtomatik olinadi. Mavjud yashovchi tanlansa, uning amaldagi tarifi saqlanadi."><InputNumber min={0} precision={2} disabled={Boolean(selectedResidentId) || user?.role!=='OPERATOR'&&!settings?.billing_change_allowed} controls={false} className="full-width"/></Form.Item><Form.Item name="payment_period_days" label="To‘lov davri (kun)" rules={[{required:true,message:"To‘lov davrini belgilang."}]}><InputNumber min={1} max={365000} disabled={Boolean(selectedResidentId) || user?.role!=='OPERATOR'&&!settings?.billing_change_allowed} className="full-width"/></Form.Item>{duplicates.length>0&&<Form.Item name="resident_id" label="Mavjud yashovchi bilan bog‘lash (ixtiyoriy)"><Select allowClear onChange={(residentId)=>{const selected=duplicates.find((item)=>item.id===residentId);const room=appDormiRooms.find((item)=>item.id===actionForm.getFieldValue('room_id'));actionForm.setFieldsValue({agreed_price:selected?.agreed_price??room?.price??undefined,payment_period_days:selected?.payment_period_days??settings?.default_period_days??30});}} options={duplicates.map((item)=>({value:item.id,label:`${item.last_name} ${item.first_name} · ${item.phone||''}`}))}/></Form.Item>}</>}
        <Form.Item name="reason" label={actionKind==='info'?'Talabaga ko‘rinadigan izoh':'Qaror uchun asos'} rules={[{required:true,min:3}]}><Input.TextArea rows={3} maxLength={2000}/></Form.Item>
      </Form>
    </Modal>
  </div>;
}

export default function Admissions() {
  const { user } = useAuth();
  return user ? <StaffAdmissions/> : <PublicIntake/>;
}

export function PublicApplication() { return <PublicIntake/>; }
