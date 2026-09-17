import React, { useState } from 'react';
import { Check, X, Shield } from 'lucide-react';
import type { HITLApprovalRequest } from '@/types';
import { Button } from '@/components/ui/Button';
import { CodeBlock } from '@/components/ui/CodeBlock';
import { Badge } from '@/components/ui/Badge';

interface HitlApprovalCardProps {
  approval: HITLApprovalRequest;
  onApprove: (approvalId: string, decision: 'once' | 'always', feedback?: string) => void;
  onReject: (approvalId: string, reason: string) => void;
}

export const HitlApprovalCard: React.FC<HitlApprovalCardProps> = ({
  approval,
  onApprove,
  onReject,
}) => {
  const [showRejectInput, setShowRejectInput] = useState(false);
  const [rejectReason, setRejectReason] = useState('');

  const handleConfirmReject = () => {
    onReject(approval.approval_id, rejectReason || '用户在交互审批卡片中拒绝执行该高危操作');
  };

  return (
    <div className="p-4 rounded-2xl border-2 border-amber-400 bg-amber-50/60 shadow-md space-y-3 animate-in fade-in zoom-in-95 duration-150 select-none">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-amber-900 font-bold text-xs">
          <Shield className="w-4 h-4 text-amber-600 shrink-0" />
          <span>人机协同权限越级审批卡片 (HITL Approval Required)</span>
        </div>
        <Badge variant="warning" size="xs" dot pulse>
          {approval.action_type}
        </Badge>
      </div>

      {/* Reason */}
      <div className="text-xs text-amber-900 leading-relaxed">
        检测到超出当前权限基线操作：<strong>{approval.reason}</strong>
      </div>

      {/* Command Display */}
      <CodeBlock
        code={approval.command}
        language="bash"
        title="待执行指令 (Raw Command)"
        className="border-amber-300"
      />

      {/* Actions */}
      {!showRejectInput ? (
        <div className="flex items-center gap-2 pt-1">
          <Button
            variant="primary"
            size="sm"
            onClick={() => onApprove(approval.approval_id, 'once')}
            leftIcon={<Check className="w-3.5 h-3.5" />}
            className="bg-emerald-600 hover:bg-emerald-700"
          >
            批准本次 (Once)
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => onApprove(approval.approval_id, 'always')}
            className="border-amber-300 text-amber-900 hover:bg-amber-100"
          >
            当前会话免审 (Always)
          </Button>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowRejectInput(true)}
            leftIcon={<X className="w-3.5 h-3.5" />}
            className="border-red-300 text-red-700 hover:bg-red-50 ml-auto"
          >
            拒绝并指示改道 (Reject)
          </Button>
        </div>
      ) : (
        <div className="space-y-2 pt-1 animate-in fade-in duration-100">
          <input
            type="text"
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value)}
            placeholder="输入拒绝原因与重规划指示（例如: 禁止推送到远端，仅在本地生成 patch 文件）..."
            className="w-full px-3 py-1.5 border border-red-300 rounded-lg text-xs bg-white focus:outline-hidden focus:ring-2 focus:ring-red-400"
          />
          <div className="flex justify-end gap-2">
            <Button variant="ghost" size="xs" onClick={() => setShowRejectInput(false)}>
              取消
            </Button>
            <Button variant="danger" size="xs" onClick={handleConfirmReject}>
              确认拒绝并通知 Planner
            </Button>
          </div>
        </div>
      )}
    </div>
  );
};
