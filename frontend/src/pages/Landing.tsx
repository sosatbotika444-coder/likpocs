import {
  AppstoreOutlined,
  BellOutlined,
  CheckCircleFilled,
  HomeOutlined,
  RightOutlined,
  SearchOutlined,
  TeamOutlined,
  WalletOutlined,
} from '@ant-design/icons';
import { Link } from 'react-router-dom';

const previewItems = [
  { icon: <AppstoreOutlined />, label: 'Boshqaruv', active: true },
  { icon: <TeamOutlined />, label: 'Yashovchilar' },
  { icon: <HomeOutlined />, label: 'Xonalar' },
  { icon: <WalletOutlined />, label: 'To‘lovlar' },
];

function DashboardPreview() {
  return (
    <div className="landing-preview-wrap" id="dashboard-preview" aria-label="DormFlow boshqaruv panelining namuna ko‘rinishi">
      <div className="landing-preview">
        <header className="preview-topbar">
          <div className="preview-brand"><span><HomeOutlined /></span><strong>dorm<span>flow</span></strong></div>
          <div className="preview-search"><SearchOutlined /><span>Qidirish</span><kbd>⌘ K</kbd></div>
          <div className="preview-top-actions"><span className="preview-demo-label">DEMO KO‘RINISH</span><BellOutlined /><span className="preview-avatar">DF</span></div>
        </header>
        <div className="preview-layout">
          <aside className="preview-sidebar" aria-hidden="true">
            <small>ISH MAYDONI</small>
            {previewItems.map((item) => (
              <div className={`preview-nav-item${item.active ? ' is-active' : ''}`} key={item.label}>
                {item.icon}<span>{item.label}</span>
              </div>
            ))}
            <div className="preview-nav-item"><span className="preview-nav-spacer" />Hisobotlar</div>
          </aside>
          <div className="preview-main">
            <div className="preview-heading">
              <div><span>BUGUNGI HOLAT</span><h2>Boshqaruv paneli</h2></div>
              <span className="preview-date">Bugun · Toshkent</span>
            </div>
            <div className="preview-metrics">
              <div><span>Yashovchilar</span><strong>86</strong><small>Faol yashovchilar</small></div>
              <div><span>Xonalar</span><strong>24</strong><small>Boshqaruvda</small></div>
              <div><span>Xonalar bandligi</span><strong>82%</strong><small>14 ta bo‘sh o‘rin</small></div>
              <div><span>To‘lov muddati o‘tgan</span><strong>3</strong><small>1 tasi bugun</small></div>
            </div>
            <div className="preview-panels">
              <section className="preview-card preview-chart-card">
                <div className="preview-card-heading"><strong>Yashovchilar bandligi</strong><span>Oxirgi 6 oy <RightOutlined /></span></div>
                <div className="preview-chart-legend"><i /> Band o‘rinlar <i className="legend-pale" /> Bo‘sh o‘rinlar</div>
                <svg className="preview-chart" viewBox="0 0 520 104" preserveAspectRatio="none" role="img" aria-label="Bandlik grafigi">
                  <defs><linearGradient id="preview-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="hsl(var(--accent))" stopOpacity=".18"/><stop offset="100%" stopColor="hsl(var(--accent))" stopOpacity="0"/></linearGradient></defs>
                  <path d="M0 84 C35 81 45 72 78 74 S129 70 156 59 S208 67 234 51 S285 56 312 44 S364 49 390 34 S442 41 468 24 S501 23 520 16 L520 104 L0 104 Z" fill="url(#preview-fill)" />
                  <path d="M0 84 C35 81 45 72 78 74 S129 70 156 59 S208 67 234 51 S285 56 312 44 S364 49 390 34 S442 41 468 24 S501 23 520 16" fill="none" stroke="hsl(var(--accent))" strokeWidth="2.4" vectorEffect="non-scaling-stroke" />
                </svg>
                <div className="preview-chart-labels"><span>May</span><span>Iyun</span><span>Iyul</span><span>Avg</span><span>Sen</span><span>Okt</span></div>
              </section>
              <section className="preview-card preview-activity-card">
                <div className="preview-card-heading"><strong>So‘nggi to‘lovlar</strong><span>Barchasi <RightOutlined /></span></div>
                <div className="preview-payment"><span className="preview-person">BI</span><span><strong>Bekzod Ismoilov</strong><small>Bugun · Naqd pul</small></span><span className="preview-amount">1 200 000 <CheckCircleFilled /></span></div>
                <div className="preview-payment"><span className="preview-person person-alt">DK</span><span><strong>Madina Karimova</strong><small>Kecha · Bank o‘tkazmasi</small></span><span className="preview-amount">950 000 <CheckCircleFilled /></span></div>
                <div className="preview-payment"><span className="preview-person person-sand">JA</span><span><strong>Jasur Abdullayev</strong><small>Kecha · Click</small></span><span className="preview-amount">1 500 000 <CheckCircleFilled /></span></div>
              </section>
            </div>
          </div>
        </div>
      </div>
      <div className="preview-footnote"><span /> Namuna ma’lumotlar · haqiqiy raqamlar tizimga kirgandan keyin ko‘rinadi</div>
    </div>
  );
}

export default function Landing() {
  return (
    <main className="landing-page">
      <video className="landing-video" autoPlay muted loop playsInline aria-hidden="true" tabIndex={-1}>
        <source src="https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260319_015952_e1deeb12-8fb7-4071-a42a-60779fc64ab6.mp4" type="video/mp4" />
      </video>
      <div className="landing-wash" />
      <nav className="landing-nav" aria-label="Asosiy navigatsiya">
        <Link className="landing-brand" to="/" aria-label="DormFlow bosh sahifa"><span className="landing-brand-symbol"><HomeOutlined /></span><span>dorm<span>flow</span></span></Link>
        <div className="landing-nav-links">
          <Link to="/app">Boshqaruv</Link>
          <Link to="/rooms">Xonalar</Link>
          <Link to="/payments">To‘lovlar</Link>
          <Link to="/reports">Hisobotlar</Link>
        </div>
        <Link className="landing-nav-cta" to="/login">Tizimga kirish <span aria-hidden="true">↗</span></Link>
      </nav>
      <div className="landing-content">
        <div className="landing-badge landing-rise landing-delay-1"><span className="landing-badge-dot" /> Yotoqxona boshqaruvi · yagona tizim</div>
        <h1 className="landing-title landing-rise landing-delay-2">Yotoqxona boshqaruvi<br />endi <em>osonroq.</em></h1>
        <p className="landing-subtitle landing-rise landing-delay-3">Yashovchilar, xonalar va to‘lovlarni bir joyda boshqaring.<br className="desktop-break" /> Kundalik ishlar tartibli, hisob-kitoblar esa doimo aniq bo‘lsin.</p>
        <div className="landing-actions landing-rise landing-delay-4">
          <Link className="landing-primary" to="/login">Hisobga kirish <span aria-hidden="true">→</span></Link>
          <a className="landing-secondary" href="#dashboard-preview"><span className="landing-play" aria-hidden="true">▶</span> Tizimni ko‘rish</a>
        </div>
        <DashboardPreview />
      </div>
    </main>
  );
}
