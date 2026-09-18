/**
 * Aegis Task Full Workflow & Thinking Process Exporter
 * Generates structured, professional GitHub Flavored Markdown of the complete execution lifecycle.
 */

import type { Task, Workspace } from '@/types';

export function generateWorkflowMarkdown(
  task: Task | null | undefined,
  workspace?: Workspace | null
): string {
  if (!task) {
    return '# Aegis 任务报告 (无活动任务)\n\n当前未选择或无执行中的任务。';
  }

  const lines: string[] = [];

  // 1. Header & Metadata
  lines.push(`# Aegis 任务执行与思考全流程报告`);
  lines.push('');
  lines.push(`> 本报告由 Aegis 高可信代码智能体全自动因果追踪引擎生成，完整记录目标拆解、状态机流转、受限工具调用与底层 AI 模型交互细节。`);
  lines.push('');
  lines.push('### 基础元数据 (Metadata)');
  lines.push(`- **任务 ID**: \`${task.id}\``);
  if (task.session_id) {
    lines.push(`- **会话 ID**: \`${task.session_id}\``);
  }
  lines.push(`- **物理工作区**: \`${workspace?.name || '本地工作区'}\` (\`${workspace?.root_path || 'Ground Truth Root'}\`)`);
  lines.push(`- **任务目标**: ${task.prompt || task.title}`);
  lines.push(`- **执行状态**: \`${task.status}\``);
  lines.push(`- **权限级别**: \`${task.permissionLevel}\``);
  lines.push(`- **配置模型**: \`${task.model}\``);
  lines.push(`- **发起时间**: ${task.createdAt}`);
  lines.push(`- **最后更新**: ${task.updatedAt}`);
  lines.push('');

  // 2. Telemetry Metrics Summary
  if (task.telemetry) {
    const tel = task.telemetry;
    lines.push('### 资源消耗与遥测指标 (Telemetry)');
    lines.push('| 指标名称 | 当前数值 | 上限 / 说明 |');
    lines.push('| :--- | :--- | :--- |');
    lines.push(`| **物理累计消耗** | \`${(tel.totalTokens || 0).toLocaleString()} tokens\` | 预算上限 200,000 tokens |`);
    lines.push(`| **活跃上下文窗口** | \`${(tel.contextTokens || 0).toLocaleString()} tokens\` | 窗口上限 32,000 tokens |`);
    lines.push(`| **上下文水位** | \`${tel.waterLevelPct || 0}%\` | 高水位压缩阈值 80% |`);
    lines.push(`| **执行总轮次 / 步数** | \`轮次: ${tel.rounds || 1} / 步骤: ${tel.steps || 1}\` | LangGraph 跃迁计数 |`);
    lines.push('');
  }

  lines.push('---');
  lines.push('');

  // 3. Milestones & Planning (Planner)
  const allMilestones = task.messages.flatMap((m) => m.milestones || []).filter(
    (m, idx, arr) => arr.findIndex((t) => t.id === m.id) === idx
  );
  if (allMilestones.length > 0) {
    lines.push('## 一、目标拆解与里程碑规划 (Milestones & Plan)');
    allMilestones.forEach((m, idx) => {
      const isDone = m.status === 'completed';
      const isProgress = m.status === 'in_progress';
      const badge = isDone ? ' [已达成]' : isProgress ? ' [执行中]' : ' [待推进]';
      lines.push(`${idx + 1}. - [${isDone ? 'x' : ' '}] **${m.title}** \`${badge}\``);
    });
    lines.push('');
  }

  // 4. Trace Timeline (State Machine execution causal steps)
  if (task.traceSteps && task.traceSteps.length > 0) {
    lines.push('## 二、状态机流转与执行轨迹 (State Machine Trace)');
    lines.push('');
    task.traceSteps.forEach((step) => {
      lines.push(`### Step #${step.step}: ${step.node.toUpperCase()} (${step.timestamp})`);
      if (step.durationMs > 0 || step.tokenUsage) {
        lines.push(`- **耗时**: \`${step.durationMs}ms\` | **Token**: \`${(step.tokenUsage || 0).toLocaleString()} tok\``);
      }
      if (step.inputSummary) {
        lines.push(`- **入参意图 / 目标**: ${step.inputSummary}`);
      }
      if (step.tool) {
        lines.push(`- **调用工具**: \`${step.tool}\``);
        if (step.toolArgs) {
          lines.push('```json');
          lines.push(typeof step.toolArgs === 'object' ? JSON.stringify(step.toolArgs, null, 2) : String(step.toolArgs));
          lines.push('```');
        }
      }
      if (step.toolResult) {
        lines.push(`- **工具返回产物**:`);
        lines.push('```text');
        lines.push(step.toolResult);
        lines.push('```');
      }
      if (step.outputSummary) {
        lines.push(`- **决策结论 / 出参**: ${step.outputSummary}`);
      }
      lines.push('');
    });
  }

  // 5. LLM Calls (Detailed Prompt & Raw Response Transparency)
  if (task.llmCalls && task.llmCalls.length > 0) {
    lines.push('## 三、AI 底层大模型调用透视 (LLM Requests & Responses)');
    lines.push('');
    lines.push(`> 累计记录 **${task.llmCalls.length} 次** 底层模型交互，每次交互均呈现完整 Prompt 注入序列、工具 Schema 与原始应答。`);
    lines.push('');

    task.llmCalls.forEach((call, idx) => {
      lines.push(`### [LLM 调用 #${idx + 1}] Step #${call.step} : ${call.node.toUpperCase()}`);
      lines.push(`- **模型与层级**: \`${call.model}\` (\`Tier: ${call.tier}\`)`);
      lines.push(`- **物理耗时**: \`${call.durationMs || 0}ms\` | **Token 消耗**: \`${(call.tokens || 0).toLocaleString()}\` | **时戳**: \`${call.timestamp}\``);
      if (call.response?.finish_reason) {
        lines.push(`- **结束原因**: \`${call.response.finish_reason}\``);
      }
      lines.push('');

      // Messages breakdown
      if (call.messages && call.messages.length > 0) {
        lines.push(`#### Prompt 消息序列 (${call.messages.length} 条)`);
        call.messages.forEach((msg, mIdx) => {
          lines.push(`##### 消息 #${mIdx + 1} [Role: ${msg.role.toUpperCase()}]`);
          if (msg.content) {
            lines.push('```text');
            lines.push(msg.content);
            lines.push('```');
          } else if (msg.tool_calls) {
            lines.push('```json');
            lines.push(JSON.stringify(msg.tool_calls, null, 2));
            lines.push('```');
          }
        });
        lines.push('');
      }

      // Tools schema
      if (call.tools && call.tools.length > 0) {
        lines.push(`#### 挂载工具定义 (${call.tools.length} 个)`);
        lines.push('```json');
        lines.push(JSON.stringify(call.tools, null, 2));
        lines.push('```');
        lines.push('');
      }

      // Raw Output
      lines.push(`#### 模型原始返回`);
      if (call.response?.content) {
        lines.push('```text');
        lines.push(call.response.content);
        lines.push('```');
      }
      if (call.response?.tool_calls && call.response.tool_calls.length > 0) {
        lines.push('**生成的 Tool Calls**:');
        lines.push('```json');
        lines.push(JSON.stringify(call.response.tool_calls, null, 2));
        lines.push('```');
      }
      lines.push('');
    });
  }

  // 6. Dialogue History & Final Delivery
  if (task.messages && task.messages.length > 0) {
    lines.push('## 四、对话协商与最终交付内容 (Conversation & Final Delivery)');
    lines.push('');
    task.messages.forEach((msg) => {
      const roleLabel = msg.role === 'user' ? '👤 用户 (User)' : msg.role === 'assistant' ? '🤖 Aegis 智能体 (Assistant)' : '⚙️ 系统 (System)';
      lines.push(`### ${roleLabel} - ${msg.timestamp}`);
      lines.push('');
      lines.push(msg.content);
      lines.push('');

      if (msg.fileMutations && msg.fileMutations.length > 0) {
        lines.push('**文件变更列表**:');
        msg.fileMutations.forEach((fm) => {
          lines.push(`- \`${fm.action.toUpperCase()}\` : \`${fm.path}\` ${fm.summary ? `(${fm.summary})` : ''}`);
        });
        lines.push('');
      }
    });
  }

  return lines.join('\n');
}
