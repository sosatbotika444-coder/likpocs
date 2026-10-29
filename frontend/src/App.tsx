import { lazy, Suspense, useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, Outlet, Route, Routes, useLocation, useNavigate } from 'react-router-dom';
import { Avatar, Badge, Button, Dropdown, Layout, Menu, Spin, Typography, Grid, Drawer, notification } from 'antd';
import {
  AppstoreOutlined, BellOutlined, FileExcelOutlined,
  HomeOutlined, LogoutOutlined, MenuOutlined, SettingOutlined, TeamOutlined, UserOutlined, SolutionOutlined,
  WalletOutlined, DollarCircleOutlined, AuditOutlined, QuestionCircleOutlined,
} from '@ant-design/icons';
import { api, errorMessage } from './api';
import { useAuth } from './auth';
import { uz, formatDate } from './locales/uz';
import type { Notification as AppNotification, Role } from './types';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Residents = lazy(() => import('./pages/Residents'));
const Rooms = lazy(() => import('./pages/Rooms'));
const Payments = lazy(() => import('./pages/Payments'));
const Reports = lazy(() => import('./pages/Reports'));
const Expenses = lazy(() => import('./pages/Expenses'));
const SettingsPage = lazy(() => import('./pages/Settings'));
const Landing = lazy(() => import('./pages/Landing'));
const Admissions = lazy(() => import('./pages/Admissions'));
const AdminGuide = lazy(() => import('./pages/AdminGuide'));
const PublicApplication = lazy(async () => {
  const module = await import('./pages/Admissions');
  return { default: module.PublicApplication };
});

const { Header, Sider, Content } = Layout;
const { Text } = Typography;
const routeTitles: Record<string, string> = {
  '/app': uz.nav.dashboard, '/residents': uz.nav.residents, '/rooms': uz.nav.rooms,
  '/payments': uz.nav.payments, '/expenses': uz.nav.expenses, '/reports': uz.nav.reports, '/settings': uz.nav.settings,
  '/admissions': uz.nav.admissions, '/guide': 'Administrator uchun qo‘llanma',
};

function Login() {
  const { login, user, loading } = useAuth();
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();
  const [notice, contextHolder] = notification.useNotification();
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    try {
      await login(String(form.get('email')), String(form.get('password')));
      const destination = (location.state as { from?: { pathname?: string } } | null)?.from?.pathname;
      navigate(destination || '/app', { replace: true });
    } catch (error) {
      notice.error({ message: 'Tizimga kirib bo‘lmadi', description: errorMessage(error), placement: 'topRight' });
    } finally { setBusy(false); }
  };
  if (loading) return <div className="auth-loading"><Spin size="large" /></div>;
  if (user) return <Navigate to="/app" replace />;
  return <main className="login-page">
    {contextHolder}
    <section className="login-art">
      <Link className="brand brand-light" to="/"><span className="brand-symbol"><HomeOutlined /></span><span className="brand-name">RS <span>Best Hostel</span><small>{uz.brand.subtitle}</small></span></Link>
      <div className="login-art-copy"><div className="eyebrow">{uz.login.eyebrow}</div><h1>{uz.login.title}</h1><p>{uz.login.subtitle}</p><div className="login-workflow"><div><span>01</span><strong>Qabul arizalarini ko‘rib chiqing</strong></div><div><span>02</span><strong>Xona va yashovchilarni boshqaring</strong></div><div><span>03</span><strong>To‘lovlarni qayd etib, hisobni kuzating</strong></div></div></div>
      <div className="login-art-footer">{uz.login.security}</div>
    </section>
    <section className="login-form-side"><div className="login-form-wrap"><div className="mobile-brand"><span className="brand-symbol"><HomeOutlined /></span><span className="brand-name">RS <span>Best Hostel</span></span></div><div className="eyebrow">Xush kelibsiz</div><h2>Hisobingizga kiring</h2><p className="muted">Ishni davom ettirish uchun ma’lumotlaringizni kiriting.</p>
      <form className="login-form" onSubmit={submit}><label htmlFor="email">{uz.login.email}</label><input id="email" name="email" type="email" autoComplete="username" required placeholder="operator@maskan.uz"/><label htmlFor="password">{uz.login.password}</label><input id="password" name="password" type="password" autoComplete="current-password" required minLength={1}/><Button type="primary" htmlType="submit" size="large" loading={busy} block>{uz.login.submit}<span aria-hidden="true"> →</span></Button></form>
      <div className="login-security"><span className="security-lock">⌑</span><span>Kirish ma’lumotlari tizim tomonidan himoyalangan.</span></div>
    </div></section>
  </main>;
}

function Shell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const screens = Grid.useBreakpoint();
  const compactDashboard = location.pathname === '/app' && Boolean(screens.sm);
  const mobile = !screens.md && !compactDashboard;
  const [drawer, setDrawer] = useState(false);
  const [alerts, setAlerts] = useState<AppNotification[]>([]);
  const [notice, contextHolder] = notification.useNotification();
  const current = routeTitles[location.pathname] || (location.pathname === '/settings/users' ? uz.nav.users : location.pathname === '/settings/audit' ? uz.nav.audit : uz.nav.dashboard);
  const initials = user?.full_name.split(/\s+/).slice(0, 2).map((item) => item[0]).join('').toLocaleUpperCase('uz-UZ') || 'RS';

  const loadAlerts = async () => {
    try { setAlerts((await api.get<AppNotification[]>('/notifications')).data); }
    catch (error) { notice.error({ message: 'Bildirishnomalarni yuklab bo‘lmadi', description: errorMessage(error) }); }
  };
  useEffect(() => { void loadAlerts(); }, []);

  const menuItems = useMemo(() => [
    { key: '/app', icon: <AppstoreOutlined />, label: uz.nav.dashboard },
    { key: '/residents', icon: <TeamOutlined />, label: uz.nav.residents },
    { key: '/rooms', icon: <HomeOutlined />, label: uz.nav.rooms },
    { key: '/admissions', icon: <SolutionOutlined />, label: uz.nav.admissions },
    { key: '/payments', icon: <WalletOutlined />, label: uz.nav.payments },
    { key: '/expenses', icon: <DollarCircleOutlined />, label: uz.nav.expenses },
    { key: '/reports', icon: <FileExcelOutlined />, label: uz.nav.reports },
    { key: '/guide', icon: <QuestionCircleOutlined />, label: 'Qo‘llanma' },
    { type: 'divider' as const },
    { key: '/settings', icon: <SettingOutlined />, label: uz.nav.settings },
    ...(user?.role === 'OPERATOR' ? [
      { key: '/settings/users', icon: <UserOutlined />, label: uz.nav.users },
      { key: '/settings/audit', icon: <AuditOutlined />, label: uz.nav.audit },
    ] : []),
  ], [user?.role]);

  const sidebar = <>
    <Link className="brand" to="/" onClick={() => setDrawer(false)}><span className="brand-symbol"><HomeOutlined /></span><span className="brand-name">RS <span>Best Hostel</span><small>{uz.brand.subtitle}</small></span></Link>
    <div className="side-section-label">ISH MAYDONI</div>
    <Menu theme="dark" mode="inline" selectedKeys={[location.pathname]} items={menuItems} onClick={({ key }) => { navigate(key); setDrawer(false); }} />
    <div className="sidebar-spacer"/>
    <div className="side-account"><Avatar size={34} className="account-avatar">{initials}</Avatar><div className="account-copy"><strong>{user?.full_name}</strong><small>{user ? uz.role[user.role as Role] : ''}</small></div><Button type="text" icon={<LogoutOutlined />} aria-label="Tizimdan chiqish" onClick={logout}/></div>
  </>;

  const notificationMenu = {
    items: alerts.length ? alerts.slice(0, 12).map((item) => ({ key: item.id, label: <div className="notification-item"><strong>{item.title}</strong><span>{item.message}</span><small>{formatDate(item.created_at.slice(0, 10), true)}</small></div> })) : [{ key: 'empty', disabled: true, label: 'Yangi bildirishnoma yo‘q' }],
    onClick: async () => { await api.post('/notifications/read-all'); await loadAlerts(); },
  };

  return <Layout className={`app-layout${location.pathname === '/app' ? ' dashboard-app' : ''}`}>
    {contextHolder}
    {!mobile && <Sider className="app-sider" width={248} theme="dark">{sidebar}</Sider>}
    <Layout className="inner-layout">
      <Header className="app-header">
        {mobile && <Button type="text" icon={<MenuOutlined />} aria-label="Menyuni ochish" onClick={() => setDrawer(true)}/>}
        <div className="breadcrumb"><span>Asosiy</span><b>/</b><strong>{current}</strong></div>
        <div className="header-actions"><Text className="header-date">{new Intl.DateTimeFormat('uz-UZ',{weekday:'short',day:'numeric',month:'short',timeZone:'Asia/Tashkent'}).format(new Date())}</Text>
          <Dropdown menu={notificationMenu} trigger={['click']} placement="bottomRight"><Button type="text" className="notification-trigger" aria-label="Bildirishnomalar"><Badge dot={alerts.length > 0}><BellOutlined/></Badge></Button></Dropdown>
          <span className="header-divider"/><Dropdown menu={{items:[{key:'profile',label:'Hisob ma’lumotlari',icon:<UserOutlined/>,onClick:()=>navigate('/settings')},{key:'logout',label:'Tizimdan chiqish',icon:<LogoutOutlined/>,onClick:logout}]}} trigger={['click']}><Button type="text" className="profile-trigger"><Avatar size={30}>{initials}</Avatar><span className="profile-name">{user?.full_name}</span></Button></Dropdown>
        </div>
      </Header>
      <Content className="app-content"><Outlet context={{ reloadAlerts: loadAlerts }} /></Content>
    </Layout>
    <Drawer open={drawer} onClose={() => setDrawer(false)} placement="left" width={270} className="mobile-nav-drawer" closable={false}>{sidebar}</Drawer>
  </Layout>;
}

function Protected() {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <div className="auth-loading"><Spin size="large"/></div>;
  return user ? <Shell/> : <Navigate to="/login" replace state={{ from: location }}/>;
}

function Home() {
  const { user, loading } = useAuth();
  if (loading) return <div className="auth-loading"><Spin size="large" /></div>;
  return user ? <Navigate to="/app" replace /> : <Landing />;
}

function OperatorOnly({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  if (user?.role !== 'OPERATOR') return <Navigate to="/settings" replace/>;
  return children;
}

export default function App() {
  return <Suspense fallback={<div className="auth-loading"><Spin size="large" /></div>}><Routes>
    <Route path="/" element={<Home/>}/>
    <Route path="/login" element={<Login/>}/>
    <Route path="/apply" element={<PublicApplication/>}/>
    <Route element={<Protected/>}>
      <Route path="/app" element={<Dashboard/>}/>
      <Route path="/residents" element={<Residents/>}/>
      <Route path="/rooms" element={<Rooms/>}/>
      <Route path="/admissions" element={<Admissions/>}/>
      <Route path="/guide" element={<AdminGuide/>}/>
      <Route path="/payments" element={<Payments/>}/>
      <Route path="/expenses" element={<Expenses/>}/>
      <Route path="/reports" element={<Reports/>}/>
      <Route path="/settings" element={<SettingsPage/>}/>
      <Route path="/settings/users" element={<OperatorOnly><SettingsPage initialTab="users"/></OperatorOnly>}/>
      <Route path="/settings/audit" element={<OperatorOnly><SettingsPage initialTab="audit"/></OperatorOnly>}/>
    </Route>
    <Route path="*" element={<Navigate to="/" replace/>}/>
  </Routes></Suspense>;
}
