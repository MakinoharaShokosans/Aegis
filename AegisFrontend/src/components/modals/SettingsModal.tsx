import React, { useState } from 'react';
import {
  X,
  Settings,
  Shield,
  Server,
  Cpu,
  Radio,
} from 'lucide-react';
import { useUiStore } from '@/stores/useUiStore';
import { httpClient, systemApi } from '@/api';
import type { McpServerInfo } from '@/types';

export const SettingsModal: React.FC = () => {
  const { settingsModalOpen, setSettingsModalOpen } = useUiStore();

  const [activeTab, setActiveTab] = useState<'security' | 'gateway' | 'sidecars' | 'mcp'>('security');

  // Security Gate form state
  const [allowedHosts, setAllowedHosts] = useState('127.0.0.1, localhost, ::1');
  const [corsOrigins, setCorsOrigins] = useState('http://localhost:5173, http://127.0.0.1:5173');

  // Dual-Tier Gateway state
  const [reasoningModel, setReasoningModel] = useState('gpt-5.6-terra');
  const [reasoningBaseUrl, setReasoningBaseUrl] = useState('https://api.openlux.ai/v1');
  const [fastModel, setFastModel] = useState('gpt-5.6-luna');
  const [fastBaseUrl, setFastBaseUrl] = useState('https://api.openlux.ai/v1');

  // Sidecar state
  const [ragPort, setRagPort] = useState('8001');
  const [shellPort, setShellPort] = useState('8002');
  const [webPort, setWebPort] = useState('8003');
  const [memoryPoolMb, setMemoryPoolMb] = useState('512');
  const [mcpServers, setMcpServers] = useState<McpServerInfo[]>([]);

  React.useEffect(() => {
    if (settingsModalOpen) {
      systemApi.getModels().then((data) => {
        if (!data) return;
        const rEndpoint = data.reasoning?.endpoints?.[0];
        if (rEndpoint) {
          setReasoningModel(rEndpoint.model || rEndpoint.name);
          setReasoningBaseUrl(rEndpoint.base_url);
        }
        const fEndpoints = data.fast?.endpoints || [];
        if (fEndpoints.length > 0) {
          setFastModel(fEndpoints.map((e) => e.model || e.name).join(' / '));
          setFastBaseUrl(fEndpoints[0].base_url);
        }
      }).catch(() => {
        // ignore
      });

      systemApi.getMcps().then((data) => {
        if (Array.isArray(data)) {
          setMcpServers(data);
        }
      }).catch(() => {
        // ignore
      });
    }
  }, [settingsModalOpen]);

  if (!settingsModalOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-xs p-4 animate-in fade-in duration-150">
      <div className="bg-white rounded-xl shadow-2xl border border-border-subtle w-full max-w-3xl max-h-[90vh] flex flex-col overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border-subtle bg-canvas-secondary">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-gray-200 text-gray-800">
              <Settings className="w-5 h-5" />
            </div>
            <div>
              <h2 className="font-bold text-gray-900 text-base">系统设置与接入层治理 (System Configuration)</h2>
              <p className="text-xs text-gray-500">
                接入层三道安全闸门、双模型分层网关与 Sidecar 微服务沙箱参数
              </p>
            </div>
          </div>
          <button
            onClick={() => setSettingsModalOpen(false)}
            className="p-1 rounded-md text-gray-400 hover:text-gray-700 hover:bg-gray-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-4 px-6 border-b border-border-subtle bg-white text-xs font-medium">
          <button
            onClick={() => setActiveTab('security')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'security'
                ? 'border-brand-600 text-brand-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Shield className="w-3.5 h-3.5" />
            <span>三道安全闸门</span>
          </button>
          <button
            onClick={() => setActiveTab('gateway')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'gateway'
                ? 'border-brand-600 text-brand-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Cpu className="w-3.5 h-3.5" />
            <span>双模型分层网关</span>
          </button>
          <button
            onClick={() => setActiveTab('sidecars')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'sidecars'
                ? 'border-brand-600 text-brand-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Server className="w-3.5 h-3.5" />
            <span>Sidecar 微服务沙箱</span>
          </button>
          <button
            onClick={() => setActiveTab('mcp')}
            className={`py-2.5 border-b-2 transition flex items-center gap-1.5 ${
              activeTab === 'mcp'
                ? 'border-brand-600 text-brand-700 font-semibold'
                : 'border-transparent text-gray-500 hover:text-gray-900'
            }`}
          >
            <Radio className="w-3.5 h-3.5" />
            <span>MCP 服务器治理</span>
          </button>
        </div>

        {/* Tab Contents */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5 text-xs">
          {activeTab === 'security' && (
            <div className="space-y-4">

              {/* Host & Origin Gates */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="font-semibold text-gray-900">1. Host 闸门 (DNS Rebinding Guard)</div>
                  <label className="text-gray-500 text-[11px] block">安全主机名白名单 (逗号分隔)</label>
                  <input
                    type="text"
                    value={allowedHosts}
                    onChange={(e) => setAllowedHosts(e.target.value)}
                    className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono text-xs bg-white"
                  />
                </div>

                <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="font-semibold text-gray-900">2. Origin 闸门 (CORS / CSRF Guard)</div>
                  <label className="text-gray-500 text-[11px] block">允许跨域源白名单 (逗号分隔)</label>
                  <input
                    type="text"
                    value={corsOrigins}
                    onChange={(e) => setCorsOrigins(e.target.value)}
                    className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono text-xs bg-white"
                  />
                </div>
              </div>
            </div>
          )}

          {activeTab === 'gateway' && (
            <div className="space-y-4">
              {/* Reasoning Tier */}
              <div className="p-4 rounded-xl border border-border-subtle bg-purple-50/30 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-purple-600" />
                    <span>思考模型层 (Reasoning Tier)</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-purple-100 text-purple-800 text-[10px] font-mono">
                    temperature = 0.0
                  </span>
                </div>
                <p className="text-[11px] text-gray-500">
                  负责宏观规划（Planner）、里程碑拆解、反思总结与最终交付报告编写。
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-gray-600 block mb-1">模型标识</label>
                    <input
                      type="text"
                      value={reasoningModel}
                      onChange={(e) => setReasoningModel(e.target.value)}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                  <div>
                    <label className="text-gray-600 block mb-1">Base URL</label>
                    <input
                      type="text"
                      value={reasoningBaseUrl}
                      onChange={(e) => setReasoningBaseUrl(e.target.value)}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                </div>
              </div>

              {/* Fast Tier */}
              <div className="p-4 rounded-xl border border-border-subtle bg-blue-50/30 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="font-semibold text-gray-900 flex items-center gap-1.5">
                    <Cpu className="w-4 h-4 text-blue-600" />
                    <span>快速动作层 (Fast Tier)</span>
                  </div>
                  <span className="px-2 py-0.5 rounded bg-blue-100 text-blue-800 text-[10px] font-mono">
                    temperature = 0.2
                  </span>
                </div>
                <p className="text-[11px] text-gray-500">
                  负责工具参数提取、代码生成、事实切片提炼与高吞吐并行派发。
                </p>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-gray-600 block mb-1">模型标识</label>
                    <input
                      type="text"
                      value={fastModel}
                      onChange={(e) => setFastModel(e.target.value)}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                  <div>
                    <label className="text-gray-600 block mb-1">Base URL</label>
                    <input
                      type="text"
                      value={fastBaseUrl}
                      onChange={(e) => setFastBaseUrl(e.target.value)}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'sidecars' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <div className="p-3.5 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between font-semibold text-gray-900">
                    <span>AegisRAG</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  </div>
                  <label className="text-gray-500 text-[10px] block">端口与协议</label>
                  <input
                    type="text"
                    value={`http://127.0.0.1:${ragPort}`}
                    onChange={(e) => setRagPort(e.target.value.split(':').pop() || '8001')}
                    className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg font-mono bg-white text-xs"
                  />
                </div>

                <div className="p-3.5 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between font-semibold text-gray-900">
                    <span>bash_shell 沙箱</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  </div>
                  <label className="text-gray-500 text-[10px] block">端口与协议</label>
                  <input
                    type="text"
                    value={`http://127.0.0.1:${shellPort}`}
                    onChange={(e) => setShellPort(e.target.value.split(':').pop() || '8002')}
                    className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg font-mono bg-white text-xs"
                  />
                </div>

                <div className="p-3.5 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                  <div className="flex items-center justify-between font-semibold text-gray-900">
                    <span>web_search 隔离</span>
                    <span className="w-2 h-2 rounded-full bg-emerald-500" />
                  </div>
                  <label className="text-gray-500 text-[10px] block">端口与协议</label>
                  <input
                    type="text"
                    value={`http://127.0.0.1:${webPort}`}
                    onChange={(e) => setWebPort(e.target.value.split(':').pop() || '8003')}
                    className="w-full px-2.5 py-1.5 border border-border-subtle rounded-lg font-mono bg-white text-xs"
                  />
                </div>
              </div>

              <div className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 space-y-2">
                <div className="font-semibold text-gray-900">沙箱内存配额与超时</div>
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <label className="text-gray-500 text-[11px] block mb-1">全局内存池上限 (MB)</label>
                    <input
                      type="number"
                      value={memoryPoolMb}
                      onChange={(e) => setMemoryPoolMb(e.target.value)}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                  <div className="flex-1">
                    <label className="text-gray-500 text-[11px] block mb-1">单命令超时时长 (秒)</label>
                    <input
                      type="number"
                      defaultValue={30}
                      className="w-full px-3 py-2 border border-border-subtle rounded-lg font-mono bg-white"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'mcp' && (
            <div className="space-y-3">
              {mcpServers.length > 0 ? (
                mcpServers.map((srv) => (
                  <div
                    key={srv.name}
                    className="p-4 rounded-xl border border-border-subtle bg-gray-50/50 flex items-center justify-between"
                  >
                    <div>
                      <div className="font-semibold text-gray-900 flex items-center gap-2">
                        <span className="font-mono">{srv.name}</span>
                        <span
                          className={`px-2 py-0.5 rounded text-[10px] font-mono font-medium ${
                            !srv.enabled
                              ? 'bg-slate-100 text-slate-600'
                              : srv.connected
                              ? 'bg-emerald-100 text-emerald-800'
                              : srv.error
                              ? 'bg-rose-100 text-rose-800'
                              : 'bg-blue-100 text-blue-800'
                          }`}
                        >
                          {!srv.enabled
                            ? '未启用 (Disabled)'
                            : srv.connected
                            ? '已连接 (Active)'
                            : srv.error
                            ? '连接失败 (Error)'
                            : '已配置待连接 (Lazy)'}
                        </span>
                        <span className="px-1.5 py-0.2 bg-slate-200/70 text-slate-600 rounded text-[10px] font-mono">
                          {srv.transport || 'stdio'}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-500 mt-1">
                        {!srv.enabled
                          ? '在 config/config.toml 中处于 disabled 状态（出于安全隔离，默认不拉起外部子进程）'
                          : srv.connected
                          ? `已通过 Aegis MCP 治理管理器纳管，成功挂载 ${srv.tool_count} 个外部工具`
                          : srv.error
                          ? `连接失败: ${srv.error}`
                          : '已声明并在需要工具时通过 Lazy 模式即时建立连接'}
                      </p>
                    </div>

                    <div className="text-right shrink-0 ml-4">
                      {!srv.enabled ? (
                        <span className="text-slate-400 font-mono text-[11px]">未激活 ○</span>
                      ) : srv.connected ? (
                        <span className="text-emerald-600 font-mono text-[11px] font-medium">已挂载 ({srv.tool_count}) ●</span>
                      ) : srv.error ? (
                        <span className="text-rose-600 font-mono text-[11px]">异常 ○</span>
                      ) : (
                        <span className="text-blue-600 font-mono text-[11px]">待唤醒 ○</span>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center rounded-xl border border-dashed border-slate-200 bg-slate-50/50 space-y-2">
                  <div className="text-slate-600 font-semibold text-xs">暂无已配置的 MCP 服务器</div>
                  <p className="text-[11px] text-slate-400 max-w-md mx-auto leading-relaxed">
                    当前环境未在 <code className="font-mono px-1 py-0.5 bg-slate-100 rounded text-slate-700">config/config.toml</code> 中启用外部 MCP 服务器。如需接入，请在配置文件的 <code className="font-mono text-slate-700">[mcp.servers.*]</code> 节点下设置 <code className="font-mono text-slate-700">enabled = true</code>。
                  </p>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-6 py-3 border-t border-border-subtle bg-gray-50">
          <button
            onClick={() => {
              httpClient.setToken(tokenVal);
              setSettingsModalOpen(false);
            }}
            className="px-4 py-2 rounded-lg bg-brand-600 hover:bg-brand-700 text-white font-medium transition"
          >
            保存并关闭
          </button>
        </div>
      </div>
    </div>
  );
};
