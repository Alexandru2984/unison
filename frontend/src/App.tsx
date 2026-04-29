import { useState, useEffect, useCallback } from 'react';
import ReactFlow, { 
  MiniMap, 
  Controls, 
  Background, 
  useNodesState, 
  useEdgesState,
  Panel
} from 'reactflow';
import dagre from 'dagre';
import 'reactflow/dist/style.css';
import axios from 'axios';

const API_URL = "/api";
const WS_URL = (window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + "/ws";

const dagreGraph = new dagre.graphlib.Graph();
dagreGraph.setDefaultEdgeLabel(() => ({}));

const nodeWidth = 250;
const nodeHeight = 80;

const getLayoutedElements = (nodes: any[], edges: any[], direction = 'TB') => {
  const isHorizontal = direction === 'LR';
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  nodes.forEach((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    node.targetPosition = isHorizontal ? 'left' : 'top';
    node.sourcePosition = isHorizontal ? 'right' : 'bottom';

    // We are shifting the dagre node position (which is centered) to top left
    node.position = {
      x: nodeWithPosition.x - nodeWidth / 2,
      y: nodeWithPosition.y - nodeHeight / 2,
    };

    return node;
  });

  return { nodes, edges };
};

interface Idea {
  id: number;
  parent_id: number | null;
  content: string;
  mutation: string;
}

const App = () => {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);
  const [input, setInput] = useState('');
  const [selectedParent, setSelectedParent] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const fetchIdeas = useCallback(async () => {
    try {
      const res = await axios.get<Idea[]>(`${API_URL}/idea`);
      const rawNodes = res.data.map((idea) => ({
        id: idea.id.toString(),
        data: { 
          label: (
            <div className="node-content">
              {idea.mutation !== 'base' && <div className="mutation-tag">{idea.mutation}</div>}
              <div className="text">{idea.content}</div>
            </div>
          ) 
        },
        style: { 
          background: selectedParent === idea.id ? '#4a148c' : '#2d2d2d',
          color: '#fff',
          borderRadius: '8px',
          border: selectedParent === idea.id ? '2px solid #e0e0e0' : '1px solid #444',
          width: nodeWidth,
        }
      }));

      const rawEdges = res.data
        .filter(i => i.parent_id !== null)
        .map(i => ({
          id: `e${i.parent_id}-${i.id}`,
          source: i.parent_id!.toString(),
          target: i.id.toString(),
          animated: true,
          style: { stroke: '#7b1fa2', strokeWidth: 2 }
        }));

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(rawNodes, rawEdges);
      setNodes([...layoutedNodes]);
      setEdges([...layoutedEdges]);
    } catch (e) {
      console.error("Failed to fetch ideas", e);
    }
  }, [selectedParent, setNodes, setEdges]);

  useEffect(() => {
    fetchIdeas();
    const ws = new WebSocket(WS_URL);
    ws.onmessage = () => fetchIdeas();
    return () => ws.close();
  }, [fetchIdeas]);

  const submitIdea = async (mutation: string = 'base') => {
    if (!input && mutation === 'base') return;
    setLoading(true);
    try {
      const parentNode = nodes.find((n: any) => n.id === selectedParent?.toString());
      
      if (mutation !== 'base' && parentNode) {
          // Extract text from the complex label if necessary, but backend knows the parent content from DB if we send parent_id
          // Actually, let's just send the parent_id and the backend can fetch the content from DB
          // Wait, my backend currently expects content in the request. Let's fix that.
      }

      await axios.post(`${API_URL}/idea`, {
        content: mutation === 'base' ? input : "", // backend will handle content if parent_id is present
        parent_id: selectedParent,
        mutation
      });
      setInput('');
      if (mutation === 'base') setSelectedParent(null);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="app-header">
        <div className="header-left">
          <h1>Idea<span>Evolution</span></h1>
          <p>Deterministic Mutation Engine Powered by <strong>Unison</strong></p>
        </div>
        <div className="header-right">
          <input 
            value={input} 
            onChange={e => setInput(e.target.value)} 
            placeholder="Seed a new idea..." 
            className="main-input"
          />
          <button onClick={() => submitIdea('base')} className="btn primary">Seed Idea</button>
        </div>
      </header>

      <main className="main-content">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={(_, node) => setSelectedParent(Number(node.id))}
          fitView
          className="flow-container"
        >
          <Background color="#333" gap={20} />
          <Controls />
          <MiniMap nodeColor={() => '#7b1fa2'} maskColor="rgba(0,0,0,0.5)" />
          
          <Panel position="bottom-center" className="action-panel">
            <div className="panel-hint">
              {selectedParent ? "Mutate the selected idea:" : "Select a node to begin evolution"}
            </div>
            <div className="btn-group">
              <button onClick={() => submitIdea('expand')} disabled={!selectedParent || loading} className="btn">Expand</button>
              <button onClick={() => submitIdea('rephrase')} disabled={!selectedParent || loading} className="btn">Rephrase</button>
              <button onClick={() => submitIdea('mutate_keywords')} disabled={!selectedParent || loading} className="btn">Mutate</button>
              <button onClick={() => submitIdea('synthesize')} disabled={!selectedParent || loading} className="btn">Synthesize</button>
            </div>
          </Panel>
        </ReactFlow>
      </main>
    </div>
  );
};

export default App;
