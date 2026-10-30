import { useCallback, useEffect, useMemo, useState, type DragEvent } from 'react';
import dayjs, { type Dayjs } from 'dayjs';
import { Alert, Avatar, Button, DatePicker, Dropdown, Form, Input, Modal, Progress, Segmented, Select, Switch, Tag, Tooltip, notification } from 'antd';
import { CalendarOutlined, FireOutlined, HomeOutlined, MoreOutlined, ReloadOutlined, UserOutlined } from '@ant-design/icons';
import { useSearchParams } from 'react-router-dom';
import { api, errorMessage } from '../api';
import { useAuth } from '../auth';
import { formatDate, uz } from '../locales/uz';
import { playSound } from '../sound';
import type { Page, Room, StaffTask, TaskAssignee, TaskPriority, TaskStatus, TaskSummary } from '../types';
import { PageHeading } from './shared';

type Scope = 'all' | 'mine' | 'created';
type TaskForm = { title: string; description?: string; priority: TaskPriority; due_date?: Dayjs | null; assignee_id?: string | null; room_id?: string | null };

const boardColumns: TaskStatus[] = ['TODO', 'IN_PROGRESS', 'DONE'];
const priorityColor: Record<TaskPriority, string> = { URGENT: 'red', HIGH: 'orange', NORMAL: 'green', LOW: 'default' };
const priorityOptions = (Object.keys(uz.tasks.priority) as TaskPriority[]).map((value) => ({ value, label: uz.tasks.priority[value] }));

function initials(name: string) {
  return name.trim().split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toLocaleUpperCase('uz-UZ');
}

export default function Tasks() {
  const { user } = useAuth();
  const [notice, holder] = notification.useNotification();
  const [form] = Form.useForm<TaskForm>();
  const [params, setParams] = useSearchParams();
  const [tasks, setTasks] = useState<StaffTask[]>([]);
  const [summary, setSummary] = useState<TaskSummary | null>(null);
  const [assignees, setAssignees] = useState<TaskAssignee[]>([]);
  const [rooms, setRooms] = useState<Room[]>([]);
  const [scope, setScope] = useState<Scope>('all');
  const [query, setQuery] = useState('');
  const [showCancelled, setShowCancelled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [editing, setEditing] = useState<StaffTask | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [dragId, setDragId] = useState<string | null>(null);
  const [dropTarget, setDropTarget] = useState<TaskStatus | null>(null);

  const load = useCallback(async () => {
    setError('');
    try {
      const [list, stats] = await Promise.all([
        api.get<StaffTask[]>('/tasks', { params: { scope, q: query || undefined, include_cancelled: showCancelled } }),
        api.get<TaskSummary>('/tasks/summary'),
      ]);
      setTasks(list.data); setSummary(stats.data);
    } catch (e) { setError(errorMessage(e)); }
    finally { setLoading(false); }
  }, [scope, query, showCancelled]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    api.get<TaskAssignee[]>('/tasks/assignees').then((r) => setAssignees(r.data)).catch(() => setAssignees([]));
    api.get<Page<Room>>('/rooms', { params: { limit: 500 } }).then((r) => setRooms(r.data.items)).catch(() => setRooms([]));
  }, []);

  const openCreate = useCallback(() => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ priority: 'NORMAL', assignee_id: user?.role === 'OPERATOR' ? undefined : user?.id });
    setModalOpen(true);
    playSound('open');
  }, [form, user]);

  useEffect(() => {
    if (params.get('new') !== '1') return;
    openCreate();
    const next = new URLSearchParams(params);
    next.delete('new');
    setParams(next, { replace: true });
  }, [params, setParams, openCreate]);

  const openEdit = (task: StaffTask) => {
    setEditing(task);
    form.setFieldsValue({
      title: task.title, description: task.description, priority: task.priority,
      due_date: task.due_date ? dayjs(task.due_date) : null, assignee_id: task.assignee_id, room_id: task.room_id,
    });
    setModalOpen(true);
    playSound('open');
  };

  const refreshSummary = () => { void api.get<TaskSummary>('/tasks/summary').then((r) => setSummary(r.data)).catch(() => undefined); };

  const patch = async (task: StaffTask, body: Record<string, unknown>) => {
    const previous = tasks;
    if (typeof body.status === 'string') {
      setTasks((items) => items.map((item) => item.id === task.id ? { ...item, status: body.status as TaskStatus } : item));
    }
    try {
      const updated = (await api.patch<StaffTask>(`/tasks/${task.id}`, body)).data;
      setTasks((items) => items.map((item) => item.id === updated.id ? updated : item).filter((item) => showCancelled || item.status !== 'CANCELLED'));
      playSound(body.status === 'DONE' ? 'success' : 'drop');
      refreshSummary();
    } catch (e) {
      setTasks(previous); playSound('error');
      notice.error({ message: 'Vazifani yangilab bo‘lmadi', description: errorMessage(e) });
    }
  };

  const save = async (values: TaskForm) => {
    setBusy(true);
    const body = {
      title: values.title.trim(), description: values.description?.trim() ?? '', priority: values.priority,
      due_date: values.due_date ? values.due_date.format('YYYY-MM-DD') : null,
      assignee_id: values.assignee_id || null, room_id: values.room_id || null,
    };
    try {
      if (editing) await api.patch(`/tasks/${editing.id}`, body);
      else await api.post('/tasks', body);
      playSound('success');
      notice.success({ message: editing ? 'Vazifa yangilandi.' : 'Vazifa yaratildi.' });
      setModalOpen(false); await load();
    } catch (e) { playSound('error'); notice.error({ message: 'Vazifani saqlab bo‘lmadi', description: errorMessage(e) }); }
    finally { setBusy(false); }
  };

  const grouped = useMemo(() => {
    const result: Record<TaskStatus, StaffTask[]> = { TODO: [], IN_PROGRESS: [], DONE: [], CANCELLED: [] };
    tasks.forEach((task) => result[task.status].push(task));
    return result;
  }, [tasks]);

  const onDrop = (status: TaskStatus) => (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDropTarget(null);
    const id = dragId ?? event.dataTransfer.getData('text/plain');
    setDragId(null);
    const task = tasks.find((item) => item.id === id);
    if (task && task.status !== status && task.can_edit) void patch(task, { status });
  };

  const visibleColumns: TaskStatus[] = showCancelled ? [...boardColumns, 'CANCELLED'] : boardColumns;
  const activeTotal = summary ? summary.todo + summary.in_progress + summary.done : 0;
  const percent = activeTotal ? Math.round(((summary?.done ?? 0) / activeTotal) * 100) : 0;

  const card = (task: StaffTask, index: number) => {
    const moveItems = (['TODO', 'IN_PROGRESS', 'DONE', 'CANCELLED'] as TaskStatus[])
      .filter((status) => status !== task.status)
      .map((status) => ({ key: status, label: status === 'CANCELLED' ? uz.tasks.cancel : `${uz.tasks.move}: ${uz.tasks.status[status]}`, danger: status === 'CANCELLED' }));
    return <article
      key={task.id}
      className={`task-card priority-${task.priority.toLowerCase()}${task.is_overdue ? ' is-overdue' : ''}${dragId === task.id ? ' is-dragging' : ''}${task.can_edit ? '' : ' is-readonly'}`}
      style={{ animationDelay: `${Math.min(index, 12) * 35}ms` }}
      draggable={task.can_edit}
      onDragStart={(event) => { event.dataTransfer.setData('text/plain', task.id); event.dataTransfer.effectAllowed = 'move'; setDragId(task.id); }}
      onDragEnd={() => { setDragId(null); setDropTarget(null); }}
    >
      <div className="task-card-top">
        <Tag color={priorityColor[task.priority]} icon={task.priority === 'URGENT' ? <FireOutlined /> : undefined}>{uz.tasks.priority[task.priority]}</Tag>
        {task.can_edit
          ? <Dropdown trigger={['click']} menu={{ items: moveItems, onClick: ({ key }) => void patch(task, { status: key }) }}><Button size="small" type="text" icon={<MoreOutlined />} aria-label={uz.tasks.move} /></Dropdown>
          : <Tooltip title={uz.tasks.readOnly}><span className="task-lock">🔒</span></Tooltip>}
      </div>
      <button type="button" className="task-title" onClick={() => task.can_edit && openEdit(task)} disabled={!task.can_edit}>{task.title}</button>
      {task.description && <p className="task-description">{task.description}</p>}
      <div className="task-meta">
        {task.due_date && <span className={task.is_overdue ? 'task-due overdue' : 'task-due'}><CalendarOutlined /> {formatDate(task.due_date)}{task.is_overdue ? ` · ${uz.tasks.overdue}` : ''}</span>}
        {task.room_number && <span><HomeOutlined /> {task.room_number}</span>}
      </div>
      <div className="task-foot">
        {task.assignee_name
          ? <Tooltip title={task.assignee_name}><Avatar size={22} className="task-avatar">{initials(task.assignee_name)}</Avatar></Tooltip>
          : <span className="task-unassigned"><UserOutlined /> {uz.tasks.unassigned}</span>}
        <small>{task.created_by_name}</small>
      </div>
    </article>;
  };

  const stat = (label: string, value: number | undefined, tone = '') => <div className={`task-stat ${tone}`}><span>{label}</span><strong>{value ?? '—'}</strong></div>;

  return <div className="page-stack tasks-page">{holder}
    <PageHeading eyebrow={uz.tasks.eyebrow} title={uz.tasks.title} subtitle={uz.tasks.subtitle} action={uz.tasks.create} onAction={openCreate} />
    {error && <Alert type="error" showIcon message="Vazifalarni yuklab bo‘lmadi" description={error} action={<Button onClick={() => void load()}>Qayta yuklash</Button>} />}
    <section className="task-stats">
      {stat(uz.tasks.status.TODO, summary?.todo)}
      {stat(uz.tasks.status.IN_PROGRESS, summary?.in_progress, 'tone-blue')}
      {stat(uz.tasks.status.DONE, summary?.done, 'tone-green')}
      {stat(uz.tasks.overdue, summary?.overdue, summary?.overdue ? 'tone-red' : '')}
      {stat(uz.tasks.mine, summary?.mine_open, 'tone-amber')}
      <div className="task-stat task-progress"><span>{uz.tasks.progress}</span><Progress percent={percent} size="small" strokeColor={{ from: '#34745b', to: '#7fc79a' }} /></div>
    </section>
    <div className="toolbar panel task-toolbar">
      <Segmented<Scope> value={scope} onChange={(value) => setScope(value)} options={(Object.keys(uz.tasks.scope) as Scope[]).map((value) => ({ value, label: uz.tasks.scope[value] }))} />
      <Input.Search allowClear className="search-input" placeholder="Sarlavha yoki tavsif bo‘yicha qidirish" onSearch={(value) => setQuery(value.trim())} />
      <label className="task-switch"><Switch size="small" checked={showCancelled} onChange={setShowCancelled} /> {uz.tasks.showCancelled}</label>
      <Button icon={<ReloadOutlined />} onClick={() => { setLoading(true); void load(); }} aria-label="Yangilash" />
    </div>
    {user?.role !== 'OPERATOR' && <Alert type="info" showIcon message={uz.tasks.adminHint} />}
    <section className={`task-board${loading ? ' is-loading' : ''}`} style={{ gridTemplateColumns: `repeat(${visibleColumns.length}, minmax(250px, 1fr))` }}>
      {visibleColumns.map((status) => <div
        key={status}
        className={`task-column column-${status.toLowerCase()}${dropTarget === status ? ' is-drop-target' : ''}`}
        onDragOver={(event) => { if (dragId) { event.preventDefault(); setDropTarget(status); } }}
        onDragLeave={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDropTarget(null); }}
        onDrop={onDrop(status)}
      >
        <header><span className="task-column-dot" /><strong>{uz.tasks.status[status]}</strong><span className="task-column-count">{grouped[status].length}</span></header>
        <div className="task-column-body">
          {grouped[status].length ? grouped[status].map(card) : <div className="task-empty">{uz.tasks.empty}</div>}
        </div>
      </div>)}
    </section>
    <Modal open={modalOpen} title={editing ? uz.tasks.edit : uz.tasks.create} onCancel={() => setModalOpen(false)} onOk={() => form.submit()} confirmLoading={busy} okText={uz.common.save} cancelText={uz.common.cancel} destroyOnClose>
      <Form form={form} layout="vertical" onFinish={(values) => void save(values)}>
        <Form.Item name="title" label={uz.tasks.fields.title} rules={[{ required: true, whitespace: true, min: 2, max: 160, message: 'Sarlavhani 2–160 belgi oralig‘ida kiriting.' }]}><Input maxLength={160} autoFocus /></Form.Item>
        <Form.Item name="description" label={uz.tasks.fields.description}><Input.TextArea rows={3} maxLength={4000} showCount /></Form.Item>
        <div className="form-grid">
          <Form.Item name="priority" label={uz.tasks.fields.priority} rules={[{ required: true, message: uz.validation.required }]}><Select options={priorityOptions} /></Form.Item>
          <Form.Item name="due_date" label={uz.tasks.fields.due_date}><DatePicker format="DD.MM.YYYY" style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="assignee_id" label={uz.tasks.fields.assignee}><Select allowClear placeholder={uz.tasks.unassigned} options={assignees.map((item) => ({ value: item.id, label: `${item.full_name} · ${uz.role[item.role]}` }))} /></Form.Item>
          <Form.Item name="room_id" label={uz.tasks.fields.room}><Select allowClear showSearch optionFilterProp="label" placeholder="Xonasiz" options={rooms.map((room) => ({ value: room.id, label: `${room.number}-xona` }))} /></Form.Item>
        </div>
      </Form>
    </Modal>
  </div>;
}
