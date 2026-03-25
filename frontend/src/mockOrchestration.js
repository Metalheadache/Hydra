// Mock orchestration event stream for demo/fallback mode
// Emits HydraEvent-shaped objects matching the real backend protocol

const MOCK_TASK_PLAN = {
  task_id: 'task_mock001',
  original_task: '',
  sub_tasks: [
    { id: 'st_001', description: 'Research the topic', estimated_tokens: 2000 },
    { id: 'st_002', description: 'Analyze findings', estimated_tokens: 1800 },
    { id: 'st_003', description: 'Compile report', estimated_tokens: 1500 },
  ],
  agent_specs: [
    { agent_id: 'agent_001', sub_task_id: 'st_001', role: 'Senior Research Analyst', tools_needed: ['web_search'] },
    { agent_id: 'agent_002', sub_task_id: 'st_002', role: 'Data Analyst', tools_needed: ['web_fetch'] },
    { agent_id: 'agent_003', sub_task_id: 'st_003', role: 'Report Writer', tools_needed: [] },
  ],
  execution_groups: [['st_001', 'st_002'], ['st_003']],
};

const delay = (ms) => new Promise(r => setTimeout(r, ms));

async function* genTokens(text, chunkMs = 40) {
  const words = text.split(/(\s+)/);
  for (const word of words) {
    await delay(chunkMs + Math.random() * 60);
    yield word;
  }
}

const SYNTHESIS_TEXT = `## Executive Summary

Based on comprehensive multi-agent analysis, I've identified the following key insights:

### Key Findings

1. **Primary Analysis**: The research phase revealed significant patterns across multiple data sources, indicating a clear trend toward distributed architectures.

2. **Secondary Research**: Cross-referencing multiple authoritative sources confirmed the initial hypothesis with high confidence.

3. **Synthesis**: The combined output from all agents provides a robust foundation for decision-making.

### Recommendations

- **Immediate actions**: Based on the research findings, prioritize the identified opportunities
- **Medium-term strategy**: Leverage the analytical insights to optimize resource allocation  
- **Long-term vision**: Position for emerging trends identified through deep research

### Conclusion

The multi-agent pipeline successfully decomposed the complex task into manageable sub-tasks, executing them in parallel groups for maximum efficiency. Total execution time was within expected parameters.`;

export async function* mockOrchestration(taskText) {
  const plan = { ...MOCK_TASK_PLAN, original_task: taskText };

  // Pipeline start
  yield { type: 'pipeline_start', timestamp: Date.now() / 1000, data: { task: taskText } };
  await delay(300);

  // Brain start
  yield { type: 'brain_start', timestamp: Date.now() / 1000, data: { task: taskText } };
  await delay(1200);

  // Brain complete
  yield {
    type: 'brain_complete',
    timestamp: Date.now() / 1000,
    data: plan,
  };
  await delay(400);

  // Group 0 — parallel: agents 001, 002
  yield {
    type: 'group_start',
    timestamp: Date.now() / 1000,
    group_index: 0,
    data: { group_index: 0, sub_task_ids: ['st_001', 'st_002'], parallel: true },
  };

  // Agent 001 start
  yield {
    type: 'agent_start',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_001',
    sub_task_id: 'st_001',
    data: {
      agent_id: 'agent_001',
      role: 'Senior Research Analyst',
      sub_task: { id: 'st_001', description: 'Research the topic', estimated_tokens: 2000 },
    },
  };

  // Agent 002 start
  yield {
    type: 'agent_start',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_002',
    sub_task_id: 'st_002',
    data: {
      agent_id: 'agent_002',
      role: 'Data Analyst',
      sub_task: { id: 'st_002', description: 'Analyze findings', estimated_tokens: 1800 },
    },
  };

  await delay(600);

  // Agent 001 tool call
  yield {
    type: 'agent_tool_call',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_001',
    data: { tool_name: 'web_search', args: { query: taskText.slice(0, 60) } },
  };

  await delay(500);

  // Stream tokens for agent 001
  const a1text = 'Conducting comprehensive research on the requested topic. Found multiple authoritative sources with relevant information. Cross-referencing data points for accuracy.';
  for (const chunk of a1text.split(' ')) {
    await delay(30 + Math.random() * 40);
    yield {
      type: 'agent_token',
      timestamp: Date.now() / 1000,
      agent_id: 'agent_001',
      tokens: 1,
      data: { token: chunk + ' ' },
    };
  }

  // Agent 002 tool call
  yield {
    type: 'agent_tool_call',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_002',
    data: { tool_name: 'web_fetch', args: { url: 'https://example.com/data' } },
  };

  await delay(400);

  // Stream tokens for agent 002
  const a2text = 'Analyzing the collected data using statistical methods. Identifying key trends and patterns. Building comprehensive data model.';
  for (const chunk of a2text.split(' ')) {
    await delay(35 + Math.random() * 40);
    yield {
      type: 'agent_token',
      timestamp: Date.now() / 1000,
      agent_id: 'agent_002',
      tokens: 1,
      data: { token: chunk + ' ' },
    };
  }

  await delay(300);

  // Agent 001 complete
  yield {
    type: 'agent_complete',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_001',
    sub_task_id: 'st_001',
    tokens: 1240,
    data: {
      agent_id: 'agent_001',
      status: 'completed',
      output: 'Research complete: Found comprehensive data across 8 sources with strong relevance.',
      tokens_used: 1240,
      execution_time_ms: 3200,
    },
  };

  await delay(200);

  // Agent 002 complete
  yield {
    type: 'agent_complete',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_002',
    sub_task_id: 'st_002',
    tokens: 980,
    data: {
      agent_id: 'agent_002',
      status: 'completed',
      output: 'Analysis complete: Identified 3 major trends with 87% confidence interval.',
      tokens_used: 980,
      execution_time_ms: 2800,
    },
  };

  // Group 0 complete
  yield {
    type: 'group_complete',
    timestamp: Date.now() / 1000,
    group_index: 0,
    data: { group_index: 0 },
  };

  await delay(300);

  // Group 1 — sequential: agent 003
  yield {
    type: 'group_start',
    timestamp: Date.now() / 1000,
    group_index: 1,
    data: { group_index: 1, sub_task_ids: ['st_003'], parallel: false },
  };

  yield {
    type: 'agent_start',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_003',
    sub_task_id: 'st_003',
    data: {
      agent_id: 'agent_003',
      role: 'Report Writer',
      sub_task: { id: 'st_003', description: 'Compile report', estimated_tokens: 1500 },
    },
  };

  await delay(500);

  const a3text = 'Synthesizing research and analysis into coherent report structure. Organizing findings by priority. Adding executive summary and recommendations.';
  for (const chunk of a3text.split(' ')) {
    await delay(30 + Math.random() * 45);
    yield {
      type: 'agent_token',
      timestamp: Date.now() / 1000,
      agent_id: 'agent_003',
      tokens: 1,
      data: { token: chunk + ' ' },
    };
  }

  await delay(300);

  yield {
    type: 'agent_complete',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_003',
    sub_task_id: 'st_003',
    tokens: 890,
    data: {
      agent_id: 'agent_003',
      status: 'completed',
      output: 'Report compiled: Comprehensive document with executive summary, findings, and actionable recommendations.',
      tokens_used: 890,
      execution_time_ms: 2100,
    },
  };

  yield {
    type: 'group_complete',
    timestamp: Date.now() / 1000,
    group_index: 1,
    data: { group_index: 1 },
  };

  await delay(400);

  // Quality scoring
  yield {
    type: 'quality_start',
    timestamp: Date.now() / 1000,
    data: { agents: ['agent_001', 'agent_002', 'agent_003'] },
  };

  await delay(600);

  yield {
    type: 'quality_score',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_001',
    data: {
      agent_id: 'agent_001',
      score: 8.5,
      feedback: 'Excellent research coverage with reliable sources. Well-structured findings.',
    },
  };

  await delay(300);

  yield {
    type: 'quality_score',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_002',
    data: {
      agent_id: 'agent_002',
      score: 9.0,
      feedback: 'Strong analytical framework. Clear data interpretation with actionable insights.',
    },
  };

  await delay(300);

  yield {
    type: 'quality_score',
    timestamp: Date.now() / 1000,
    agent_id: 'agent_003',
    data: {
      agent_id: 'agent_003',
      score: 8.0,
      feedback: 'Well-written report with coherent narrative. Recommendations are practical.',
    },
  };

  await delay(400);

  // Synthesis
  yield {
    type: 'synthesis_start',
    timestamp: Date.now() / 1000,
    data: {},
  };

  await delay(300);

  let synthTokens = 0;
  for await (const chunk of genTokens(SYNTHESIS_TEXT)) {
    synthTokens++;
    yield {
      type: 'synthesis_token',
      timestamp: Date.now() / 1000,
      tokens: 1,
      data: { token: chunk },
    };
  }

  await delay(200);

  yield {
    type: 'synthesis_complete',
    timestamp: Date.now() / 1000,
    data: { output: SYNTHESIS_TEXT },
  };

  await delay(300);

  // Pipeline complete
  const totalTokens = 1240 + 980 + 890 + synthTokens;
  yield {
    type: 'pipeline_complete',
    timestamp: Date.now() / 1000,
    data: {
      task_id: plan.task_id,
      synthesis: SYNTHESIS_TEXT,
      per_agent_quality: {
        agent_001: { score: 8.5, feedback: 'Excellent research coverage.', output: 'Research complete: Found comprehensive data across 8 sources.' },
        agent_002: { score: 9.0, feedback: 'Strong analytical framework.', output: 'Analysis complete: Identified 3 major trends.' },
        agent_003: { score: 8.0, feedback: 'Well-written report.', output: 'Report compiled with executive summary and recommendations.' },
      },
      files_generated: [],
      execution_summary: {
        total_tokens: totalTokens,
        total_cost: (totalTokens / 1000000) * 3,
        total_time_ms: 12000,
        agent_count: 3,
        group_count: 2,
      },
    },
  };
}
