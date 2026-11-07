import ContractView from './ContractView';
import type { StaffContract } from '../types';
import { uz } from '../locales/uz';

const formatSignedAt = (value: string | null) => value ? new Intl.DateTimeFormat('uz-UZ', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Tashkent' }).format(new Date(value)) : '—';

export default function SignedContractDocument({ contract }: { contract: StaffContract }) {
  return <article className="signed-contract-document" role="document">
    <div className="contract-print-header"><h2>{contract.title}</h2><p>{contract.number} · {contract.date} · {contract.city}</p></div>
    <div className="contract-print-body"><ContractView contract={contract} /></div>
    <section className="contract-verification">
      <h3>{uz.contract.verificationTitle}</h3>
      <dl>
        <dt>{uz.contract.signedBy}</dt><dd>{contract.signature_name || uz.contract.unsigned}</dd>
        <dt>{uz.contract.signedAt}</dt><dd>{formatSignedAt(contract.signed_at)}</dd>
        <dt>{uz.contract.channel}</dt><dd>{contract.signed_via === 'TELEGRAM' ? uz.contract.telegram : contract.signed_via ? uz.contract.web : '—'}</dd>
        <dt>{uz.contract.version}</dt><dd>{contract.signed_version || '—'}</dd>
        <dt>{uz.contract.hash}</dt><dd>{contract.hash}</dd>
        <dt>{uz.contract.hashCheck}</dt><dd>{contract.signed_hash_matches ? uz.contract.hashValid : uz.contract.changed}</dd>
        <dt>{uz.contract.operatorName}</dt><dd>{contract.operator_signature_name || uz.contract.operatorMissing}</dd>
        <dt>{uz.contract.operatorSignedAt}</dt><dd>{formatSignedAt(contract.operator_signed_at)}</dd>
      </dl>
    </section>
    <section className="contract-signature-slots">
      <div><strong>{uz.contract.tenantSlot}</strong><p>{contract.signature_name || '________________________'}</p><small>{uz.contract.signatureSpace}</small></div>
      <div><strong>{uz.contract.operatorSlot}</strong><p>{contract.operator_signature_name || '________________________'}</p><small>{uz.contract.signatureSpace} · {uz.contract.stampSpace}</small></div>
    </section>
  </article>;
}
