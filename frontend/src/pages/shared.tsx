import type { ReactNode } from 'react';
import { Button, Space, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';

const { Title, Text } = Typography;

export function PageHeading({ eyebrow, title, subtitle, action, onAction }: { eyebrow: string; title: string; subtitle?: string; action?: string; onAction?: () => void }) {
  return <div className="page-heading"><div><div className="eyebrow">{eyebrow}</div><Title level={2}>{title}</Title>{subtitle && <Text type="secondary">{subtitle}</Text>}</div>{action && <Button type="primary" icon={<PlusOutlined />} onClick={onAction}>{action}</Button>}</div>;
}

export function Panel({ title, extra, children, className = '' }: { title: string; extra?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}><div className="panel-heading"><strong>{title}</strong>{extra}</div>{children}</section>;
}

export function EmptyBlock({ title, detail }: { title: string; detail?: string }) {
  return <div className="empty-block"><span>⌂</span><strong>{title}</strong>{detail && <small>{detail}</small>}</div>;
}

export function Actions({ children }: { children: ReactNode }) { return <Space size={4}>{children}</Space>; }
